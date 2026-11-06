import {lockFeet} from '../rig/bind.mjs';
import {clamp, mix, smooth, world, wrap} from '../rig/runtime.mjs';

function trackAt(keys, time) {
  const right = keys.findIndex(([t]) => t > time);
  if (right < 0) return keys.at(-1).slice(1);
  if (right === 0) return keys[0].slice(1);
  const [from, ...a] = keys[right - 1];
  const [to, ...b] = keys[right];
  const u = smooth((time - from) / (to - from));
  return a.map((value, i) => mix(value, b[i], u));
}

function gaitAt(leg, gait, u) {
  const phase = (u + leg.phase) % 1;
  const swing = clamp((phase - gait.duty) / (1 - gait.duty), 0, 1);
  return [leg.foot[0] + gait.stride * (gait.duty / 2 - phase + smooth(swing)),
    leg.foot[1] + gait.lift * Math.sin(Math.PI * swing) ** 2];
}

function buildClip(rig, spec, name, source) {
  const {duration, gait, tracks = {}, rise, events = [], attachment_keys = {}} = source;
  const samples = Math.round(duration * 120);
  if (!Number.isFinite(duration) || duration <= 0 || Math.abs(duration * 120 - samples) > 1e-6) {
    throw new Error('Clip duration must align with 120 Hz: ' + name);
  }
  const keyTimes = new Set([0, duration]);
  const validateTimes = keys => {
    let previous = -1;
    for (const t of keys) {
      if (!Number.isFinite(t) || t < 0 || t > duration || t <= previous) {
        throw new Error('Invalid or unordered key in ' + name);
      }
      keyTimes.add(t);
      previous = t;
    }
  };
  const bones = new Set(rig.bones.map(bone => bone.id));
  for (const [bone, keys] of Object.entries(tracks)) {
    if (!bones.has(bone) || !keys.length || keys.some(row => row.length !== 4 || !row.every(Number.isFinite))) {
      throw new Error('Invalid bone track: ' + bone);
    }
    validateTimes(keys.map(key => key[0]));
  }
  if (rise) validateTimes(rise.map(key => key[0]));
  for (const [part, keys] of Object.entries(attachment_keys)) {
    const slot = rig.attachments.find(s => s.part === part);
    if (!slot || keys.some(key => key.variant && !slot.variants?.[key.variant])) {
      throw new Error('Invalid attachment track: ' + part);
    }
    validateTimes(keys.map(key => key.time));
  }
  const contacts = {}, clipEvents = [...events];
  for (const leg of rig.legs) {
    const point = 'sole_' + leg.suffix;
    contacts[point] = [];
    if (gait) {
      for (let cycle = 0; cycle <= 1; cycle++) {
        const start = cycle - leg.phase;
        const lo = Math.max(0, start), hi = Math.min(1, start + gait.duty);
        if (hi > lo) contacts[point].push([lo * duration, hi * duration]);
        if (start >= 0 && start < 1) clipEvents.push({id:'footstep', time:start * duration, point});
      }
    } else {
      contacts[point] = source.contacts ?? [[0, duration]];
    }
  }
  const frames = Array.from({length:samples + 1}, (_, i) => {
    const time = duration * i / samples;
    const lift = rise ? trackAt(rise, time)[0] : 0;
    const pose = Object.fromEntries(Object.entries(tracks).map(([bone, keys]) => [bone, trackAt(keys, time)]));
    if (lift) {
      pose.hip ??= [0, 0, 0];
      pose.hip[1] += lift;
    }
    const targets = Object.fromEntries(rig.legs.map(leg => {
      const [x, y] = gait ? gaitAt(leg, gait, i / samples) : leg.foot;
      return [leg.suffix, [x, y + lift, 0]];
    }));
    lockFeet(rig, pose, targets);
    if (spec.worldAngles) {
      const w = world(rig, pose);
      for (const [bone, angle] of Object.entries(spec.worldAngles)) {
        pose[bone] = [0, 0, wrap(angle - w[bone].a)];
      }
    }
    return pose;
  });
  return {name, duration, fps:30, bake_hz:120, frames,
    events:clipEvents.sort((a,b)=>a.time-b.time), keyTimes:[...keyTimes].sort((a,b)=>a-b),
    meta:{label:source.label, loop:!!source.loop, root_motion_mode:'in_place',
      locomotion_speed:gait ? gait.stride/duration : 0, contact_intervals:contacts,
      required_events:[...new Set(clipEvents.map(event=>event.id))], qa_exceptions:[],
      support_rule:gait || !rise ? 'always' : null, attachment_keys}};
}

export function makeKeyedClips(rig, spec, names = Object.keys(spec.animation)) {
  return names.map(name => {
    const source = spec.animation[name];
    if (!source) throw new Error('Unknown authored clip: ' + name);
    return buildClip(rig, spec, name, source);
  });
}
