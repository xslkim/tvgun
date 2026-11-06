import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {rotate} from '../../../pipeline/rig/runtime.mjs';

const model=JSON.parse(readFileSync(process.argv[2],'utf8'));
const {bones,animations,skeleton}=model;
const hip=bones.find(b=>b.name==='hip');
const root=bones.find(b=>b.name===hip.parent);
const idle=animations.idle.bones.hip;
assert.match(skeleton.spine,/^4\.3/);
assert.equal(idle.rotate[0].time??0,0);

function cubic(a,b,c,d,t) {
  const s=1-t;
  return s*s*s*a+3*s*s*t*b+3*s*t*t*c+t*t*t*d;
}
function evaluate(keys,t,field,axis=0) {
  const i=keys.findIndex(k=>(k.time??0)>t);
  if(i<0) return keys.at(-1)[field]??0;
  if(i===0) return 0;
  const a=keys[i-1], b=keys[i], start=a.time??0, end=b.time;
  const from=a[field]??0,to=b[field]??0;
  if(a.curve==='stepped') return from;
  if(!Array.isArray(a.curve)) return from+(to-from)*(t-start)/(end-start);
  const [x1,y1,x2,y2]=a.curve.slice(4*axis,4*axis+4);
  let lo=0,hi=1;
  for(let j=0;j<32;j++){
    const mid=(lo+hi)/2;
    if(cubic(start,x1,x2,end,mid)<t) lo=mid;else hi=mid;
  }
  return cubic(from,y1,y2,to,(lo+hi)/2);
}
for(const track of [idle.rotate,idle.translate]) {
  const field=track===idle.rotate?'value':'x';
  for(const k of track) assert.ok(Math.abs(evaluate(track,k.time??0,field)-(k[field]??0))<1e-6);
}
const t=.2;
const point=rotate((hip.x??0)+evaluate(idle.translate,t,'x'),hip.y+evaluate(idle.translate,t,'y',1),root.rotation??0);
assert.ok(point.every(Number.isFinite));
console.log(JSON.stringify({version:skeleton.spine,bones:bones.length,animations:Object.keys(animations).length,
  idleHip:{time:t,x:point[0],y:point[1],angle:(root.rotation??0)+evaluate(idle.rotate,t,'value')},
  scope:'JSON, hip key and Bezier sample. No Spine editor or redistributable runtime used.'},null,2));
