"""fl.py <addr>...: 4-byte float/int at ELF virtual addresses (support/socom.elf, read-only). Scratch."""
import _dev
import struct, sys, os
elf = _dev.elf()
e_phoff, = struct.unpack_from('<I', elf, 0x1c); phentsize, phnum = struct.unpack_from('<HH', elf, 0x2a)
for a in sys.argv[1:]:
    va = int(a, 16)
    for i in range(phnum):
        t, off, v, p, fs, ms, fl, al = struct.unpack_from('<IIIIIIII', elf, e_phoff + i * phentsize)
        if v <= va < v + fs:
            raw = elf[off + va - v: off + va - v + 4]
            print('%08x float %g int %d hex %s' % (va, struct.unpack('<f', raw)[0], struct.unpack('<i', raw)[0], raw[::-1].hex()))
            break
    else:
        print('%08x not in file (bss)' % va)
