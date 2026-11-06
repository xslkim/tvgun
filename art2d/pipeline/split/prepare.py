"""Crop and pack a reviewed image sheet. Anchors in the layout refer to trimmed sprites."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageChops, ImageCms, ImageDraw, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parents[2]
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def isolate(image, box, background, polygon=None, subtract=False, with_bounds=False):
    left, top, right, bottom = box
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ValueError(f'Crop {box} is outside image bounds {image.size}')
    region = image.crop(box)
    if background:
        # Flood-fill from the edges so white highlights inside the art survive.
        color = tuple(background) + (255,)
        marker = (17, 249, 12, 0)
        for x, y in [(x, 0) for x in range(region.width)] + [
                (x, region.height - 1) for x in range(region.width)] + [
                (0, y) for y in range(region.height)] + [
                (region.width - 1, y) for y in range(region.height)]:
            if sum(abs(a - b) for a, b in zip(region.getpixel((x, y)), color)) < 70:
                ImageDraw.floodfill(region, (x, y), marker, thresh=64)
    if polygon:
        mask = Image.new('L', region.size, 255 if subtract else 0)
        ImageDraw.Draw(mask).polygon([(x-box[0], y-box[1]) for x,y in polygon], fill=0 if subtract else 255)
        region.putalpha(ImageChops.multiply(region.getchannel('A'), mask))
    bbox = region.getchannel('A').point(lambda a: 255 if a > 30 else 0).getbbox()
    if bbox is None:
        raise ValueError(f'No opaque content in {box}')
    if not background and region.getchannel('A').getextrema() == (255, 255):
        raise ValueError(f'No alpha in {box}. Record an explicit background key or use an alpha source.')
    trimmed = region.crop(bbox)
    trimmed.putalpha(trimmed.getchannel('A').point(lambda a: 0 if a < 20 else a))
    return (trimmed, bbox) if with_bounds else trimmed


def pack(sprites, max_size=2048, padding=4):
    atlas = Image.new('RGBA', (max_size, max_size))
    rects = {}
    x = y = padding
    row_height = 0
    used_width = 0
    for part, sprite in sorted(sprites.items(), key=lambda item: (-item[1].height, item[0])):
        w, h = sprite.size
        if w + padding * 2 > max_size:
            raise ValueError(f'Sprite {part} is wider than atlas')
        if x + w + padding > max_size:
            x, y = padding, y + row_height + padding * 2
            row_height = 0
        if y + h + padding > max_size:
            raise ValueError('Atlas exceeds 2048px; split into pages')
        atlas.paste(sprite, (x, y))
        # Extrude one texel on each edge, then leave transparent separation.
        atlas.paste(sprite.crop((0, 0, w, 1)), (x, y - 1))
        atlas.paste(sprite.crop((0, h - 1, w, h)), (x, y + h))
        atlas.paste(sprite.crop((0, 0, 1, h)), (x - 1, y))
        atlas.paste(sprite.crop((w - 1, 0, w, h)), (x + w, y))
        for dx, sx in [(-1, 0), (w, w - 1)]:
            for dy, sy in [(-1, 0), (h, h - 1)]:
                atlas.putpixel((x + dx, y + dy), sprite.getpixel((sx, sy)))
        rects[part] = [x, y, w, h]
        x += w + padding * 2
        row_height = max(row_height, h)
        used_width = max(used_width, x - padding)
    return atlas.crop((0, 0, used_width, y + row_height + padding)), rects


def build(folder):
    layout = json.loads((folder / 'concept/layout.json').read_text(encoding='utf-8-sig'))
    identifier = folder.name
    if not re.fullmatch('[a-z][a-z0-9_]+', identifier):
        raise ValueError('Asset identifier must use lowercase snake case')
    raw = folder / 'concept/raw.png'
    image = Image.open(raw).convert('RGBA')
    source_profile = image.info.get('icc_profile')
    if source_profile:
        from io import BytesIO
        image = ImageCms.profileToProfile(image, BytesIO(source_profile), ImageCms.createProfile('sRGB'))
    for subdir in ['parts', 'export']:
        (folder / subdir).mkdir(exist_ok=True)
    sprites = {}
    anchors = {}
    for name, spec in layout['parts'].items():
        if not re.fullmatch('[a-z][a-z0-9_]+', name):
            raise ValueError(f'Invalid part name {name}')
        sprite = isolate(image, spec['crop'], layout.get('background'), spec.get('polygon'), spec.get('subtract',False))
        if spec.get('mirror'):
            sprite = ImageOps.mirror(sprite)
        if spec.get('rotate'):
            sprite = sprite.rotate(spec['rotate'], resample=Image.Resampling.BICUBIC, expand=True)
            sprite = sprite.crop(sprite.getchannel('A').getbbox())
        if 'brightness' in spec:
            sprite = ImageEnhance.Brightness(sprite).enhance(spec['brightness'])
        if min(sprite.size) < 24:
            raise ValueError(f'{name} below 24px min: {sprite.size}')
        anchor = spec['anchor']
        if not all(0 <= point <= 1 for point in anchor):
            raise ValueError(f'Invalid anchor for {name}')
        target = folder / 'parts' / f'{identifier}_{name}_default.png'
        sprite.save(target, icc_profile=SRGB)
        sprites[name] = sprite
        anchors[name] = dict(uv=anchor, pixels=[round(anchor[i] * sprite.size[i], 2) for i in range(2)],
                             image=target.name, source_crop=spec['crop'], size=sprite.size)
    atlas, rects = pack(sprites)
    atlas.save(folder / 'export/atlas.png', icc_profile=SRGB)
    write_json(folder / 'parts/anchors.json', anchors)
    write_json(folder / 'export/atlas.json', dict(image='atlas.png', size=atlas.size, regions=rects))
    reference = isolate(image, layout['reference'], layout.get('background'))
    reference.save(folder / 'concept/master.png', icc_profile=SRGB)
    manifest_path = folder / 'concept/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    manifest.update(original='raw.png', reference='master.png', dimensions=list(image.size),
                    sha256=hashlib.sha256(raw.read_bytes()).hexdigest(), layout='layout.json')
    write_json(manifest_path, manifest)
    print(f'{identifier}: {len(sprites)} parts, atlas {atlas.size}, source {image.size}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('character', nargs='+')
    for character in parser.parse_args().character:
        build(ROOT / 'assets' / character)
