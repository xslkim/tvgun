import {deg, rotate, wrap, world, solve2} from './runtime.mjs';

export function makeRig(spec, anchors, atlas) {
  const bones = [];
  const positions = {};
  const legs = [];
  const limits = [];
  const add = (id, parent, x, y, a, length = 0, elastic = false) => {
    const p = positions[parent];
    if (p && x === null) {
      const [dx, dy] = rotate(p.length, 0, p.a);
      x = p.x + dx;
      y = p.y + dy;
    }
    if (positions[id] || (parent && !p) || ![x,y,a,length].every(Number.isFinite)) {
      throw new Error('Invalid or out-of-order bone ' + id);
    }
    positions[id] = {x, y, a, length};
    const [lx, ly] = p ? rotate(x - p.x, y - p.y, -p.a) : [x,y];
    bones.push({id,parent,x:lx,y:ly,a:p ? wrap(a-p.a) : a,length,elastic});
  };
  add('root',null,0,0,0);
  add('hip','root',...spec.hip,0);
  for (const entry of spec.bones) add(...entry);
  for (const entry of spec.legs ?? []) {
    const {suffix, origin, foot, lengths, sign, phase} = entry;
    const upper = 'upper_leg_' + suffix, lower = 'lower_leg_' + suffix, end = 'foot_' + suffix;
    const [l1,l2] = lengths;
    const [dx,dy] = [foot[0]-origin[0],foot[1]-origin[1]];
    const distance = Math.hypot(dx,dy);
    if (distance >= l1 + l2 || distance <= Math.abs(l1-l2)) throw new Error('Unreachable bind foot ' + suffix);
    const knee = sign * Math.acos((distance**2-l1**2-l2**2)/(2*l1*l2));
    const angle = Math.atan2(dy,dx) - Math.atan2(l2*Math.sin(knee),l1+l2*Math.cos(knee));
    add(upper, entry.parent ?? 'hip', ...origin, deg(angle), l1);
    add(lower, upper, null,null, deg(angle+knee),l2);
    add(end, lower, null,null, 0, entry.sole?.[0] ?? 25);
    limits.push({id:upper,parent:entry.parent ?? 'hip',min:-105,max:105});
    limits.push({id:lower,parent:upper,min:sign < 0 ? -145 : 0,max:sign < 0 ? 0 : 145,bend_sign:sign,chain:true});
    limits.push({id:end,parent:lower,min:-115,max:115});
    legs.push({suffix,chain:[upper,lower,end,sign],foot,phase,sole:entry.sole ?? [25,-foot[1]]});
  }
  for (const [id,min,max,bend_sign] of spec.limits ?? []) {
    limits.push({id,parent:bones.find(b=>b.id===id).parent,min,max,bend_sign});
  }
  const rig = {version:1,id:spec.id,label:spec.label,prototype:spec.prototype,height:spec.height,
    ground:0,bones,legs,limits,atlas:atlas.image,attachments:[],elastic:spec.prototype==='blob'};
  const w = world(rig);
  for (const [bone,part,width,height,imageAxis,variants,tip] of spec.attachments) {
    const item = (name, size) => {
      const uv = anchors[name]?.uv;
      const src = atlas.regions[name];
      if (!uv || !src || !positions[bone] || !size.every(x=>x>0)) throw new Error('Invalid attachment ' + name);
      return {part:name,rect:src,size,pivot:uv};
    };
    const slot = {bone, a:-imageAxis, ...item(part,[width,height])};
    if (variants) {
      slot.variants = {};
      for (const [id, v] of Object.entries(variants)) {
        slot.variants[id] = item(v.part, v.size);
        if (v.imageAxis !== undefined) slot.variants[id].a = -v.imageAxis;
      }
    }
    if (spec.prototype === 'blob' && part === 'jelly') slot.mesh = makeMesh(slot,w,'jelly_top','jelly');
    if (spec.prototype === 'humanoid' && part === 'body') slot.mesh = makeMesh(slot,w,'chest','torso');
    if (tip) slot.mesh = makeMesh(slot,w,tip,'chain');
    rig.attachments.push(slot);
  }
  return rig;
}

function makeMesh(slot, bind, tip, mode) {
  const columns = 8, rows = 8, vertices = [], triangles = [];
  for (let j=0; j<=rows; j++) {
    for (let i=0; i<=columns; i++) {
      const u=i/columns,v=j/rows;
      const root=bind[slot.bone];
      const localX=(u-slot.pivot[0])*slot.size[0];
      const localY=(slot.pivot[1]-v)*slot.size[1];
      const [dx,dy]=rotate(localX,localY,root.a+slot.a);
      const x=root.x+dx,y=root.y+dy;
      const along=rotate(dx,dy,-root.a)[0];
      const input=mode==='jelly'?(1-v)**.35:mode==='torso'?(.77-v)/.46:along/rootLength(bind,slot.bone,tip)-.25;
      const k=Math.max(0,Math.min(1,input));
      const weights = [[slot.bone,1-k],[tip,k]].map(([id,weight])=>[
        id,weight,...rotate(x-bind[id].x,y-bind[id].y,-bind[id].a),
      ]);
      vertices.push({uv:[u,v],weights});
      if (i && j) {
        const d=j*(columns+1)+i, b=d-columns-1;
        triangles.push([b-1,b,d],[b-1,d,d-1]);
      }
    }
  }
  return {vertices,triangles};
}

export function lockFeet(rig, pose, targets) {
  for (const leg of rig.legs) {
    const [x,y,a=0] = targets[leg.suffix];
    solve2(rig,pose,leg.chain,x,y,a);
  }
}


function rootLength(w,root,tip) {
  return Math.hypot(w[tip].x-w[root].x,w[tip].y-w[root].y);
}
