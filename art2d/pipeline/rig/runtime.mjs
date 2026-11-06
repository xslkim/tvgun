export const rad = d => d * Math.PI / 180;
export const deg = r => r * 180 / Math.PI;
export const wrap = a => ((a + 180) % 360 + 360) % 360 - 180;
export const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
export const mix = (a, b, t) => a + (b - a) * t;
export const smooth = t => t * t * (3 - 2 * t);

export function rotate(x, y, angle) {
  const c = Math.cos(rad(angle)), s = Math.sin(rad(angle));
  return [c * x - s * y, s * x + c * y];
}

export function transform(bone, point) {
  const [x, y] = rotate(point[0] * bone.sx, point[1] * bone.sy, bone.a);
  return [bone.x + x, bone.y + y];
}

export function world(rig, pose = {}) {
  const result = {};
  for (const b of rig.bones) {
    const [dx = 0, dy = 0, da = 0, sx = 1, sy = 1] = pose[b.id] ?? [];
    const p = result[b.parent];
    const [x, y] = p ? transform(p, [b.x + dx, b.y + dy]) : [b.x + dx, b.y + dy];
    result[b.id] = {x, y, a: (p?.a ?? 0) + b.a + da, sx, sy};
  }
  return result;
}

export function blend(from, to, t) {
  const result = {};
  for (const id of new Set([...Object.keys(from), ...Object.keys(to)])) {
    const rest = [0, 0, 0, 1, 1];
    result[id] = rest.map((value, i) => mix(from[id]?.[i] ?? value, to[id]?.[i] ?? value, t));
  }
  return result;
}

export function sample(clip, time, repeat = clip.meta.loop) {
  const t = repeat ? ((time % clip.duration) + clip.duration) % clip.duration : clamp(time, 0, clip.duration);
  const frame = t / clip.duration * (clip.frames.length - 1);
  const i = Math.floor(frame);
  return blend(clip.frames[i], clip.frames[Math.min(i + 1, clip.frames.length - 1)], frame - i);
}

export function solve2(rig, pose, [upper, lower, end, sign], x, y, endAngle = 0) {
  const bones = Object.fromEntries(rig.bones.map(b => [b.id, b]));
  const w = world(rig, pose);
  const a = w[upper], b = bones[upper], c = bones[lower], e = bones[end];
  const distance = clamp(Math.hypot(x - a.x, y - a.y), Math.abs(b.length - c.length) + 0.001, b.length + c.length - 0.001);
  const bend = sign * deg(Math.acos(clamp((distance ** 2 - b.length ** 2 - c.length ** 2) / (2 * b.length * c.length), -1, 1)));
  const angle = deg(Math.atan2(y - a.y, x - a.x) - Math.atan2(c.length * Math.sin(rad(bend)), b.length + c.length * Math.cos(rad(bend))));
  pose[upper] = [0, 0, wrap(angle - w[b.parent].a - b.a)];
  pose[lower] = [0, 0, wrap(bend - c.a)];
  pose[end] = [0, 0, wrap(endAngle - angle - bend - e.a)];
}

export function skinVertex(vertex, w) {
  const position = [0, 0];
  for (const [id, weight, x, y] of vertex.weights) {
    const [vx, vy] = transform(w[id], [x, y]);
    position[0] += vx * weight;
    position[1] += vy * weight;
  }
  return position;
}
