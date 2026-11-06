import {sample,world,transform,skinVertex,blend,smooth,clamp,rad} from '/pipeline/rig/runtime.mjs';

const $=id=>document.getElementById(id);
const stage=$('stage'),ctx=stage.getContext('2d');
let character, rig, atlas, clips={}, clip, time=0, moving=0, playing=true, last, transition, sequence;
let selection=0;
const PROTOTYPES={humanoid:'人形 / HUMANOID',quadruped:'四足 / QUADRUPED',winged:'飞行 / WINGED',multileg:'多足 / MULTI-LEG',blob:'软体 / SOFT BODY'};
const data=async url=>{
  const response=await fetch(url);
  if(!response.ok) throw new Error(url+' HTTP '+response.status);
  return response.json();
};
const bitmap=async url=>{
  const image=new Image();
  image.src=url;
  await image.decode();
  return image;
};

async function selectCharacter(entry) {
  const attempt=++selection;
  $('status').textContent='加载 '+entry.label+'…';
  const url=new URL(entry.path,location);
  const asset=await data(url);
  const results=await Promise.all([
    bitmap(new URL(asset.rig.atlas,url)),
    ...Object.values(asset.clips).map(path=>data(new URL(path,url))),
  ]);
  if(attempt!==selection) return;
  [atlas]=results;
  character=entry;
  rig=asset.rig;
  clips=Object.fromEntries(results.slice(1).map(c=>[c.name,c]));
  $('name').textContent=entry.label;
  $('prototype').textContent=PROTOTYPES[rig.prototype]+' · '+rig.bones.length+' BONES';
  $('report').href='/assets/'+entry.id+'/qa/REPORT.md';
  $('skinRow').hidden=rig.prototype!=='humanoid';
  $('skin').value='';
  for(const button of $('roster').children) button.setAttribute('aria-pressed',button.dataset.id===entry.id);
  $('clips').replaceChildren(...Object.values(clips).map(c=>{
    const b=document.createElement('button');
    b.className='clip';
    b.dataset.clip=c.name;
    b.append(c.name);
    const tag=document.createElement('span');
    tag.textContent=c.meta.loop?'↻':c.duration.toFixed(2)+'s';
    b.append(tag);
    b.onclick=()=>{sequence=undefined;setClip(c.name,true);};
    return b;
  }));
  sequence=undefined;
  setClip(clips.idle ? 'idle' : Object.keys(clips)[0],true);
}

function setClip(name,reset=false) {
  if(!clips[name]) return;
  transition=reset||!clip?undefined:{pose:currentPose(),age:0,duration:.15};
  if(reset) moving=0;
  clip=clips[name];
  time=0;
  playing=true;
  $('time').max=clip.duration;
  $('clipBadge').textContent=clip.meta.loop?'LOOP':'ONE SHOT';
  $('status').textContent=clip.events.length?clip.events.map(e=>e.id+' '+e.time.toFixed(2)+'s').join('  ·  '):'当前动作无事件';
  for(const button of $('clips').children) button.setAttribute('aria-pressed',button.dataset.clip===name);
  transport();
}
function currentPose() {
  const pose=sample(clip,time,false);
  if (!transition) return pose;
  return blend(transition.pose,pose,smooth(clamp(transition.age/transition.duration,0,1)));
}

function transport() {
  $('play').textContent=playing?'❚❚':'▶';
  $('play').setAttribute('aria-label',playing?'暂停':'播放');
  $('time').value=time;
  $('clock').textContent=time.toFixed(3)+' / '+clip.duration.toFixed(2)+'s';
  const ev=clip.events.find(e=>Math.abs(time-e.time)<.09);
  $('event').textContent=ev?ev.id+(ev.point?' / '+ev.point:''):'';
}

function texturedTriangle(slot,uv,points) {
  const [sx,sy,sw,sh]=slot.rect;
  const [a,b,c]=uv.map(([x,y])=>[x*sw,y*sh]);
  const [p,q,r]=points;
  const u=[b[0]-a[0],b[1]-a[1]], v=[c[0]-a[0],c[1]-a[1]];
  const det=u[0]*v[1]-u[1]*v[0];
  const mx=(x,y)=>[(v[1]*x-u[1]*y)/det,(-v[0]*x+u[0]*y)/det];
  const [m1,m3]=mx(q[0]-p[0],r[0]-p[0]), [m2,m4]=mx(q[1]-p[1],r[1]-p[1]);
  const cx=(p[0]+q[0]+r[0])/3,cy=(p[1]+q[1]+r[1])/3;
  ctx.save();
  ctx.beginPath();
  for(const [x,y] of points) {
    const mag=Math.hypot(x-cx,y-cy)||1;
    ctx.lineTo(x+.6*(x-cx)/mag,y+.6*(y-cy)/mag);
  }
  ctx.closePath(); ctx.clip();
  ctx.transform(m1,m2,m3,m4,p[0]-m1*a[0]-m3*a[1],p[1]-m2*a[0]-m4*a[1]);
  ctx.drawImage(atlas,sx,sy,sw,sh,0,0,sw,sh);
  ctx.restore();
}

function render() {
  const h=stage.height,w=stage.width;
  const pose=currentPose(), positions=world(rig,pose);
  const s=Math.min((rig.prototype==='humanoid'?360:300)/rig.height,1.05);
  const dx=($('motion').checked?moving:0)*s;
  const camera=clip.meta.root_motion_mode==='root'?positions.root.x*s:0;
  const cx=w*.5-camera,cy=h-56;
  const xy=([x,y])=>[cx+s*x,cy-s*y];
  ctx.clearRect(0,0,w,h);
  ctx.fillStyle='#0f1a26';ctx.fillRect(0,0,w,h);
  const grid=40*s;
  const gridOffset=((cx-dx)%grid+grid)%grid;
  ctx.strokeStyle='#213448';ctx.lineWidth=1;ctx.beginPath();
  for(let x=gridOffset;x<w;x+=grid){ctx.moveTo(x,0);ctx.lineTo(x,h);}
  for(let y=cy%grid;y<h;y+=grid){ctx.moveTo(0,y);ctx.lineTo(w,y);}
  ctx.stroke();
  ctx.strokeStyle='#6a8794';ctx.beginPath();ctx.moveTo(0,cy);ctx.lineTo(w,cy);ctx.stroke();
  ctx.fillStyle='#8da6ae';ctx.font='12px monospace';ctx.fillText('GROUND / Y = 0',14,cy+22);
  const skin=$('skin').value;
  for(const slot of rig.attachments) {
    const p=positions[slot.bone];
    if(skin==='palm' && slot.bone==='weapon') continue;
    if(slot.mesh) {
      const {vertices,triangles}=slot.mesh;
      const points=vertices.map(v=>xy(skinVertex(v,positions)));
      for(const tri of triangles) texturedTriangle(slot,tri.map(i=>vertices[i].uv),tri.map(i=>points[i]));
      if($('mesh').checked) {
        ctx.strokeStyle='#72e5db90';
        ctx.beginPath();
        for(const [a,b,c] of triangles){ctx.moveTo(...points[a]);ctx.lineTo(...points[b]);ctx.lineTo(...points[c]);ctx.closePath();}
        ctx.stroke();
      }
      continue;
    }
    const {rect,size,pivot,a=slot.a}=slot.variants?.[skin]??slot;
    ctx.save();
    ctx.translate(...xy([p.x,p.y]));
    ctx.rotate(-rad(p.a+a));
    ctx.scale(s*p.sx,s*p.sy);
    const box=[-pivot[0]*size[0],-pivot[1]*size[1],...size];
    ctx.drawImage(atlas,...rect,...box);
    if($('mesh').checked) {ctx.strokeStyle='#76e2c399';ctx.lineWidth=1/s;ctx.strokeRect(...box);}
    ctx.restore();
  }
  if($('bones').checked) {
    ctx.lineWidth=2;
    for(const b of rig.bones) {
      const p=positions[b.id], start=xy([p.x,p.y]);
      const end=xy(transform(p,[b.length,0]));
      ctx.beginPath();ctx.moveTo(...start);ctx.lineTo(...end);ctx.strokeStyle='#76e2c3';ctx.stroke();
      ctx.beginPath();ctx.arc(...start,3,0,2*Math.PI);ctx.fillStyle='#f5c078';ctx.fill();
    }
  }
}
function tick(now) {
  const dt=clamp((now-(last??now))/1000,0,.08)*Number($('rate').value);
  last=now;
  if(clip) {
    if(playing) {
      time+=dt;
      moving=(moving+dt*clip.meta.locomotion_speed)%40;
      if(transition) {
        transition.age+=dt;
        if(transition.age>=transition.duration) transition=undefined;
      }
      if(sequence) {
        sequence.elapsed+=dt;
        if(sequence.phase===0 && sequence.elapsed>=clip.duration) {
          sequence.phase=1;setClip('attack_light');
        } else if(sequence.phase===1 && time>=clip.duration) {
          const move=sequence.move; sequence=undefined;setClip(move);
        }
      }
      if(time>=clip.duration) {
        if(clip.meta.loop) time%=clip.duration;
        else {time=clip.duration;playing=false;}
      }
    }
    render();transport();
  }
  requestAnimationFrame(tick);
}

function seek(t){
  if(!clip) return;
  sequence=transition=undefined;playing=false;
  time=clamp(t,0,clip.duration);
  moving=time*clip.meta.locomotion_speed;
  transport();render();
}
$('time').oninput=e=>seek(Number(e.target.value));
$('prev').onclick=()=>seek(Math.max(0,Math.ceil(time*30-1e-6)-1)/30);
$('next').onclick=()=>seek((Math.floor(time*30+1e-6)+1)/30);
$('play').onclick=()=>{
  if(!clip) return;
  if(!playing && time>=clip.duration) time=0;
  playing=!playing;
  transport();
};
$('sequence').onclick=()=>{
  const move=clips.walk?'walk':clips.fly?'fly':'run';
  if(!clips[move] || !clips.attack_light) return;
  setClip(move,true);
  sequence={move,phase:0,elapsed:0};
};
function showError(error) { $('status').textContent='加载失败 · '+error.message; }
async function init() {
  const roster=await data('/demos/characters.json');
  for(const c of roster) {
    const b=document.createElement('button');
    b.className='character';
    b.dataset.id=c.id;
    const label=document.createElement('strong'), kind=document.createElement('small');
    label.textContent=c.label;kind.textContent=PROTOTYPES[c.prototype];
    b.append(label,kind);
    b.onclick=()=>selectCharacter(c).catch(showError);
    $('roster').append(b);
  }
  await selectCharacter(roster[0]);
  requestAnimationFrame(tick);
}
init().catch(showError);
