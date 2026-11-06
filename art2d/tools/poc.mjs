import assert from 'node:assert/strict';
import {mkdirSync, writeFileSync} from 'node:fs';
import {sample, world} from '../pipeline/rig/runtime.mjs';

const rig = {bones: [
  {id:'root', x:0, y:0, a:0}, {id:'hip', parent:'root', x:0, y:90, a:0},
  {id:'chest', parent:'hip', x:0, y:15, a:0}, {id:'head', parent:'chest', x:0, y:36, a:0},
  {id:'arm', parent:'chest', x:12, y:24, a:-75}, {id:'forearm', parent:'arm', x:28, y:0, a:12},
  {id:'hand', parent:'forearm', x:24, y:0, a:0},
]};
const clip = {duration:2, meta:{loop:true}, frames:Array.from({length:61}, (_, i) => ({
  chest:[0,0,4*Math.sin(i*Math.PI/30)], forearm:[0,0,3*(1-Math.cos(i*Math.PI/30))],
}))};
const frames = Array.from({length:60}, (_, i) => world(rig,sample(clip,i/30)));
assert.equal(frames[0].head.y,141);
assert.notEqual(frames[7].hand.x,frames[0].hand.x);
assert.deepEqual(world(rig,sample(clip,0)),world(rig,sample(clip,2)));
mkdirSync('demos/poc',{recursive:true});
writeFileSync('demos/poc/world.json',JSON.stringify({rig,clip,frames}));
console.log('7 bones, 60 world samples, start/end verified');
