"""Apply several fence-region replacements from one file.
usage: multi_replace.py <source-file> <edits-file>
The edits file holds sections headed '@@ <mangled-name>'; each section replaces the
region that follows that skeleton fence, up to the next fence line (the fence line is
kept, one blank line is kept before the next fence)."""
import re
import sys

path, edits = sys.argv[1], sys.argv[2]
raw = open(path, 'rb').read()
crlf = b'\r\n' in raw
text = raw.decode('utf-8')
if crlf:
    text = text.replace('\r\n', '\n')
lines = text.split('\n')

sections = []
cur = None
for l in open(edits, encoding='utf-8').read().replace('\r\n', '\n').split('\n'):
    if l.startswith('@@ '):
        cur = [l[3:].strip(), []]
        sections.append(cur)
    elif cur is not None:
        cur[1].append(l)

for name, body in sections:
    pat = re.compile(r'^/\* @socom-skeleton (body|stub) ' + re.escape(name) + r' \*/$')
    idx = [i for i, l in enumerate(lines) if pat.match(l)]
    if len(idx) != 1:
        sys.exit('fence %s: %d matches' % (name, len(idx)))
    start = idx[0] + 1
    end = start
    while end < len(lines) and not lines[end].startswith('/* @socom-skeleton '):
        end += 1
    while body and body[-1] == '':
        body.pop()
    tail = [''] if end < len(lines) else []
    lines[start:end] = body + tail
    print('replaced', name)

out = '\n'.join(lines)
if crlf:
    out = out.replace('\n', '\r\n')
open(path, 'wb').write(out.encode('utf-8'))
