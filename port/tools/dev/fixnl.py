"""fixnl.py <file>...: repair inline-asm string literals whose \\n\\t escapes were turned into a real
newline + tab by a shell layer (a quote opened on a line that ends inside the literal), and make
the file's line endings uniform CRLF."""
import re, sys

for path in sys.argv[1:]:
    s = open(path, encoding='utf-8', newline='').read()
    lines = s.replace('\r\n', '\n').split('\n')
    out = []
    i = 0
    fixed = 0
    while i < len(lines):
        line = lines[i]
        # an odd number of double quotes: the literal continues on the next line
        while line.count('"') % 2 == 1 and i + 1 < len(lines) and lines[i + 1].startswith('\t'):
            nxt = lines[i + 1]
            line = line + '\\n\\t' + nxt[1:]
            i += 1
            fixed += 1
        out.append(line)
        i += 1
    open(path, 'w', encoding='utf-8', newline='').write('\r\n'.join(out))
    print(path, 'joined', fixed)
