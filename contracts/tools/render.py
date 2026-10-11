"""Rasterize previews/*.svg (1x1 rect pixel art, class-based fills) to PNG + a contact sheet.
Parses the SVG exactly as emitted by Tunki.art(): background colour, .cN{fill:#hex} classes,
<rect x y class>, and the <g transform="translate(a b)"> head offset (frame 0 of the bob).
Also writes frame strips showing the discrete bob so the animation can be checked.
"""
import os, re, sys, json
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PV = os.path.join(HERE, '..', 'previews')
SCALE = 12


def parse(svg, frame=None):
    bg = re.search(r'background:#([0-9a-f]{6})', svg).group(1)
    cls = dict(re.findall(r'\.c(\d+)\{fill:#([0-9a-f]{6})\}', svg))
    img = Image.new('RGB', (32, 32), '#' + bg)
    px = img.load()
    head_start = svg.find('<animateTransform')
    head_end = svg.find('</g></g>')
    base = re.search(r'<g transform="translate\((-?\d+) (-?\d+)\)">', svg)
    bx, by = (int(base.group(1)), int(base.group(2))) if base else (0, 0)
    vals = re.search(r'values="([^"]+)"', svg).group(1).split(';')
    fx, fy = (0, 0) if frame is None else map(int, vals[frame % len(vals)].split())
    for m in re.finditer(r'<rect x="(\d+)" y="(\d+)" width="1" height="1" class="c(\d+)"/>', svg):
        x, y, c = int(m.group(1)), int(m.group(2)), m.group(3)
        if head_start < m.start() < head_end:
            x, y = x + bx + fx, y + by + fy
        if 0 <= x < 32 and 0 <= y < 32:
            px[x, y] = tuple(int(cls[c][i:i + 2], 16) for i in (0, 2, 4))
    return img, len(vals)


def main():
    ids = sorted(int(f[:-4]) for f in os.listdir(PV) if f.endswith('.svg'))
    tiles = []
    for i in ids:
        svg = open(os.path.join(PV, f'{i}.svg')).read()
        img, nf = parse(svg)
        img.resize((32 * SCALE, 32 * SCALE), Image.NEAREST).save(os.path.join(PV, f'{i}.png'))
        tiles.append(img)
        frames = [parse(svg, k)[0] for k in range(nf)]
        strip = Image.new('RGB', (32 * nf + (nf - 1), 32), '#000')
        for k, f in enumerate(frames):
            strip.paste(f, (k * 33, 0))
        strip.resize((strip.width * 6, 32 * 6), Image.NEAREST).save(os.path.join(PV, f'{i}_bob.png'))
        if i <= 6:  # animated gif of the bob for quick viewing
            g = [f.resize((256, 256), Image.NEAREST) for f in frames]
            g[0].save(os.path.join(PV, f'{i}_bob.gif'), save_all=True, append_images=g[1:], duration=230, loop=0)
    cols = 8
    rows = (len(tiles) + cols - 1) // cols
    t = 32 * 6
    sheet = Image.new('RGB', (cols * (t + 6) + 6, rows * (t + 6) + 6), '#111')
    for k, img in enumerate(tiles):
        sheet.paste(img.resize((t, t), Image.NEAREST), (6 + (k % cols) * (t + 6), 6 + (k // cols) * (t + 6)))
    sheet.save(os.path.join(PV, 'sheet.png'))
    # stamp test: every token at 16x16 (half resolution, box filter)
    stamp = Image.new('RGB', (cols * 20 + 4, rows * 20 + 4), '#111')
    for k, img in enumerate(tiles):
        stamp.paste(img.resize((16, 16), Image.BOX), (4 + (k % cols) * 20, 4 + (k // cols) * 20))
    stamp.resize((stamp.width * 4, stamp.height * 4), Image.NEAREST).save(os.path.join(PV, 'stamp_test.png'))
    print('rendered', len(ids), 'sheet', os.path.abspath(os.path.join(PV, 'sheet.png')))


if __name__ == '__main__':
    main()
