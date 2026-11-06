import {mkdirSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {root,read,save} from '../../pipeline/export/build.mjs';
import {sample,world,transform,wrap,skinVertex} from '../../pipeline/rig/runtime.mjs';

const EPS = 1e-7;
export const QA_VERSION='1.0.0';
const length=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);

export function inspect(rig,clip) {
  const {meta,duration}=clip;
  const results=new Map(), h=rig.height, bind=world(rig);
  const issues=(rule,bone,time,value,limit,severity='error')=>{
    const ex=meta.qa_exceptions.find(x=>x.rule===rule && x.bone===bone &&
      typeof x.reason==='string' && x.reason.trim() && Array.isArray(x.time) && x.time[0]<=time && x.time[1]>=time);
    const hard=['hinge_reverse','bone_length','foot_slide','ground_contact','ground_penetration','cycle_pose','cycle_speed','walk_support','run_aerial','ik_flip','angle_wrap','mesh_fold'];
    const level=ex && !hard.includes(rule)?'exception':severity;
    const id=[rule,bone,level].join('/');
    const previous=results.get(id);
    if (!previous || Math.abs(value)>Math.abs(previous.value)) {
      results.set(id,{rule,bone,time,value,limit,severity:level,...(level==='exception'?{reason:ex.reason}:{})});
    }
  };
  const meshArea=([a,b,c])=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
  const meshes=rig.attachments.filter(s=>s.mesh).map(s=>{
    const points=s.mesh.vertices.map(v=>skinVertex(v,bind));
    return {slot:s,areas:s.mesh.triangles.map(tri=>meshArea(tri.map(i=>points[i])))};
  });
  const keyRate=clip.keyTimes.length/duration;
  if(keyRate<2 || keyRate>22) issues('key_density','timeline',0,keyRate,[2,22],'hint');
  const poses=new Map();
  const times=new Set([0,duration,...clip.keyTimes,...clip.events.map(e=>e.time)]);
  for (let k=0;k<clip.frames.length;k++) times.add(k*duration/(clip.frames.length-1));
  for (let k=0;k<=Math.ceil(duration*120);k++) times.add(Math.min(k/120,duration));
  const contacts=meta.contact_intervals;
  for (const intervals of Object.values(contacts)) {
    for (const [start,end] of intervals) {
      if (!(0<=start && end<=duration+EPS && start<end)) throw new Error('Invalid contact interval');
      times.add(start); times.add(end);
    }
  }
  const timeline=[...times].sort((a,b)=>a-b).filter((t,i,sorted)=>i===0 || t-sorted[i-1]>EPS);
  for(const t of timeline) {
    if(!Number.isFinite(t) || t<0 || t>duration+EPS) throw new Error('Invalid timestamp');
    poses.set(t,world(rig,sample(clip,t,false)));
  }
  for (const id of meta.required_events) if(!clip.events.some(e=>e.id===id)) issues('missing_event',id,0,1,0);
  const joints=Object.fromEntries(rig.limits.map(j=>[j.id,[]]));
  const contactOrigins=new Map();
  const signs=new Map();
  let previous, prevTime=0, air=0, bodyTravel=0, unbalanced=0;
  for (const [t,w] of poses) {
    const dt=t-prevTime;
    for (const b of rig.bones) {
      const p=w[b.id];
      if (![p.x,p.y,p.a,p.sx,p.sy].every(Number.isFinite)) throw new Error('Non-finite transform for '+b.id);
      if (!b.elastic && b.length>0 && Math.abs(p.sx-1)>.02+EPS) {
        issues('bone_length',b.id,t,Math.abs(p.sx-1),.02);
      }
      if (!b.elastic && Math.abs(p.sy-1)>.02+EPS) issues('bone_scale',b.id,t,Math.abs(p.sy-1),.02);
      if (b.parent && !b.elastic && !['hip','root'].includes(b.id)) {
        const expected=length(bind[b.id],bind[b.parent]);
        const drift=Math.abs(length(p,w[b.parent])-expected);
        if (drift>Math.max(.001,.02*expected)+EPS) issues('bone_length',b.id,t,drift/Math.max(expected,.05),.02);
      }
      if (previous) {
        const angle=(p.a-(w[b.parent]?.a??0))-(previous[b.id].a-(previous[b.parent]?.a??0));
        if(Math.abs(angle)>180+EPS) issues('angle_wrap',b.id,t,angle,180);
        if (Math.abs(angle/dt)>1440+EPS) issues('angular_jump',b.id,t,angle/dt,1440);
        const velocity=length(p,previous[b.id])/dt;
        if (velocity>8*h) issues('translation_jump',b.id,t,velocity,8*h);
      }
    }
    for (const {slot,areas} of meshes) {
      const points=slot.mesh.vertices.map(v=>skinVertex(v,w));
      for (const [index,tri] of slot.mesh.triangles.entries()) {
        const area=meshArea(tri.map(i=>points[i]));
        if (area/areas[index]<.03) issues('mesh_fold',slot.bone,t,area/areas[index],.03);
      }
    }
    if (previous) bodyTravel+=length(w.hip,previous.hip);
    for (const j of rig.limits) {
      const physical=wrap(w[j.id].a-w[j.parent].a);
      const rest=wrap(bind[j.id].a-bind[j.parent].a);
      const delta=wrap(physical-rest);
      // A limb in its bind pose can already be bent. Allow extension to straight.
      const value=j.chain?physical:delta;
      joints[j.id].push([t,value]);
      if(value<j.min-EPS || value>j.max+EPS) issues('joint_limit',j.id,t,value,[j.min,j.max]);
      if(j.bend_sign && j.bend_sign*physical < -5-EPS) issues('hinge_reverse',j.id,t,physical,5);
      if(j.chain && Math.abs(physical)>2) {
        const sign=Math.sign(physical);
        if(signs.has(j.id) && signs.get(j.id)!==sign) issues('ik_flip',j.id,t,physical,0);
        signs.set(j.id,sign);
      }
    }
    const active=[]; let allAirborne=rig.legs.length>0;
    for (const leg of rig.legs) {
      const id='sole_'+leg.suffix;
      const [x,y]=transform(w[leg.chain[2]],leg.sole);
      const intervals=contacts[id]??[];
      const clearance=y-rig.ground;
      allAirborne &&= clearance>.001*h;
      if (clearance<-.01*h-EPS) issues('ground_penetration',id,t,clearance,.01*h);
      for (const [i,[start,end]] of intervals.entries()) {
        if(t<start-EPS || t>end+EPS) continue;
        active.push(x);
        const compensated=x+(meta.root_motion_mode==='in_place'?meta.locomotion_speed*t:0);
        const key=id+'/'+i;
        if(!contactOrigins.has(key)) contactOrigins.set(key,compensated);
        const drift=compensated-contactOrigins.get(key);
        if(Math.abs(drift)>.01*h+EPS) issues('foot_slide',id,t,drift,.01*h);
        if(Math.abs(clearance)>.01*h+EPS) issues('ground_contact',id,t,clearance,.01*h);
      }
    }
    if (meta.support_rule==='always' && active.length===0) issues('walk_support','hip',t,1,0);
    if (meta.support_rule==='aerial' && !active.length && allAirborne) air+=dt;
    if (active.length>1 && ['idle','walk','block','cast'].includes(clip.name)) {
      if (w.hip.x<Math.min(...active)-.06*h || w.hip.x>Math.max(...active)+.06*h) unbalanced+=dt;
    }
    prevTime=t; previous=w;
  }
  if (meta.support_rule==='aerial' && air<.025) issues('run_aerial','hip',duration,air,.025);
  if (unbalanced>duration*.25) issues('balance','hip',duration,unbalanced/duration,.25,'warning');
  if (bodyTravel<h*.008 && !['idle','block','cast'].includes(clip.name)) {
    const travel=Object.values(joints).reduce((s,points)=>s+points.slice(1).reduce((v,[,a],i)=>v+Math.abs(a-points[i][1]),0),0);
    if (travel<12 && !rig.elastic) issues('low_motion','hip',duration,bodyTravel,.008*h,'warning');
  }
  if(meta.loop) {
    const dt=Math.min(duration/4,duration/(clip.frames.length-1));
    const first=world(rig,sample(clip,0,false)), last=world(rig,sample(clip,duration,false));
    const next=world(rig,sample(clip,dt,false)), prev=world(rig,sample(clip,duration-dt,false));
    for(const b of rig.bones) {
      const id=b.id, p=first[id], q=last[id], n=next[id], v=prev[id];
      const angle=Math.abs(wrap(p.a-q.a)), distance=length(p,q);
      const scale=Math.max(Math.abs(p.sx-q.sx),Math.abs(p.sy-q.sy));
      if(angle>1) issues('cycle_pose',id,duration,angle,1);
      if(distance>.005*h) issues('cycle_pose',id,duration,distance,.005*h);
      if(scale>.005) issues('cycle_pose',id,duration,scale,.005);
      const rate=Math.abs(wrap(n.a-p.a)-wrap(q.a-v.a))/dt;
      const linear=Math.hypot((n.x-p.x)-(q.x-v.x),(n.y-p.y)-(q.y-v.y))/dt;
      const scaleRate=Math.max(Math.abs(n.sx-p.sx-q.sx+v.sx),Math.abs(n.sy-p.sy-q.sy+v.sy))/dt;
      if(rate>85) issues('cycle_speed',id,duration,rate,85);
      if(linear>.65*h) issues('cycle_speed',id,duration,linear,.65*h);
      if(scaleRate>.8) issues('cycle_speed',id,duration,scaleRate,.8);
    }
  }
  const findings=[...results.values()];
  return {clip:clip.name,duration,samples:timeline.length,
    errors:findings.filter(x=>x.severity==='error').length,
    warnings:findings.filter(x=>x.severity==='warning').length,findings,joints};
}

function plots(report) {
  const colors=['#42d4b0','#ffd07a','#a1aaff','#ff826f','#8be4fd'];
  const bands=Object.entries(report.joints);
  const height=60+Math.max(1,bands.length)*92;
  const plots=bands.map(([name,points],i)=>{
    const base=55+i*92, max=Math.max(20,...points.map(([,v])=>Math.abs(v)));
    const line=points.map(([t,v])=>[190+t/report.duration*660,base+37-v/max*34].map(n=>n.toFixed(1)).join(',')).join(' ');
    return '<text x="20" y="'+(base+30)+'">'+name+'</text><text x="20" y="'+(base+49)+'" fill="#93adbd">±'+max.toFixed(0)+'°</text>'
      +'<path d="M190 '+(base+37)+' H850" stroke="#526677"/><polyline fill="none" stroke="'+colors[i%colors.length]+'" stroke-width="2" points="'+line+'"/>';
  }).join('');
  return '<svg xmlns="http://www.w3.org/2000/svg" width="890" height="'+height+'" viewBox="0 0 890 '+height+'"><rect width="100%" height="100%" fill="#142536"/><g fill="#eef6f8" font-family="monospace" font-size="14"><text x="20" y="28">'+report.clip+' | joint angle / time (0–'+report.duration.toFixed(3)+'s)</text>'+plots+'</g></svg>\n';
}

export function checkCharacter(id) {
  const folder=join(root,'assets',id), output=join(folder,'qa');
  const {rig,clips}=read(join(folder,'export','character.json'));
  mkdirSync(output,{recursive:true});
  const reports=[];
  for (const file of Object.values(clips)) {
    const c=read(join(folder,'export',file));
    const report=inspect(rig,c);
    reports.push(report);
    writeFileSync(join(output,c.name+'.svg'),plots(report));
  }
  const total=reports.reduce((n,r)=>n+r.errors,0);
  save(join(output,'report.json'),{version:QA_VERSION,id,total,reports},false);
  const parts=reports.map(r=>{
    const findings=r.findings.map((f,i)=>{
      const frame=f.severity==='error'?' · [帧](frames/'+r.clip+'_'+i+'.png)':'';
      return '- '+f.severity+' / '+f.rule+' / '+f.bone+' @ '+f.time.toFixed(4)+'s · '+Number(f.value).toFixed(3)+' / '+JSON.stringify(f.limit)+frame+(f.reason?' · '+f.reason:'');
    });
    return '## '+r.clip+'\n\n'+r.samples+' 个采样 · 错误 '+r.errors+' · 警告 '+r.warnings+' · [角度曲线]('+r.clip+'.svg)\n\n'+findings.join('\n');
  });
  writeFileSync(join(output,'REPORT.md'),'# '+id+' 自动 QA '+QA_VERSION+'\n\n错误总数 '+total+'。\n\n'+parts.join('\n\n').trimEnd()+'\n');
  console.log(id+': '+reports.length+' clips, '+total+' errors');
  for (const r of reports.filter(r=>r.errors)) console.log(r.clip,r.findings.map(f=>f.rule+'/'+f.bone+'='+f.value.toFixed(2)).join(' '));
  return total;
}

if(process.argv[1] && fileURLToPath(import.meta.url)===process.argv[1]) {
  if (process.argv.length<3) throw new Error('Usage: node tools/qa/check.mjs <id> [id ...]');
  process.exitCode=process.argv.slice(2).map(checkCharacter).some(n=>n>0)?1:0;
}
