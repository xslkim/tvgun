import sys
from PIL import Image, ImageDraw
sys.path.insert(0,'pipeline/split')
from prepare import isolate, pack

sprite = Image.new('RGBA',(96,96),'#ff00ff')
draw = ImageDraw.Draw(sprite)
draw.rectangle((20,18,75,77),fill='#031627')
draw.ellipse((38,35,54,52),fill='#ff00ff')
cut = isolate(sprite,(0,0,96,96),[255,0,255])
assert cut.size==(56,60),cut.size
assert cut.getpixel((25,25))==(255,0,255,255)
atlas, rects = pack({'part':cut})
assert atlas.crop((4,4,60,64)).tobytes()==cut.tobytes()
print('PASS keyed RGB flood-fill preserves enclosed highlights and atlas texels')
