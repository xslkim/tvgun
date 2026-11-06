"""Check the resident animation's visible attached ink at its game display size.

Run from the workspace with the GunForge art Python environment and Node on PATH.
"""
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


def check(role, display_height):
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
    results = []
    for shot in data['frames']:
        slots = shot['attachments']
        ink_index = next(i for i, slot in enumerate(slots) if slot and slot['part'] == 'rescue_ink')

        def alpha(selected):
            chosen = [slot if selected(i) else None for i, slot in enumerate(slots)]
            return np.asarray(renderer.art({**shot, 'attachments': chosen}))[..., 3]

        ink = alpha(lambda i: i == ink_index)
        front = alpha(lambda i: i > ink_index)
        paper = alpha(lambda i: i != ink_index) >= 128
        visible = ink * (1 - front/255) >= 128
        opened = binary_opening(visible, structure=disk)
        results.append({
            'clip': shot['name'], 'time': shot['time'],
            'radius': float(np.sqrt(opened.sum()/np.pi)),
            'paper_clearance': float(distance_transform_edt(paper)[visible].min()) if visible.any() else 0,
            'outside': int((visible & ~paper).sum()),
        })
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
    (folder / 'qa/ink_attachment.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(role, {key: value for key, value in report.items() if key != 'samples'}, flush=True)
    return report['passed']


if __name__ == '__main__':
    checks = [check('vendor', 512), check('video', 300)]
    raise SystemExit(0 if all(checks) else 1)
