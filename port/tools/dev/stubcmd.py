"""stubcmd.py <tree-root>: TEST ONLY (scratch trees under ~/.cache/socom, never the repo): every
empty non-void command tick stub (bool / unsigned char return, a _zanim_cmd_hdr* or C2DAnimCmdHdr*
parameter) gets a trace and `return 1;` so a test boot lists the unwritten commands the anims
reach instead of STOPping."""
import os, re, sys, glob
root = os.path.abspath(sys.argv[1])
if '.cache' not in root:
    sys.exit('stubcmd: refusing a root outside ~/.cache (test trees only)')
n = 0
pat = re.compile(r'^/\* @socom-skeleton stub (\S+) \*/\n((?:bool|unsigned char|u8) [^\n]*\([^\n]*(?:_zanim_cmd_hdr|C2DAnimCmdHdr)[^\n]*\))\n\{\n((?:\t/\* @socom-skeleton stub [^\n]*\n\tstatic [^\n]*\n)*)\}\n', re.M)
for f in glob.glob(os.path.join(root, 'src', '**', '*.cpp'), recursive=True):
    s = open(f, encoding='utf-8', errors='replace').read()
    out = s
    changed = False
    for m in pat.finditer(s):
        name = m.group(1)
        new = '/* @socom-skeleton stub %s */\n%s\n{\n%s\tSOCOM_PORT_TRACE("DIAG: STUBCMD %s"); return 1;\n}\n' % (name, m.group(2), m.group(3), name)
        out = out.replace(m.group(0), new, 1)
        changed = True
        n += 1
    if changed:
        open(f, 'w', encoding='utf-8').write(out)
        open(os.path.join(root, '.touched'), 'a').write(os.path.relpath(f, root).replace(os.sep, '/') + chr(10))
print('stubcmd: %d stubs' % n)
