import {lockFeet} from '../rig/bind.mjs';
import {clamp, mix, smooth} from '../rig/runtime.mjs';

const wave = (u, phase=0) => Math.sin(2*Math.PI*(u+phase));
const period = q => ((q%1)+1)%1;
const curve = (u, keys) => {
  for (let i=1;i<keys.length;i++) {
    const [t,v]=keys[i], [p,w]=keys[i-1];
    if (u <= t) return mix(w,v,smooth(clamp((u-p)/(t-p),0,1)));
  }
  return keys.at(-1)[1];
};
const pi=Math.PI;
const POUNCE_START=.24, POUNCE_END=.65;
const pounces=(rig,name)=>rig.prototype==='quadruped' && name==='attack_heavy';

const MATRIX = {
  humanoid: ['idle','walk','run','jump_start','jump_air','jump_fall','jump_land','attack_light','attack_heavy','cast','hit','death','block','dash'],
  quadruped: ['idle','walk','run','attack_light','attack_heavy','hit','death','spawn'],
  winged: ['idle','fly','attack_light','attack_heavy','hit','death','spawn'],
  multileg: ['idle','walk','run','attack_light','attack_heavy','hit','death'],
  blob: ['idle','walk','jump_start','jump_air','jump_fall','jump_land','attack_light','attack_heavy','hit','death','spawn'],
};
const DURATIONS = {
  idle:2, fly:0.7, walk:1, run:0.7, attack_light:0.5, attack_heavy:0.9,
  jump_start:0.32,jump_air:0.5,jump_fall:0.4,jump_land:0.3,
  cast:1,hit:0.37,death:1.2,block:0.7,dash:0.55,spawn:1.1,
};
const EVENT = {
  attack_light:[['hit',.39],['sfx',.37]],attack_heavy:[['hit',.47],['sfx',.44]],
  cast:[['fx_spawn',.57]],jump_start:[['takeoff',1]],jump_land:[['land',0]],
  dash:[['sfx',.12]],block:[['guard_on',.23],['guard_off',.78]],
  hit:[['sfx',0]],death:[['defeated',.83]],spawn:[['fx_spawn',.25]],
};
const TIMES = {
  idle:[0,.25,.5,.75,1],walk:[0,.13,.25,.38,.5,.63,.75,.88,1],run:[0,.12,.24,.42,.5,.62,.74,.92,1],
  fly:[0,.25,.5,.75,1],attack_light:[0,.16,.39,.49,.72,1],
  attack_heavy:[0,.26,.47,.57,.80,1],cast:[0,.27,.57,.72,1],
  hit:[0,.19,.46,1],death:[0,.18,.46,.83,1],spawn:[0,.25,.47,.72,1],
  block:[0,.23,.78,1],dash:[0,.12,.43,.82,1],
  jump_start:[0,.52,1],jump_air:[0,.45,1],jump_fall:[0,.5,1],jump_land:[0,.32,1],
};
const LOOPS = new Set(['idle','walk','run','fly','jump_air']);
const p3=(x=0,y=0,a=0)=>[x,y,a];

function footPhase(leg, u, duty, stride, lift, phase, center = leg.foot[0]) {
  const q=period(u+phase);
  const s=clamp((q-duty)/(1-duty),0,1);
  return [center+stride*(duty/2-q+smooth(s)),leg.foot[1]+lift*Math.sin(pi*s)**2];
}

function action(name,u) {
  switch (name) {
    case 'attack_light': return curve(u,[[0,0],[.16,-.30],[.39,1],[.49,.94],[.72,.35],[1,0]]);
    case 'attack_heavy': return curve(u,[[0,0],[.26,-.65],[.47,1],[.57,.97],[.80,.36],[1,0]]);
    case 'cast': return curve(u,[[0,0],[.27,-.35],[.57,1],[.72,.88],[1,0]]);
    case 'hit': return curve(u,[[0,0],[.19,-1],[.46,-.34],[1,0]]);
    case 'death': return curve(u,[[0,0],[.18,-.18],[.46,.52],[.83,1],[1,1]]);
    case 'spawn': return curve(u,[[0,-1],[.25,-.78],[.47,.29],[.72,-.11],[1,0]]);
    case 'block': return curve(u,[[0,0],[.23,1],[.78,1],[1,0]]);
    case 'dash': return curve(u,[[0,0],[.12,-.28],[.43,1],[.82,.68],[1,0]]);
    default: return 0;
  }
}

function jump(name,u) {
  const curves={
    jump_start:[[0,0],[.52,-24],[1,28]],
    jump_air:[[0,28],[.50,40],[1,28]],
    jump_fall:[[0,28],[.45,17],[1,0]],
    jump_land:[[0,0],[.32,-31],[1,0]],
  };
  return curves[name] ? curve(u,curves[name]) : 0;
}

function poseAt(rig,spec,name,u,motion,duration) {
  const actionValue=action(name,u), flight=jump(name,u);
  const humanoid=rig.prototype==='humanoid';
  const a=humanoid && name==='death' && actionValue>0 ? smooth(actionValue) : actionValue;
  const moving=!!motion, running=name==='run', attacking=name.startsWith('attack'), isJump=name.startsWith('jump');
  const breathing=wave(u,-.25)+1;
  const leap=pounces(rig,name)?clamp((u-POUNCE_START)/(POUNCE_END-POUNCE_START),0,1):0;
  const leapHeight=54*Math.sin(pi*leap)**2;
  const p={}, targets={};
  let shift=0,bob=0,tilt=0;
  if (name==='idle') { bob=-3*breathing; tilt=1.8*wave(u); }
  if (moving) {
    shift=3*wave(2*u); bob=running ? -15-8*wave(2*u,.2) : -8-7*wave(2*u,.1);
    tilt=(running?-7:-4)+2*wave(2*u);
  }
  if (attacking) { shift=a*18; bob=-7*Math.abs(a); tilt=-8*a; }
  if (name==='hit') { shift=23*a; bob=17*a; tilt=-15*a; }
  if (name==='cast') { shift=-6*a; bob=-9*Math.abs(a); tilt=3*a; }
  if (name==='block') { shift=-15*a; bob=-23*a; tilt=-7*a; }
  if (name==='dash') {
    bob=-26*Math.abs(a);
    tilt=-13*a;
    p.root=p3(265*smooth(clamp((u-.12)/.78,0,1)));
  }
  if (isJump) {
    bob=Math.min(flight,0);
    tilt=(-7+flight*.11)*smooth(clamp(flight/18,0,1));
    if (humanoid) {
      const launch=name==='jump_start' ? smooth(clamp((u-.18)/.34,0,1)) : 1;
      const landing=name==='jump_land' ? 1-smooth(clamp(u/.55,0,1)) : 1;
      const nearGround=1-smooth(clamp(Math.abs(flight)/24,0,1));
      bob+=Math.max(0,flight)*1.32-10*nearGround*launch*landing;
    }
  }
  if (pounces(rig,name)) {
    p.root=p3(134*smooth(leap));
    shift=13*a;
    bob+=.87*leapHeight;
    tilt=-12*a;
  }
  if (name==='spawn') { bob=24*a; tilt=6*a; }
  if (name==='death') {
    const collapse=Math.max(0,a);
    shift=-37*a;
    bob=-collapse*(spec.hip[1]-(spec.collapseHeight ?? 84));
    if (rig.prototype==='humanoid' && a<0) {
      shift=0;
      bob=28*a;
    }
    tilt=rig.prototype==='humanoid'?77*a:rig.prototype==='quadruped'?6*a:12*a;
  }
  p.hip=p3(shift,bob,tilt);

  if (rig.prototype==='humanoid') {
    const swing=moving ? (running?34:23)*wave(u) : 0;
    const landTuck=name==='jump_land' ? -flight/31 : 0;
    p.spine=p3(0,0,moving?3*wave(2*u,.18):attacking?-7*a:2*wave(u));
    if (!LOOPS.has(name) && !attacking) p.spine=p3(0,0,4*a);
    p.head=p3(0,0, name==='idle' ? 4*wave(u,-.06) : attacking ? 5*a : -tilt*.38);
    p.scarf=p3(0,0, moving ? -5+7*wave(u,-.14) : name==='idle' ? 4*wave(u,-.12) : name==='death' ? -94*Math.max(0,a) : 9*a);
    p.upper_arm_r=p3(0,0, name==='block'?40*a : name==='cast'?105*a : attacking?(name==='attack_heavy'?75:59)*a : name==='death'?-27*a : swing+(isJump?flight*.8+18*landTuck:10*a));
    p.upper_arm_l=p3(0,0, attacking?-31*a : name==='death'?32*a : -swing+(isJump?flight*.45:-24*a));
    p.forearm_r=p3(0,0, name==='block'?83*a : attacking?25*Math.abs(a) : 11*Math.abs(a)+Math.max(0,swing)**2*.018);
    p.forearm_l=p3(0,0, 5*Math.abs(a)+Math.max(0,-swing)**2*.018);
    p.weapon=p3(0,0, attacking?24*a : name==='death'?-65*a : name==='cast'?31*a : -swing*.43+Math.max(0,-swing)**2*.013+24*landTuck);
  } else if (rig.prototype==='winged') {
    const f = name==='death' ? .53*Math.max(0,a)+.22*wave(u)*(1-Math.max(0,a)) : name==='fly' ? wave(u,-.15) : name==='idle' ? wave(u*2,-.08) : attacking ? -a : wave(u)*.5*(1-Math.max(0,a));
    p.hip=p3(shift+(attacking?58*a:0),name==='death'?-Math.max(0,a)*(spec.hip[1]-55):name==='spawn'?63*a:attacking?-41*a:(name==='fly'?28:10)*wave(u),attacking?-19*a:name==='death'?-27*a:tilt);
    p.wing_r=p3(0,0, (name==='fly'?39:28)*f);
    p.wing_l=p3(0,0, -(name==='fly'?35:25)*f);
    p.wing_tip_r=p3(0,0,17*(name==='fly'?wave(u,-.26):f));
    p.wing_tip_l=p3(0,0,-14*(name==='fly'?wave(u,-.29):f));
    p.head=p3(0,0, attacking?12*a:-7*f);
    p.tail=p3(0,0,name==='death'?-17*a:13*f);
  } else if (rig.prototype==='blob') {
    const pulse = name==='idle' ? -.08*breathing : name==='walk' ? .21*wave(u) : isJump ? clamp(flight/175,-.2,.22) : attacking ? -.24*a : name==='death' ? -.67*a : .23*a;
    p.hip=[moving?14*wave(u):attacking?40*a:shift,Math.max(0,flight),0,1-pulse*.72,1];
    p.jelly_top=[moving?30*wave(u,-.10):attacking?34*a:0,0,0,1-pulse*.37,1+pulse];
  } else {
    const v=moving?wave(u,-.12):name==='idle'?wave(u):a;
    p.head=p3(0,0,attacking?-27*a:name==='death'?-26*a:9*v);
    p.tail=p3(0,0,attacking?22*a:14*v);
    p.tail_tip=p3(0,0,moving?18*wave(u,-.23):10*v);
    if (rig.prototype==='quadruped') p.jaw=p3(0,0,attacking?-36*curve(u,[[0,0],[.15,.05],[.34,.84],[.48,.12],[.67,.02],[1,0]]):0);
    if (rig.prototype==='multileg') p.fang=p3(0,0,attacking?25*a:5*v);
  }

  const rootX=p.root?.[0]??0;
  for (const leg of rig.legs) {
    const [x,y]=moving?footPhase(leg,u,motion.duty,motion.speed*duration,motion.height,motion.phases?.[leg.suffix]??leg.phase,motion.footCenters?.[leg.suffix]):leg.foot;
    const high=Math.max(0,flight);
    let target=[x+rootX,y+high+leapHeight,0];
    if (isJump && high) target=[x+(leg.phase? -9:13)*high/28,y+high*1.9,(leg.phase?-12:8)*smooth(clamp(high/18,0,1))];
    if (name==='death' && a>0) {
      // Collapse with the soles in view and the feet following the hips.
      const direction=rig.prototype==='humanoid'?1:rig.prototype==='quadruped'?-leg.chain[3]:(leg.suffix.startsWith('front')?1:-1);
      const slide=rig.prototype==='humanoid'?(leg.suffix==='l'?115:66):rig.prototype==='quadruped'?(leg.suffix==='back_r'?68:95):direction>0?52:96;
      target=[x+a*slide*direction,y+a*3,0];
    }
    if (name==='dash') target=[x+rootX+(leg.phase? -70:47)*Math.max(0,a),y+(leg.phase?27:7)*Math.max(0,a),0];
    targets[leg.suffix]=target;
  }
  lockFeet(rig,p,targets);
  const valid = new Set(rig.bones.map(b=>b.id));
  return Object.fromEntries(Object.entries(p).filter(([id])=>valid.has(id)));
}

function support(rig,spec,name,duration,motion) {
  const contacts={}, events=[];
  const pointNames=rig.legs.map(leg=>'sole_'+leg.suffix);
  if (motion && rig.legs.length) {
    for (const leg of rig.legs) {
      const id='sole_'+leg.suffix;
      contacts[id]=[];
      for(let k=0;k<2;k++) {
        const lo=k-(motion.phases?.[leg.suffix]??leg.phase), hi=lo+motion.duty;
        if (hi>0 && lo<1) {
          contacts[id].push([Math.max(0,lo)*duration,Math.min(1,hi)*duration]);
        }
        if (lo>=0 && lo<1) events.push({id:'footstep',time:lo*duration,point:id});
      }
    }
  } else {
    let interval;
    if (['idle','attack_light','attack_heavy','hit','block','cast','jump_land','spawn'].includes(name)) interval=[0,duration];
    if(name==='jump_start') interval=[0,.52*duration];
    if(pounces(rig,name)) {
      for(const id of pointNames) contacts[id]=[[0,POUNCE_START*duration],[POUNCE_END*duration,duration]];
      return {contacts,events};
    }
    for (const id of pointNames) contacts[id]=interval?[interval]:[];
  }
  return {contacts,events};
}

export function makeClips(rig,spec,names=MATRIX[rig.prototype]) {
  const supported=MATRIX[rig.prototype];
  if (!supported || !names || names.some(name=>!supported.includes(name))) {
    throw new Error('Invalid clips for prototype '+rig.prototype);
  }
  return names.map(name=>{
    const motion = rig.legs.length && ['walk','run'].includes(name) ? spec[name] : null;
    const duration=Math.round((motion?.duration??DURATIONS[name])*30)/30;
    const {contacts,events}=support(rig,spec,name,duration,motion);
    for (const [id,u] of EVENT[name]??[]) events.push({id,time:u*duration});
    const required_events = [...new Set([...(EVENT[name]??[]).map(([id])=>id),...(motion?['footstep']:[])])];
    const length=Math.round(duration*120);
    const frames=Array.from({length:length+1},(_,i)=>poseAt(rig,spec,name,i/length,motion,duration));
    return {name,duration,fps:30,bake_hz:120,frames,events:events.sort((a,b)=>a.time-b.time),
      keyTimes:TIMES[name].map(u=>u*duration),
      meta:{loop:LOOPS.has(name),root_motion_mode:name==='dash'||pounces(rig,name)?'root':'in_place',
        locomotion_speed:motion?.speed??0,contact_intervals:contacts,required_events,qa_exceptions:[],
        support_rule:motion?(name==='run'?'aerial':'always'):null}};
  });
}
