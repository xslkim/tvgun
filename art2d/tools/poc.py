from json import loads
from pathlib import Path
from PIL import Image, ImageDraw

source = Path('demos/poc/world.json')
data = loads(source.read_text())
images = []
for frame in data['frames']:
    im = Image.new('RGB', (240, 220), '#111f30')
    d = ImageDraw.Draw(im)
    d.line((0, 194, 240, 194), fill='#537386')
    for bone in data['rig']['bones']:
        w = frame[bone['id']]
        x, y = 115 + w['x'], 194 - w['y']
        if bone.get('parent'):
            p = frame[bone['parent']]
            d.line((115 + p['x'], 194 - p['y'], x, y), fill='#59d7bb', width=4)
        d.ellipse((x-4, y-4, x+4, y+4), fill='#ffd184')
    images.append(im)
images[0].save(source.with_name('idle.gif'), save_all=True, append_images=images[1:], duration=33, loop=0)
