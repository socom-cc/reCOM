"""nd.py < cz-output: list branches whose delay slot is a nop but are followed by a real instruction
(the places where a nop-stripped listing is misread). Prints the branch and the following line."""
import sys, re
L = [l.rstrip('\n') for l in sys.stdin]
for i, l in enumerate(L[:-1]):
    body = l[9:].strip() if len(l) > 9 else l.strip()
    if body.startswith('| '): body = body[2:]
    op = body.split(' ')[0] if body else ''
    if (op.startswith('b') or op in ('j', 'jr')) and not L[i + 1][9:].strip().startswith('| '):
        print('%4d %s   >>   %s' % (i + 1, body, L[i + 1].strip()))
