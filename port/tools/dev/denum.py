"""denum.py <EnumName>...: DWARF 1 enumerators (element_list: value of byte_size bytes, then the name)."""
import _dev
import pickle, sys, os
types = _dev.types()
for want in sys.argv[1:]:
    for t in types:
        if t.get('qualified_name') == want and t.get('kind') == 'enumeration_type':
            ev = t['evidence']['attributes']
            b = bytes.fromhex(ev['element_list']['value'])
            sz = ev.get('byte_size', {}).get('value', 4)
            i = 0; out = []
            while i < len(b):
                v = int.from_bytes(b[i:i+sz], 'little', signed=True); i += sz
                j = b.index(0, i); out.append((v, b[i:j].decode())); i = j + 1
            print(want, 'size', sz, ' '.join('%s=%d' % (n, v) for v, n in out))
            break
