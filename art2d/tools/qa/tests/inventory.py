"""Validate the delivery inventory, traceability, reports, and preview files."""
from hashlib import sha256
import csv
import json
from pathlib import Path
import re
from urllib.parse import unquote

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def verify_courier_art(folder, rig):
    order = {slot['part']: index for index, slot in enumerate(rig['attachments'])}
    assert order['upper_arm_r'] < order['body'] < order['upper_arm_l']
    assert order['thigh_r'] < order['thigh_l'] < order['body']
    assert order['sword'] < order['fist_r'] < order['body']
    assert order['body'] < order['scarf_collar'] < order['head']

    backgrounds = {(23, 40, 56), (35, 56, 74), (103, 131, 141)}
    with Image.open(folder/'preview/master_vs_bind.png') as comparison:
        width = comparison.width // 2
        panels = [comparison.crop((x, 26, x+width, comparison.height)).convert('RGB')
                  for x in (0, width)]
    reference, bind = [list(panel.get_flattened_data()) for panel in panels]
    pairs = [(a not in backgrounds, b not in backgrounds) for a,b in zip(reference, bind)]
    overlap = sum(a and b for a,b in pairs) / sum(a or b for a,b in pairs)
    assert overlap >= .90, f'Courier aligned silhouette overlap: {overlap:.3f}'

    def scarf_pixels(pixels):
        return sum(r > 1.6*g and g > 1.2*b for r,g,b in pixels)

    assert scarf_pixels(bind) >= .85*scarf_pixels(reference) > 0
    print(f'PASS courier reference layers, scarf, and silhouette ({overlap:.1%} overlap)')


def verify_character(entry):
    export = ROOT / entry['path'].lstrip('/')
    folder = export.parents[1]
    manifest = read(folder / 'concept/manifest.json')
    assert sha256((folder/'concept/raw.png').read_bytes()).hexdigest() == manifest['sha256'], entry
    data = read(export)
    rig, clips = data['rig'], data['clips']
    atlas = read(export.with_name('atlas.json'))
    with Image.open(export.with_name(rig['atlas'])) as art:
        assert art.mode == 'RGBA' and tuple(atlas['size']) == art.size
        for x,y,w,h in atlas['regions'].values():
            assert 0 <= x < x+w <= art.width and 0 <= y < y+h <= art.height
    for info in read(folder/'parts/anchors.json').values():
        with Image.open(folder/'parts'/info['image']) as part:
            assert part.mode == 'RGBA' and part.size == tuple(info['size'])
    report = read(folder/'qa/report.json')
    assert report['total'] == 0 and {r['clip'] for r in report['reports']} == set(clips), entry
    for name, relative in clips.items():
        clip = read(export.with_name('character.json').parent / relative)
        assert clip['name'] == name and clip['bake_hz'] == 120
        for suffix in ['.gif','_sheet.png']:
            with Image.open(folder/'preview'/(name+suffix)) as image:
                image.verify()
        assert (folder/'qa'/(name+'.svg')).is_file()
    if entry['id'] == 'courier':
        verify_courier_art(folder, rig)
    if not entry.get('validation'):
        with (folder/'qa/history.csv').open(encoding='utf-8-sig',newline='') as handle:
            scores = {r['clip']:r for r in csv.DictReader(handle) if r['iteration']=='4'}
        assert set(scores)==set(clips)
        for name, score in scores.items():
            ratings=[int(score[k]) for k in ('pose','timing','flow','overlap','character','assembly')]
            assert min(ratings) >= 3 and sum(ratings) >= 24, (name,score)
            assert (folder/'qa'/score['evidence']).is_file()
    return len(clips), sum(r['samples'] for r in report['reports'])


def local_links():
    issues=[]
    for path in ROOT.rglob('*.md'):
        if 'archive' in path.relative_to(ROOT).parts:
            continue
        for target in re.findall(r'\]\(([^)\s]+)\)',path.read_text(encoding='utf-8-sig')):
            value=unquote(target.split('#')[0])
            if value and not re.match(r'^\w+://',value) and not (path.parent/value).exists():
                issues.append((path.relative_to(ROOT).as_posix(),value))
    return issues


def main():
    roster={entry['id']:entry for entry in read(ROOT/'demos/characters.json')}
    expected={
        'courier':('humanoid',14), 'hound':('quadruped',8), 'moth':('winged',7),
        'scarab':('multileg',7), 'jelly':('blob',11),
    }
    demo_count, samples=0,0
    for ident, (prototype, count) in expected.items():
        n,m=verify_character(roster[ident])
        assert n == count and roster[ident]['prototype'] == prototype, ident
        demo_count += n
        samples += m
    extra,_=verify_character(roster['ember'])
    assert demo_count==47 and extra==11
    assert not (missing:=local_links()), missing
    print(f'PASS 5 demos, {demo_count} clips, {samples} samples, {extra} validation clips')
    print('PASS all raw hashes, part/atlas images, per-clip previews, QA/visual coverage, local links')


if __name__=='__main__':
    main()
