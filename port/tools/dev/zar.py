"""zar.py <file> [tree [prefix] | get <path/with/slashes> | hex <path>]: dump a soCOM ZAR (read-only)."""
import sys, struct
d = open(sys.argv[1], 'rb').read()
tail = d[-96:]
flags, key_count, ssize, sofs = struct.unpack_from('<4i', tail, 0)
offset, crc, appver, ver = struct.unpack_from('<4i', tail, 80)
secure = False
if ver not in (1, 2) and (~ver & 0xffffffff) in (1, 2):
    secure = True
def unsec(b): return bytes((~x) & 0xff for x in b) if secure else b
st = unsec(d[offset:offset + ssize])
keys = unsec(d[offset + ssize: offset + ssize + key_count * 16])
pos = [0]
def name(o):
    o -= sofs
    return st[o:st.index(b'\0', o)].decode('latin1') if 0 <= o < len(st) else '?%x' % (o + sofs)
def readkey(root=False):
    n, off, size, cnt = struct.unpack_from('<iiiI', keys, pos[0]); pos[0] += 16
    k = {'name': '' if root else name(n), 'off': off, 'size': size, 'kids': []}
    for _ in range(cnt): k['kids'].append(readkey())
    return k
root = readkey(True)
def data(k): return unsec(d[k['off']:k['off'] + k['size']])
def walk(k, path=''):
    yield path, k
    for c in k['kids']: yield from walk(c, path + '/' + c['name'])
def find(p):
    k = root
    for part in [x for x in p.split('/') if x]:
        k = next(c for c in k['kids'] if c['name'].lower() == part.lower())
    return k
if __name__ == '__main__':
    cmd = sys.argv[2] if len(sys.argv) > 2 else 'tree'
    if cmd == 'tree':
        pre = sys.argv[3] if len(sys.argv) > 3 else ''
        base = find(pre) if pre else root
        for p, k in walk(base, pre):
            dd = data(k) if k['size'] > 0 else b''
            print('%-70s %6d %s' % (p, k['size'], dd[:24].hex(' ') if len(dd) <= 64 or True else ''))
    elif cmd == 'hex':
        k = find(sys.argv[3]); dd = data(k)
        for i in range(0, len(dd), 16): print('%04x: %s  %s' % (i, dd[i:i+16].hex(' '), ''.join(chr(c) if 32 <= c < 127 else '.' for c in dd[i:i+16])))
    elif cmd == 'get':
        sys.stdout.buffer.write(data(find(sys.argv[3])))
