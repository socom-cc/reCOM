"""vt.py <vtable-addr> <nslots>: vtable slot -> symbol. Scratch."""
import os, subprocess, sys
syms = {}
for l in subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sym.py'), '^'], capture_output=True, text=True).stdout.splitlines():
    p = l.split()
    if len(p) >= 3:
        try: syms.setdefault(int(p[0], 16), p[2])
        except ValueError: pass
out = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sym.py'), sys.argv[1], sys.argv[2]], capture_output=True, text=True).stdout
for i, l in enumerate(out.splitlines()):
    try: a = int(l.split(':')[1].split()[0], 16)
    except ValueError: continue
    print('+0x%02x %s' % (i * 4, syms.get(a, hex(a))))
