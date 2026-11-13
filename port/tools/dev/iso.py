"""iso.py [<image>] [ls [path-prefix]] | [get <path> <out>]: read-only ISO9660 walk of the game disc
image (2048 or raw 2352-byte sectors). The image is the first argument when it names a file, else
SOCOM_DISC_IMAGE (user-local; never record its path). Never writes disc data into the repository."""
import os, sys, struct
if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
    pass
elif os.environ.get('SOCOM_DISC_IMAGE'):
    sys.argv.insert(1, os.environ['SOCOM_DISC_IMAGE'])
else:
    sys.exit('iso.py: give the disc image path or set SOCOM_DISC_IMAGE')
img = open(sys.argv[1], 'rb')
def probe():
    for ss, off in ((2048, 0), (2352, 24), (2352, 16)):
        img.seek(16 * ss + off)
        if img.read(6)[1:6] == b'CD001':
            return ss, off
    raise SystemExit('no ISO9660')
SS, OFF = probe()
def sector(n, count=1):
    out = b''
    for i in range(count):
        img.seek((n + i) * SS + OFF); out += img.read(2048)
    return out
def read_extent(lba, size):
    data = sector(lba, (size + 2047) // 2048)
    return data[:size]
pvd = sector(16)
root = pvd[156:156 + 34]
def entries(lba, size):
    data = read_extent(lba, size); i = 0
    while i < len(data):
        l = data[i]
        if l == 0:
            i = (i // 2048 + 1) * 2048; continue
        rec = data[i:i + l]
        elba, = struct.unpack_from('<I', rec, 2); esize, = struct.unpack_from('<I', rec, 10)
        flags = rec[25]; nl = rec[32]; name = rec[33:33 + nl].decode('latin1')
        if name not in ('\x00', '\x01'):
            yield name.split(';')[0], elba, esize, bool(flags & 2)
        i += l
def walk(lba, size, path=''):
    for name, elba, esize, isdir in entries(lba, size):
        p = path + '/' + name
        yield p, elba, esize, isdir
        if isdir:
            yield from walk(elba, esize, p)
rlba, = struct.unpack_from('<I', root, 2); rsize, = struct.unpack_from('<I', root, 10)
cmd = sys.argv[2] if len(sys.argv) > 2 else 'ls'
if cmd == 'ls':
    pre = sys.argv[3].upper() if len(sys.argv) > 3 else ''
    for p, lba, size, isdir in walk(rlba, rsize):
        if p.upper().startswith(pre): print('%s%s %d' % (p, '/' if isdir else '', size))
elif cmd == 'get':
    want = sys.argv[3].upper()
    for p, lba, size, isdir in walk(rlba, rsize):
        if p.upper() == want:
            open(sys.argv[4], 'wb').write(read_extent(lba, size)); print('ok', size); break
