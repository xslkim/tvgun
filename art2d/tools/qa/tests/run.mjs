import assert from 'node:assert/strict';
import {join} from 'node:path';
import {read,root} from '../../../pipeline/export/build.mjs';
import {inspect} from '../check.mjs';

const dir=join(root,'assets','courier','export');
const {rig,clips}=read(join(dir,'character.json'));
const get=name=>read(join(dir,clips[name]));
const tests=[];
function test(name,body) { body(); tests.push(name); console.log('PASS '+name); }
const find=(report,rule,bone)=>report.findings.some(f=>f.rule===rule && (!bone || f.bone===bone));
function mutate(name,change) {
  const clip=get(name);
  change(clip);
  return inspect(rig,clip);
}
const mid=clip=>Math.floor(clip.frames.length/2);
test('idle positive',()=>assert.equal(inspect(rig,get('idle')).errors,0));
test('in-place walk positive',()=>assert.equal(inspect(rig,get('walk')).errors,0));
test('in-place run with flight positive',()=>assert.equal(inspect(rig,get('run')).errors,0));
test('reversed knee and IK sign flip',()=>{
  const bad=mutate('idle',c=>{c.frames[mid(c)].lower_leg_r[2]=90;});
  assert.ok(find(bad,'hinge_reverse','lower_leg_r'));
  assert.ok(find(bad,'ik_flip','lower_leg_r'));
});
test('sliding planted foot',()=>{
  const bad=mutate('walk',c=>{c.meta.locomotion_speed=0;});
  assert.ok(find(bad,'foot_slide','sole_r'));
});
test('wrong contact height',()=>{
  const bad=mutate('idle',c=>{c.frames[mid(c)].root=[0,22,0];});
  assert.ok(find(bad,'ground_contact','sole_r'));
});
test('discontinuous cycle pose',()=>{
  const bad=mutate('idle',c=>{c.frames.at(-1).head[2]+=12;});
  assert.ok(find(bad,'cycle_pose','head'));
});
test('discontinuous cycle velocity',()=>{
  const bad=mutate('idle',c=>{c.frames.at(-2).head[2]+=4;});
  assert.ok(find(bad,'cycle_speed','head'));
});
test('long-path wrap and abrupt rotation',()=>{
  const bad=mutate('idle',c=>{
    c.frames[mid(c)].head[2]=350;
    c.frames[mid(c)+1].head[2]=10;
  });
  assert.ok(find(bad,'angle_wrap','head'));
  assert.ok(find(bad,'angular_jump','head'));
});
test('stretched bone',()=>{
  const bad=mutate('idle',c=>{c.frames[mid(c)].upper_leg_r.push(1.25);});
  assert.ok(find(bad,'bone_length','upper_leg_r'));
});
test('missing attack event',()=>{
  const bad=mutate('attack_light',c=>{c.events=c.events.filter(e=>e.id!=='hit');});
  assert.ok(find(bad,'missing_event','hit'));
});
test('no walk support',()=>{
  const bad=mutate('walk',c=>{c.meta.contact_intervals={sole_l:[],sole_r:[]};});
  assert.ok(find(bad,'walk_support'));
});
test('no flight during run',()=>{
  const bad=mutate('run',c=>{c.meta.contact_intervals.sole_r=[[0,c.duration]];});
  assert.ok(find(bad,'run_aerial'));
});
test('hard constraint cannot be exempted',()=>{
  const bad=mutate('walk',c=>{
    c.meta.locomotion_speed=0;
    c.meta.qa_exceptions=[{rule:'foot_slide',bone:'sole_r',time:[0,c.duration],reason:'Fixture'}];
  });
  assert.ok(bad.findings.some(f=>f.rule==='foot_slide' && f.severity==='error'));
});
test('folded mesh',()=>{
  const dir=join(root,'assets','jelly','export');
  const {rig:soft,clips}=read(join(dir,'character.json'));
  const idle=read(join(dir,clips.idle));
  idle.frames[mid(idle)].jelly_top[4]=.01;
  assert.ok(find(inspect(soft,idle),'mesh_fold','hip'));
});
console.log(tests.length+' regression tests passed');
