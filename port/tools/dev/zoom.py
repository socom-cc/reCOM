"""zoom.py <png> <x0> <y0> <x1> <y1> [scale] [out]: crop a screenshot region and upscale it (scratch only)."""
import sys
from PIL import Image
p = sys.argv[1]; x0, y0, x1, y1 = map(int, sys.argv[2:6])
k = int(sys.argv[6]) if len(sys.argv) > 6 else 3
out = sys.argv[7] if len(sys.argv) > 7 else p.replace('.png', '_z.png')
im = Image.open(p).crop((x0, y0, x1, y1))
im = im.resize((im.width * k, im.height * k), Image.LANCZOS)
im.save(out); print(out, im.size)
