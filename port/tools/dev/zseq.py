"""zseq.py <zar> <anim>: dump an anim's compiled sequences (commands: type, size, words) from a zanim ZAR (scratch)."""
import os, sys, struct, importlib.util
spec = importlib.util.spec_from_file_location('zar', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zar.py'))
argv = sys.argv; sys.argv = argv[:2] + ['none']
z = importlib.util.module_from_spec(spec)
try: spec.loader.exec_module(z)
except SystemExit: pass
base = z.find('/Anim_Sets/mission')
names = [k['name'] for k in z.find('/Anim_Sets/mission/Name_Table')['kids']]
a = z.find('/Anim_Sets/mission/Animation_List/' + argv[2])
nit = z.data(next(k for k in a['kids'] if k['name'] == 'Name_Index_Table'))
idx = struct.unpack_from('<%dH' % (len(nit) // 2), nit)
d = z.data(next(k for k in a['kids'] if k['name'] == 'Seq_Data'))
o = 0
while o < len(d):
    w0, w1, pc, size = struct.unpack_from('<IIII', d, o)
    ni = w0 & 0xffff
    print('SEQ %s (state %d act %d) size 0x%x' % (names[idx[ni]] if ni < len(idx) else ni, (w1 >> 8) & 0xff, (w1 >> 1) & 0x7f, size))
    c = o + 28
    while c < o + size:
        h, = struct.unpack_from('<I', d, c)
        t = h & 0xffff; sz = h >> 18
        words = struct.unpack_from('<%dI' % (sz // 4 - 1), d, c + 4) if sz >= 8 else ()
        fl = ['%g' % struct.unpack('<f', struct.pack('<I', w))[0] if 0x30000000 < w < 0x50000000 or 0xb0000000 < w < 0xd0000000 else hex(w) for w in words]
        print('  +%03x type %04x size %3d: %s' % (c - o, t, sz, ' '.join(fl)))
        if sz == 0: break
        c += sz
    o += size
