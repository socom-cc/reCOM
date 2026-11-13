"""splice.py <file> <marker> <tailfile>: replace everything from the line containing <marker> to the
end of <file> with the contents of <tailfile> (keeps BOM and line endings). The marker must occur
exactly once (merged from tail.py). Use on scratch/test-tree copies or your own files only."""
import sys
path, marker, tail = sys.argv[1], sys.argv[2], sys.argv[3]
raw = open(path, 'rb').read()
bom = raw.startswith(b'\xef\xbb\xbf')
text = raw.decode('utf-8-sig')
crlf = '\r\n' in text
text = text.replace('\r\n', '\n')
n = text.count(marker)
if n != 1:
    sys.exit('splice: marker occurs %d times in %s (need exactly 1)' % (n, path))
i = text.index(marker)
i = text.rfind('\n', 0, i) + 1
new = open(tail, encoding='utf-8').read().replace('\r\n', '\n')
out = text[:i] + new
if crlf:
    out = out.replace('\n', '\r\n')
open(path, 'wb').write((b'\xef\xbb\xbf' if bom else b'') + out.encode('utf-8'))
print('spliced', path, 'at', i)
