import {existsSync, mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {makeRig} from '../rig/bind.mjs';
import {makeClips} from '../anim/clips.mjs';
import {world} from '../rig/runtime.mjs';

export const root=fileURLToPath(new URL('../../',import.meta.url));
export const read=path=>JSON.parse(readFileSync(path,'utf8').replace(/^\uFEFF/,''));
export const save=(path,value,pretty=true)=>writeFileSync(path,JSON.stringify(value,null,pretty?2:0)+'\n');

export function build(id, only) {
  if (!/^[a-z][a-z0-9_]+$/.test(id)) throw new Error('Invalid character identifier');
  const dir=join(root,'assets',id);
  const spec=read(join(dir,'concept','rig_layout.json'));
  if (id!==spec.id) throw new Error('Folder and spec id disagree');
  const anchors=read(join(dir,'parts','anchors.json'));
  const atlas=read(join(dir,'export','atlas.json'));
  const rig=makeRig(spec,anchors,atlas);
  const clips=makeClips(rig,spec,only);
  for (const name of ['rig','anim','export','preview','qa']) mkdirSync(join(dir,name),{recursive:true});
  const support=rig.legs.map(l=>({id:'sole_'+l.suffix,bone:l.chain[2],point:l.sole}));
  save(join(dir,'rig','rig_meta.json'),{coordinate_system:{y:'up',unit:'pixel',angle:'deg_ccw'},bind_pose:world(rig),character_height:rig.height,ground_y:rig.ground,support});
  save(join(dir,'rig','joint_limits.json'),rig.limits);
  const boneMap=Object.fromEntries(rig.bones.map(b=>[b.id,[]]));
  for (const [i,slot] of rig.attachments.entries()) {
    const weights=slot.mesh?[...new Set(slot.mesh.vertices.flatMap(v=>v.weights.map(w=>w[0])))]:[slot.bone];
    boneMap[slot.bone].push({slot:i,part:slot.part,variants:Object.keys(slot.variants??{}),weights});
  }
  save(join(dir,'rig','rig_map.json'),boneMap);
  save(join(dir,'rig','skeleton.json'),rig);
  save(join(dir,'anim','anim_meta.json'),Object.fromEntries(clips.map(c=>[c.name,c.meta])));
  save(join(dir,'anim','blocking.json'),Object.fromEntries(clips.map(c=>[c.name,c.keyTimes])));
  const index=Object.fromEntries(clips.map(c=>[c.name,'clips/'+c.name+'.json']));
  mkdirSync(join(dir,'export','clips'),{recursive:true});
  for (const clip of clips) save(join(dir,'export',index[clip.name]),clip,false);
  save(join(dir,'export','character.json'),{rig,clips:index});
  const demoPath=join(root,'demos','characters.json');
  const demo=existsSync(demoPath)?read(demoPath):[];
  const next={id,label:spec.label,prototype:spec.prototype,...(spec.validation?{validation:true}:{}),path:'/assets/'+id+'/export/character.json'};
  const order=['humanoid','quadruped','winged','multileg','blob'];
  save(demoPath,[...demo.filter(x=>x.id!==id),next].sort((a,b)=>Number(!!a.validation)-Number(!!b.validation)||order.indexOf(a.prototype)-order.indexOf(b.prototype)||a.id.localeCompare(b.id)));
  console.log(id+': '+rig.bones.length+' bones, '+clips.length+' clips');
}

if(process.argv[1] && fileURLToPath(import.meta.url)===process.argv[1]) {
  const [id, ...only]=process.argv.slice(2);
  if (!id) throw new Error('Usage: node pipeline/export/build.mjs <id> [clip ...]');
  build(id,only.length?only:undefined);
}
