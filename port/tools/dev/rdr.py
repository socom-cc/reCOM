"""rdr.py <zar> <name> : dump a compiled zReader file from a ZAR (read-only, port diagnosis)."""
import os, sys, struct, importlib.util
spec = importlib.util.spec_from_file_location('zar', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zar.py'))
argv = sys.argv; sys.argv = argv[:2]
z = importlib.util.module_from_spec(spec); spec.loader.exec_module(z)
d = z.data(z.find(argv[2]))
slen, root = struct.unpack_from('<II', d, 0)
def s(o):
    o += 8
    return d[o:d.index(b'\0', o)].decode('latin1')
def node(o, ind):
    t, v = struct.unpack_from('<Ii', d, o)
    if t == 1: return str(v)
    if t == 2: return '%g' % struct.unpack_from('<f', d, o + 4)[0]
    if t == 3: return repr(s(v))
    if t == 4: return arr(root + v, ind)
    return '?%d:%x' % (t, v)
def arr(o, ind):
    t, n = struct.unpack_from('<Ii', d, o)
    items = [node(o + 8 * i, ind + 1) for i in range(1, n)]
    flat = '(' + ' '.join(items) + ')'
    if len(flat) < 100 and '\n' not in flat: return flat
    return '(\n' + ''.join('  ' * (ind + 1) + it + '\n' for it in items) + '  ' * ind + ')'
print(arr(root, 0))
