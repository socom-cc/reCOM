# Verified patterns

This file records reusable observations only after they are reproduced against
immutable evidence. It intentionally begins with workspace-level facts rather
than speculative code patterns.

## Accepted workspace facts

- The reference is little-endian ELF32 MIPS with entry point `0x140010`.
- The live Ghidra program uses `r5900:LE:32:default`; the fresh import reports
  9,715 functions, 24,194 symbols, 210 data types, and 26 memory blocks.
- Bootstrap analysis has 716 Analysis bookmarks (713 Address Table and three
  Non-Returning Function) and no Error or Warning bookmarks.
- Metrowerks DWARF 1 synthetic `@...` type spellings are not globally unique.
  Import identities therefore include compile-unit, parent, and DIE offsets.
- `R_MIPS_HI16` and `R_MIPS_LO16` evidence must be interpreted as paired
  relocation semantics, not unrelated scalar fixups.
- Full compiler execution remains blocked until a valid FLEXlm license is
  supplied; compiler identity verification alone is not ABI proof.

## Entry template

For each later pattern record:

- concise claim;
- ELF addresses/sections and DIE/symbol IDs;
- reproducing command or exact compiler probe;
- accepted tracker evidence;
- scope and counterexamples;
- date/tool version.

Do not promote a single decompilation shape or one source occurrence into a
global pattern.
