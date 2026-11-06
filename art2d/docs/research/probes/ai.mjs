import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';

const dir=process.argv[2];
const read=name=>readFileSync(join(dir,name),'utf8');
const info=[];
for(const name of ['flux_schnell.json','image_qwen_image_layered.json']) {
  const graph=JSON.parse(read(name));
  const types=graph.nodes.map(n=>n.type);
  assert.ok(types.includes('SaveImage'));
  if(name.startsWith('flux')) assert.ok(types.includes('KSampler') && types.includes('CheckpointLoaderSimple'));
  else assert.ok(types.includes('LoadImage') && graph.definitions?.subgraphs?.length>0);
  info.push({name,nodes:types,subgraphs:graph.definitions?.subgraphs?.length??0});
}
const raw=read('char_cfg.yaml');
const joints=[...raw.matchAll(/^  name: (.+)\r?$/gm)].map(m=>m[1]);
assert.ok(joints.includes('root') && joints.includes('hip') && joints.includes('torso'));
assert.equal(new Set(joints).size,joints.length);
info.push({name:'Animated Drawings char1',joints,hasLimits:/joint_limits|bend_sign|contact_intervals/.test(raw)});
console.log(JSON.stringify({scope:'Official graph and sample schema probes; no model inference',info},null,2));
