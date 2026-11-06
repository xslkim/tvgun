"""Make compact four-column clip reviews from rendered GIFs."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]


def review(ident):
    folder = ROOT / 'assets' / ident
    export = folder / 'export'
    preview = folder / 'preview'
    names = json.loads((export / 'character.json').read_text(encoding='utf-8'))['clips']
    for group, start in enumerate(range(0, len(names), 7), 1):
        section = list(names)[start:start+7]
        board = Image.new('RGB', (960, 194*len(section)), '#101f30')
        draw = ImageDraw.Draw(board)
        for row, name in enumerate(section):
            with Image.open(preview / f'{name}.gif') as frames:
                for col, phase in enumerate([0,.30,.52,.88]):
                    frames.seek(round((frames.n_frames-1)*phase))
                    im = frames.convert('RGB').resize((240, 188), Image.Resampling.LANCZOS)
                    board.paste(im, (col*240,row*194+6))
                draw.text((4,row*194+6), name, fill='#ffe1a8', stroke_width=1, stroke_fill='#101f30')
        board.save(preview / f'review_{group}.png',optimize=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ident', nargs='+')
    for ident in parser.parse_args().ident:
        review(ident)
