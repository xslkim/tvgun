"""Check grip overlap and render close-ups from the exported Paper Lantern rigs."""
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from render import Preview


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = """
import {read} from './pipeline/export/build.mjs';
import {world,sample,attachmentAt} from './pipeline/rig/runtime.mjs';

const dir = process.argv[1];
const {rig, clips} = read(dir + '/character.json');
const poses = Object.entries(clips).map(([name, file]) => [name, read(dir + '/' + file)]);
const parts = ['hand_far', 'held_object', 'hand_far_front', 'sleeve_far'];
const indices = parts.map(part => rig.attachments.findIndex(slot => slot.part === part));
if (indices[0] < 0 || indices.some((index, i) => i && index <= indices[i-1])) {
  throw new Error('Expected palm, held object, thumb, then sleeve in draw order');
}
const frames = poses.flatMap(([name, clip]) => clip.frames.map((pose, i) => {
  const time = Math.min(i / clip.bake_hz, clip.duration);
  const w = world(rig, pose);
  const attachments = indices.map(index => attachmentAt(rig.attachments[index], clip, time));
  if (attachments.some((slot, j) => slot?.part !== parts[j])) {
    throw new Error('Grip slot changed in ' + name + ' at ' + time);
  }
  return {name, time, w: Object.fromEntries(attachments.map(slot => [slot.bone, w[slot.bone]]))};
}));
const closeups = [['idle', .6], ['walk', .63], ['wave_for_help', 1.38], ['struggle', 1.15]]
  .map(([name, time]) => {
    const clip = poses.find(([key]) => key === name)[1];
    return {name, time, w: world(rig, sample(clip, time, false)),
      attachments: rig.attachments.map(slot => attachmentAt(slot, clip, time))};
  });
console.log(JSON.stringify({rig, grip: indices.map(i => rig.attachments[i]), frames, closeups}));
"""


def check(role, sheet, row):
    export = ROOT / 'assets' / ('paper_lantern_' + role) / 'export'
    data = json.loads(subprocess.check_output(
        ['node', '--input-type=module', '-e', SAMPLE, str(export)], cwd=ROOT, encoding='utf-8'))
    with Image.open(export / 'atlas.png') as atlas:
        renderer = Preview(data['rig'], atlas.convert('RGBA'))
    renderer.size = (96, 96)
    renderer.scale = 1.5
    minimum_covered = float('inf')
    minimum_visible = float('inf')
    for frame in data['frames']:
        grip = frame['w']['held_prop']
        renderer.origin = (48 - grip['x'] * renderer.scale, 48 + grip['y'] * renderer.scale)
        palm, prop, thumb, sleeve = (
            np.asarray(renderer.art({**frame, 'attachments': [slot]}))[..., 3] >= 128
            for slot in data['grip']
        )
        contact = palm & prop & ~sleeve
        covered = int(np.count_nonzero(contact & thumb))
        visible = int(np.count_nonzero(contact & ~thumb))
        if covered < 3 or visible < 3:
            raise ValueError(f'{role} {frame["name"]} {frame["time"]:.3f}s: {covered=} {visible=}')
        minimum_covered = min(minimum_covered, covered)
        minimum_visible = min(minimum_visible, visible)
    print(f'{role}: {len(data["frames"])} baked poses, '
          f'minimum thumb-covered / visible over palm: {minimum_covered} / {minimum_visible} pixels', flush=True)

    renderer.size = (220, 240)
    center = (95, 155) if role == 'vendor' else (82, 85)
    for col, frame in enumerate(data['closeups']):
        grip = frame['w']['held_prop']
        renderer.origin = (center[0] - grip['x'] * renderer.scale, center[1] + grip['y'] * renderer.scale)
        panel = Image.new('RGBA', renderer.size, '#172838')
        panel.alpha_composite(renderer.art(frame))
        ImageDraw.Draw(panel).text((9, 8), f'{role} / {frame["name"]}', fill='white')
        sheet.paste(panel.convert('RGB'), (col * panel.width, row * panel.height))


if __name__ == '__main__':
    preview = Image.new('RGB', (880, 480))
    check('vendor', preview, 0)
    check('video', preview, 1)
    preview.save(ROOT / 'assets/paper_lantern_vendor/qa/grip_recheck.png')
