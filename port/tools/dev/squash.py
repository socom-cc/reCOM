"""squash.py <decompile.c>: compress Ghidra's VU0 transform loops, xyz copies and seal chord registrations."""
import re, sys
s = open(sys.argv[1]).read()
s = s.replace('_curChord__18_unnamed_seal_cpp_', 'curChord').replace('(this->super_CBody).', '').replace('(this->super_CEntity).', '')
s = s.replace('.super_PNT3D', '').replace('->super_PNT3D', '')
s = re.sub(r'iVar\d+ = 1;\s*\n\s*pPVar\d+ = (&?\w+);\s*\n\s*auVar\d+ = _lqc2\(\(undefined1  \[16\]\)([^\n]*?)\.m_matrix\[0\]\);.*?\} while \(iVar\d+ != 0\);',
           lambda m: 'XFORM(%s by %s);' % (m.group(1), m.group(2)), s, flags=re.S)
pat = re.compile(r'(?:\*\*\(undefined2 \*\*\)\(dilr__18_unnamed_seal_cpp_ \+ curChord \* 4\) = 2;\s*)?(?:\w+\._0_8_ = uVar22;\s*)?zdb__CWorld__RegIntersectDelayed\s*\(zdb__CWorld__m_world,\s*\*\(DiIntersect \*\*\)\s*\(dilr__18_unnamed_seal_cpp_ \+ curChord \* 4\)\s*,\s*\(CPnt3D \*\)([^,]+),\s*\(CPnt3D \*\)([^)]+)\);\s*pCVar\d+ = CEntity__GetNode\(&this->super_CEntity\);\s*\*\(CNode \*\*\)\s*\(\*\(int \*\)\(dilr__18_unnamed_seal_cpp_ \+ curChord \* 4\) \+ 0x3c\)\s*=\s*pCVar\d+;\s*\*\(byte \*\)\(\*\(int \*\)\(dilr__18_unnamed_seal_cpp_ \+ curChord \* 4\) \+ 2\) =\s*\*\(byte \*\)\(\*\(int \*\)\(dilr__18_unnamed_seal_cpp_ \+ curChord \* 4\) \+\s*2\)\s*&\s*0xfe;\s*curChord = curChord \+ 1;')
s = pat.sub(lambda m: 'CHORD(%s, %s);' % (m.group(1), m.group(2)), s)
s = re.sub(r'if \(0x31 < curChord\) \{\s*return;\s*\}\s*', 'CHK50; ', s)
# xyz copies
s = re.sub(r'(\S+)\.x = (\S+)\.x;\s*\n\s*\1\.y = (\S+)\.y;\s*\n\s*\1\.z = (\S+)\.z;', lambda m: '%s = %s/%s/%s;' % (m.group(1), m.group(2), m.group(3), m.group(4)) if not (m.group(2)==m.group(3)==m.group(4)) else '%s = %s;' % (m.group(1), m.group(2)), s)
s = re.sub(r'\n\s*uVar22 = [^;]*;', '', s)
s = re.sub(r'\n\s*\w+\._0_8_ = uVar22;', '', s)
print(s)
