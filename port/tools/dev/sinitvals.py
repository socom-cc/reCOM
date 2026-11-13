"""sinitvals.py <asm file> <ptr-stack-off> [base-symbol]: emulate a straight-line __sinit
(lui/ori/li/addiu/move/lw/sw/sq/lq/mtc1/swc1/lwc1) and print the words stored at offsets of the
pointer kept at <ptr-stack-off>(sp) or of registers set by lui/addiu to the base symbol. Scratch."""
import re, sys, struct
lines = open(sys.argv[1], encoding='utf-8-sig').read().split('\n')
poff = int(sys.argv[2])
base = sys.argv[3] if len(sys.argv) > 3 else 'theCharacterDynamics'
R = {'zero': 0}
F = {}
S = {}
PTR = 'PTR'
out = {}
def val(r):
    return R.get(r)
for l in lines:
    m = re.match(r'\s*[0-9a-f]+:\s+(\S+)\s+([^;]*)', l)
    if not m: continue
    op, args = m.group(1), [a.strip() for a in m.group(2).split(',')]
    ann = l.split(';')[1] if ';' in l else ''
    try:
        if op == 'lui': R[args[0]] = int(args[1], 0) << 16
        elif op == 'ori':
            v = val(args[1]); R[args[0]] = (v | int(args[2], 0)) if isinstance(v, int) else None
        elif op == 'li': R[args[0]] = int(args[1], 0) & 0xffffffff
        elif op == 'move': R[args[0]] = val(args[1])
        elif op == 'addiu':
            if base in ann: R[args[0]] = PTR
            else:
                v = val(args[1]); R[args[0]] = ((v + int(args[2], 0)) & 0xffffffff) if isinstance(v, int) else None
        elif op in ('lw', 'lq', 'ld'):
            mm = re.match(r'(-?\d+)\((\w+)\)', args[1])
            if mm.group(2) == 'sp':
                o = int(mm.group(1)); R[args[0]] = PTR if o == poff else S.get(o)
            else: R[args[0]] = None
        elif op in ('sw', 'sq', 'sd'):
            mm = re.match(r'(-?\d+)\((\w+)\)', args[1])
            o, b = int(mm.group(1)), mm.group(2)
            if b == 'sp': S[o] = val(args[0])
            elif val(b) == PTR: out[o] = val(args[0])
        elif op == 'mtc1': F[args[1]] = val(args[0])
        elif op == 'mov.s': F[args[0]] = F.get(args[1])
        elif op == 'swc1':
            mm = re.match(r'(-?\d+)\((\w+)\)', args[1])
            o, b = int(mm.group(1)), mm.group(2)
            if b == 'sp': S[o] = F.get(args[0])
            elif val(b) == PTR: out[o] = F.get(args[0])
        elif op == 'lwc1':
            mm = re.match(r'(-?\d+)\((\w+)\)', args[1])
            F[args[0]] = S.get(int(mm.group(1))) if mm.group(2) == 'sp' else None
        elif op in ('jal', 'jalr'):
            for r in ('v0', 'v1', 'a0', 'a1', 'a2', 'a3', 't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7', 't8', 't9'): R[r] = None
    except Exception as e:
        pass
for o in sorted(out):
    v = out[o]
    f = struct.unpack('<f', struct.pack('<I', v))[0] if isinstance(v, int) else None
    print('+%d (0x%x): %s %s' % (o, o, ('0x%08x' % v) if isinstance(v, int) else v, f))
