import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def triangle(target, sprite, uv, points):
    a, b, c = points
    ux, uy = b[0]-a[0], b[1]-a[1]
    vx, vy = c[0]-a[0], c[1]-a[1]
    det = ux*vy-uy*vx
    if abs(det) < 1e-6:
        return
    left, top = math.floor(min(p[0] for p in points)), math.floor(min(p[1] for p in points))
    right, bottom = math.ceil(max(p[0] for p in points)), math.ceil(max(p[1] for p in points))
    if left >= right or top >= bottom:
        return
    dest = [(x-left, y-top) for x,y in points]
    coeffs = []
    for dim, size in enumerate(sprite.size):
        du = (uv[1][dim]-uv[0][dim])*size
        dv = (uv[2][dim]-uv[0][dim])*size
        x, y = (vy*du-uy*dv)/det, (ux*dv-vx*du)/det
        coeffs.extend([x,y,uv[0][dim]*size-x*dest[0][0]-y*dest[0][1]])
    tile = sprite.transform((right-left,bottom-top),Image.Transform.AFFINE,coeffs,Image.Resampling.BICUBIC)
    mask = Image.new('L',tile.size)
    ImageDraw.Draw(mask).polygon(dest,fill=255)
    tile.putalpha(Image.composite(tile.getchannel('A'),Image.new('L',tile.size),mask))
    target.alpha_composite(tile,(left,top))


class Preview:
    def __init__(self, rig, atlas):
        self.rig = rig
        self.atlas = atlas
        self.sprites = {}
        self.size = (420,330)
        h = rig['height']
        self.scale = min(230/h, .58) if rig['prototype'] in ('humanoid','blob') else min(174/h,.48)
        self.origin = (self.size[0]//2, self.size[1]-42)

    def xy(self, x, y):
        return (self.origin[0]+x*self.scale,self.origin[1]-y*self.scale)

    def art(self, shot):
        layer = Image.new('RGBA',self.size)
        for i,slot in enumerate(shot.get('attachments', self.rig['attachments'])):
            if slot is None:
                continue
            rect = tuple(slot['rect'])
            if rect not in self.sprites:
                x,y,w,h = rect
                self.sprites[rect] = self.atlas.crop((x,y,x+w,y+h))
            sprite = self.sprites[rect]
            if slot.get('mesh'):
                vertices=slot['mesh']['vertices']
                points=[self.xy(*p) for p in shot['meshes'][i]]
                for tri in slot['mesh']['triangles']:
                    triangle(layer,sprite,[vertices[k]['uv'] for k in tri],[points[k] for k in tri])
                continue
            pose=shot['w'][slot['bone']]
            x,y=self.xy(pose['x'],pose['y'])
            a=math.radians(-(pose['a']+slot['a']))
            co,si=math.cos(a),math.sin(a)
            w,h=slot['size']
            sw,sh=sprite.size
            sx,sy=sw/(w*self.scale*pose['sx']),sh/(h*self.scale*pose['sy'])
            u,v=slot['pivot']
            coeffs=(co*sx,si*sx,u*sw-(co*x+si*y)*sx,-si*sy,co*sy,v*sh+(si*x-co*y)*sy)
            radius=math.ceil(math.hypot(w,h)*self.scale*max(abs(pose['sx']),abs(pose['sy'])))
            left,top=max(0,int(x)-radius),max(0,int(y)-radius)
            right,bottom=min(self.size[0],int(x)+radius+1),min(self.size[1],int(y)+radius+1)
            if left>=right or top>=bottom:
                continue
            a,b,c,d,e,f=coeffs
            tile=sprite.transform((right-left,bottom-top),Image.Transform.AFFINE,
                                  (a,b,c+a*left+b*top,d,e,f+d*left+e*top),Image.Resampling.BICUBIC)
            layer.alpha_composite(tile,(left,top))
        return layer

    def render(self, shot, bones=False, onions=(), art=None):
        frame = Image.new('RGBA',self.size,'#172838')
        d=ImageDraw.Draw(frame)
        for x in range(self.origin[0]%28,self.size[0],28):
            d.line((x,0,x,self.size[1]),fill='#23384a')
        for y in range(self.origin[1]%28,self.size[1],28):
            d.line((0,y,self.size[0],y),fill='#23384a')
        d.line((0,self.origin[1],self.size[0],self.origin[1]),fill='#67838d',width=2)
        for ghost,color in zip(onions,['#ef8583','#74bbff']):
            silhouette=self.art(ghost)
            tint=Image.new('RGBA',self.size,color)
            tint.putalpha(silhouette.getchannel('A').point(lambda a:int(a*.3)))
            frame.alpha_composite(tint)
        frame.alpha_composite(self.art(shot) if art is None else art)
        d=ImageDraw.Draw(frame)
        if bones:
            for bone in self.rig['bones']:
                p=shot['w'][bone['id']]
                x,y=self.xy(p['x'],p['y'])
                if bone['parent']:
                    q=shot['w'][bone['parent']]
                    d.line((*self.xy(q['x'],q['y']),x,y),fill='#5cf0ce',width=2)
                d.ellipse((x-2,y-2,x+2,y+2),fill='#ffe08c')
        d.text((10,10),shot.get('caption') or f"{shot['time']:.2f}s",fill='#e6f5f3')
        return frame.convert('RGB')

    def sheet(self, images, dest, cols=4):
        w,h=self.size
        rows=(len(images)+cols-1)//cols
        canvas=Image.new('RGB',(w*cols,h*rows),'#102031')
        for i,im in enumerate(images):
            canvas.paste(im,((i%cols)*w,(i//cols)*h))
        canvas.save(dest,optimize=True)


def opaque_bounds(image):
    return image.getchannel('A').point(lambda a: 255 if a >= 100 else 0).getbbox()


def aligned_reference(master, bind):
    source = master.crop(opaque_bounds(master))
    left, top, right, bottom = opaque_bounds(bind)
    height = bottom - top
    width = round(source.width * height / source.height)
    resized = source.resize((width, height), Image.Resampling.LANCZOS)
    result = Image.new('RGBA', bind.size)
    result.alpha_composite(resized, ((left + right - width) // 2, top))
    return result


def gif(images,fps,loop,path):
    durations=[round(100*(i+1)/fps)*10-round(100*i/fps)*10 for i in range(len(images))]
    images[0].save(path,save_all=True,append_images=images[1:],duration=durations,
                   optimize=True,**({'loop':0} if loop else {}))


def main():
    data=json.load(sys.stdin)
    root=Path(data['path'])
    preview=root/'preview'
    issue_frames=root/'qa/frames'
    issue_frames.mkdir(parents=True,exist_ok=True)
    renderer=Preview(data['rig'],Image.open(root/'export/atlas.png').convert('RGBA'))
    bind = data['bind']
    art = renderer.art(bind)
    rendered_bind = renderer.render(bind, art=art)
    rendered_bind.save(preview/'bind.png')
    master = Image.open(root/'concept/master.png').convert('RGBA')
    reference = renderer.render({**bind, 'caption': 'AI master reference'}, art=aligned_reference(master, art))
    renderer.sheet([reference, rendered_bind], preview/'master_vs_bind.png', 2)
    if data['limits']:
        renderer.sheet([renderer.render(x,True) for x in data['limits']],preview/'joint_extremes.png')
    metrics_path = preview/'raster_metrics.json'
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    for shot in data['shots']:
        name=shot['name']
        film=shot['film']
        art = [renderer.art(f) for f in film]
        bottoms = [opaque_bounds(layer) for layer in art]
        offsets = [(bbox[3]-renderer.origin[1])/renderer.scale for bbox in bottoms if bbox]
        metrics[name] = {'frames': len(art), 'max_below_ground': round(max(offsets, default=0), 2),
                         'terminal_below_ground': round(offsets[-1],2) if offsets else None}
        gif([renderer.render(f,art=a) for f,a in zip(film,art)],shot['fps'],shot['loop'],preview/(name+'.gif'))
        renderer.sheet([renderer.render(f) for f in shot['keys']],preview/(name+'_sheet.png'))
        for f in shot['faults']:
            renderer.render(f['frame'],True).save(issue_frames/(f['name']+'.png'))
        if data['debug']:
            gif([renderer.render(f,True,art=a) for f,a in zip(film,art)],shot['fps'],shot['loop'],preview/(name+'_bones.gif'))
            step=max(1,round(shot['fps']/10))
            def neighbor(i):
                return film[i%len(film)] if shot['loop'] else film[max(0,min(len(film)-1,i))]
            renderer.sheet([renderer.render(f,onions=(neighbor(round(f['time']*shot['fps'])-step),
                neighbor(round(f['time']*shot['fps'])+step))) for f in shot['keys']],preview/(name+'_onion.png'))
        print(data['rig']['id']+'/'+name,flush=True)
    metrics_path.write_text(json.dumps(metrics,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
