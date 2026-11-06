import {spawnSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {join} from 'node:path';
import {root,read} from '../../pipeline/export/build.mjs';
import {world,sample,skinVertex} from '../../pipeline/rig/runtime.mjs';

const [id,...args]=process.argv.slice(2);
if(!id) throw new Error('Usage: node tools/qa/render.mjs <id> [clip ...] [--quick] [--debug]');
const path=join(root,'assets',id);
const {rig,clips}=read(join(path,'export','character.json'));
const quick=args.includes('--quick'), debug=args.includes('--debug');
const only=args.filter(a=>a!=='--quick' && a!=='--debug');
const reportPath=join(path,'qa','report.json');
const reports=existsSync(reportPath)?read(reportPath).reports:[];
const frame=(pose,time,caption)=>{
  const w=world(rig,pose);
  return {time,caption,w,meshes:rig.attachments.map(s=>s.mesh?.vertices.map(v=>skinVertex(v,w)))};
};
const shots=[];
for(const name of (only.length?only:Object.keys(clips))) {
  const clip=read(join(path,'export',clips[name]));
  const fps=quick?15:30;
  const at=(t,label)=>frame(sample(clip,t,false),t,label);
  const count=Math.round(clip.duration*fps);
  const film=Array.from({length:count+(clip.meta.loop?0:1)},(_,i)=>at(i*clip.duration/count));
  const keys=clip.keyTimes.filter(t=>!clip.meta.loop || t<clip.duration).map(t=>at(t,name+' | '+t.toFixed(2)+'s'));
  const faults=(reports.find(r=>r.clip===name)?.findings??[]).flatMap((f,i)=>f.severity==='error'?[{
    name:name+'_'+i,frame:at(f.time,f.rule+' '+f.bone+' '+f.time.toFixed(3)+'s'),
  }]:[]);
  shots.push({name,film,keys,faults,fps,loop:clip.meta.loop});
}
const bind=frame({},0,'bind pose');
const limits=rig.limits.flatMap(j=>[j.min,j.max].map((angle,i)=>{
  const a=j.chain?angle-(bind.w[j.id].a-bind.w[j.parent].a):angle;
  return frame({[j.id]:[0,0,a]},0,j.id+' '+(i?'max':'min')+' '+angle+' deg');
}));
const result=spawnSync('uv',['-q','run','--python','3.12','--with','Pillow==12.2.0','python',join(root,'tools','qa','render.py')],{
  input:JSON.stringify({path,rig,shots,bind,limits,debug}),encoding:'utf8',maxBuffer:16*1024*1024,
});
if(result.error) throw result.error;
process.stdout.write(result.stdout);
process.stderr.write(result.stderr);
process.exitCode=result.status??1;
