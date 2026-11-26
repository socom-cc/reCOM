# Stage 1: intake of the release (2026-11-25)

Read-only facts about the release disc and executable. The disc was handed over by the user as
a directory with its extracted contents; its location is user-local and not recorded.

## The disc

- `SYSTEM.CNF`: `BOOT2 = cdrom0:\SCUS_971.34;1`, `VER = 1.00`, `VMODE = NTSC`.
- 674 files, about 3.49 GB: 354 `.zed`, 150 `.zar` (683 MB), 60 `.pss` movies (2.53 GB),
  49 `.irx` modules, 23 `.mps`.
- Top level: the executable `SCUS_971.34`, a second executable `ntgui.elf` (3,510,137 bytes, the
  network set-up program), `ENDER` (1,146,880 bytes, not an ELF), network configuration files,
  and the folders `cnf`, `netgui` and `run`.
- `run` holds `common`, `Icons`, `irx`, `MOVIES`, `mp`, `reco`, `SOUNDS`, `sp`, `ui` and the
  archives `czanim.zar`, `extzanim.zar`, `ldzanim.zar`, `motion.zar`, `mpzanim.zar`,
  `readerc.zar`, `uizanim.zar`, `zweapon.zar`.

## The executable

| | Release `SCUS_971.34` | Prototype `socom.elf` |
|---|---|---|
| File size | 3,724,336 bytes | 10,765,300 bytes |
| SHA-256 | `5111e776...30d1` | `00c9cee7...4f8a` |
| Sections | 8; `.symtab` and `.strtab` empty; no debug sections | 12, with `.symtab` (21,894 symbols), `.debug`, `.line`, `.relmain`, `.mwcats` |
| Loaded image | 3,723,776 bytes at 0x100000 (memory size 0x4d6d00) | 3,626,496 bytes at 0x100000 (memory size 0x4e7f00) |
| Entry point | 0x140008 | 0x140010 |
| `.comment` | `MW MIPS C Compiler (2.4.1.01)`, `PlayStation2` | `MW MIPS C Compiler` |

Both are ELF32 little-endian MIPS with the same header flags (0x20924000).

## The Ghidra program

`SCUS_971.34` at project path `/socom-release`, language `r5900:LE:32:default`, compiler
specification `default`, image base 0x100000, created with Ghidra 12.1.4. Its recorded
`Executable SHA256` equals the disc's executable. The user ran the default auto-analysis on
2026-11-25: 8,772 functions and 11,384 symbols. Without symbols Ghidra finds only what calls and
address tables reach, so this is a lower bound; the comparison's own function list has 9,846.

## First comparison

These are the first run's numbers; the tool has been improved since, and the current ones are
in [../COMPARISON.md](../COMPARISON.md).

`python tools/release/compare.py` pairs the two executables directly: 6,320 exact, 2,331 deviating, 375 unsure, 820 new, 680
removed. For authored code: 3,768 exact, 2,132 deviating (1.28 MB), 294 unsure, 371 removed, and
545 of the new functions sit among authored neighbours. No pair has been checked by a second
agent yet.
