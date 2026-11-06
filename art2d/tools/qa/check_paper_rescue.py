"""Check the resident animation's visible attached ink at its game display size.

Run from the workspace with the GunForge art Python environment and Node on PATH.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import binary_opening, distance_transform_edt

from render import Preview


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = '''
import {read} from './pipeline/export/build.mjs';
import {sample, world, attachmentAt} from './pipeline/rig/runtime.mjs';
const path = process.argv[1];
const {rig, clips} = read(path + '/character.json');
const frames = [];
for (const name of ['struggle', 'rescued_bounce']) {
  const clip = read(path + '/' + clips[name]);
  for (let i = 0; i <= Math.round(clip.duration * 30); i++) {
    const time = i / 30;
    const attachments = rig.attachments.map(slot => attachmentAt(slot, clip, time));
    if (attachments.some(slot => slot?.part === 'rescue_ink')) {
      frames.push({name, time, w:world(rig, sample(clip, time, false)), attachments});
    }
  }
}
console.log(JSON.stringify({rig, frames}));
'''


def candidate_sprites(directory, reference, slot):
    """Keep the candidate's shape and aspect ratio at the shipped ink's fitted width."""
    def bounds(sprite):
        return sprite.getchannel('A').point(lambda a: 255 if a > 30 else 0).getbbox()

    base = bounds(reference)
    for i in range(6):
        path = directory / f'blob_{i:02}.png'
        with Image.open(path) as src:
            sprite = src.convert('RGBA')
        left, top, right, bottom = bounds(sprite)
        scale = (base[2] - base[0]) / (right - left)
        center = [(left + right)/2, (top + bottom)/2]
        size = [slot['size'][i] * scale * sprite.size[i] / reference.size[i] for i in range(2)]
        base_center = [slot['size'][i] * ((base[i]+base[i+2])/2/reference.size[i] - slot['pivot'][i])
                       for i in range(2)]
        pivot = [center[i]/sprite.size[i] - base_center[i]/size[i] for i in range(2)]
        yield path.stem, hashlib.sha256(path.read_bytes()).hexdigest(), sprite, {**slot, 'size': size, 'pivot': pivot}


def check(role, display_height, variant_dir=None):
    folder = ROOT / 'assets' / ('paper_lantern_' + role)
    export = folder / 'export'
    data = json.loads(subprocess.check_output(
        ['node', '--input-type=module', '-e', SAMPLE, str(export)], cwd=ROOT, encoding='utf-8'))
    with Image.open(export / 'atlas.png') as atlas:
        renderer = Preview(data['rig'], atlas.convert('RGBA'))
    renderer.size = (640, 650)
    renderer.origin = (320, 605)
    renderer.scale = display_height / data['rig']['height']
    y, x = np.ogrid[-12:13, -12:13]
    disk = x*x + y*y <= 12*12
    results = {}
    for shot in data['frames']:
        slots = shot['attachments']
        ink_index = next(i for i, slot in enumerate(slots) if slot and slot['part'] == 'rescue_ink')

        def alpha(selected):
            chosen = [slot if selected(i) else None for i, slot in enumerate(slots)]
            return np.asarray(renderer.art({**shot, 'attachments': chosen}))[..., 3]

        front = alpha(lambda i: i > ink_index)
        paper = alpha(lambda i: i != ink_index) >= 128
        clearance = distance_transform_edt(paper)
        rect = tuple(slots[ink_index]['rect'])
        if not results:
            x, y, w, h = rect
            base = renderer.atlas.crop((x, y, x+w, y+h))
            sprites = [('shipped', None, base, slots[ink_index])]
            if variant_dir:
                sprites.extend(candidate_sprites(variant_dir, base, slots[ink_index]))
            results = {name: [] for name, _, _, _ in sprites}
        for name, _, sprite, candidate in sprites:
            renderer.sprites[rect] = sprite
            chosen = [None] * len(slots)
            chosen[ink_index] = candidate
            ink = np.asarray(renderer.art({**shot, 'attachments': chosen}))[..., 3]
            visible = ink * (1 - front/255) >= 128
            opened = binary_opening(visible, structure=disk)
            row = {
                'clip': shot['name'], 'time': shot['time'],
                'radius': float(np.sqrt(opened.sum()/np.pi)),
                'paper_clearance': float(clearance[visible].min()) if visible.any() else 0,
                'outside': int((visible & ~paper).sum()),
            }
            if variant_dir:
                raw = ink >= 128
                row['unoccluded_source_paper_clearance'] = float(clearance[raw].min()) if raw.any() else 0
            results[name].append(row)
    if variant_dir:
        variants = {}
        for name, digest, _, _ in sprites:
            rows = results[name]
            report = summarize(rows, display_height)
            del report['samples']
            report['source_sha256'] = digest
            report['minimum_source_paper_clearance'] = min(r['unoccluded_source_paper_clearance'] for r in rows)
            failures = [r for r in rows if r['radius'] < 40 or r['paper_clearance'] < 6
                        or r['outside'] or r['unoccluded_source_paper_clearance'] < 6]
            report['passed'] = not failures
            report['failure_count'] = len(failures)
            report['first_failure'] = failures[0] if failures else None
            variants[name] = report
        print(role, {name: result['failure_count'] for name, result in variants.items()}, flush=True)
        return variants
    report = summarize(results['shipped'], display_height)
    (folder / 'qa/ink_attachment.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(role, {key: value for key, value in report.items() if key != 'samples'}, flush=True)
    return report['passed']


def summarize(results, display_height):
    report = {
        'scope': 'offline rendered alpha, current ink attachment, 30 fps',
        'display_height': display_height,
        'frames': len(results),
        'minimum_effective_radius': min(row['radius'] for row in results),
        'minimum_paper_clearance': min(row['paper_clearance'] for row in results),
        'max_outside_paper_pixels': max(row['outside'] for row in results),
        'samples': results,
    }
    report['passed'] = (report['minimum_effective_radius'] >= 40
                        and report['minimum_paper_clearance'] >= 6
                        and report['max_outside_paper_pixels'] == 0)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant-dir', type=Path, help='Directory containing original blob_00–05.png')
    parser.add_argument('--output', type=Path, help='Write diagnostic report without changing shipped assets')
    args = parser.parse_args()
    if bool(args.variant_dir) != bool(args.output):
        parser.error('--variant-dir and --output must be supplied together')
    roles = [('vendor', 512), ('video', 300)]
    if args.variant_dir:
        variants = {role: check(role, height, args.variant_dir) for role, height in roles}
        args.output.write_text(json.dumps({
            'scope': 'offline candidate fitting only, art2d atlas transform, 30 fps',
            'roles': variants,
        }, indent=2)+'\n', encoding='utf-8')
        raise SystemExit(0 if all(r['passed'] for group in variants.values() for r in group.values()) else 1)
    checks = [check(role, height) for role, height in roles]
    raise SystemExit(0 if all(checks) else 1)
