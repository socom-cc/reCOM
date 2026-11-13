# Port development tools

Helpers for the functional port lane (AGENTS.md "Functional port lane"): reading the reference ELF
and its DWARF, editing your test copy of the source, building isolated test builds with the pinned
ps2dev toolchain on the Linux side, and booting them in PCSX2. They are development aids only: none
of them is a public `python tools/socom.py` command, none mutates the tracker or Ghidra, and nothing
they produce is evidence for the matching stages. Test hooks live in
[`port/test-hooks/`](../../test-hooks/README.md).

All tools find the checkout from their own location. Outputs go to your scratch folder (ignored
`build/`) or to `~/.cache/socom` on the Linux side; the reference ELF is only read.

## How the pieces fit

```text
 checkout (HEAD + your files)                     Linux side (WSL), ~/.cache/socom
 ---------------------------                      --------------------------------
 tree.sh ------------------------------------->   tree-<name>/   isolated src/ + port/
   copy.txt / shared.txt / base.txt in scratch       |
 tb.sh (tree + test edits + fake + hook) ------>     v
 fake.sh <build> <pad>  ----------------------->  <build>/socom_port.elf  (fake-pad build)
 hook.sh / port/test-hooks/<f>/build.sh ------->  <build>/socom_port.elf  (+ --wrap test hook)
 default.sh <build> --------------------------->  <build>/socom_port.elf  (normal build check)
                                                     |
 Windows side                                        v
 run.ps1 -Build <build> -Name <run>   copies the ELF into the scratch folder, then
   pcsx2-boot.ps1                     boots it (second monitor, never takes focus, quiet), kills it
                                      after -Seconds, writes <run>.log and <run>-<t>.png
 lg.sh <run>.log                      the interesting log lines (HOOK / DIAG / STOP / exceptions)
```

From PowerShell, run any Linux-side script with `.\port\tools\dev\wsl.ps1 <script> [args]` (it
converts the path and forwards the variables below). From a WSL shell, run
`bash <checkout>/port/tools/dev/<script>` directly.

A typical test cycle:

```powershell
$env:SOCOM_SCRATCH = 'build\port\boot-mywork'      # your scratch folder (lists, edits, logs)
.\port\tools\dev\wsl.ps1 tree.sh --fresh             # isolated tree = HEAD + copy.txt files
.\port\tools\dev\wsl.ps1 tb.sh -k stance stc1 pad_s1.txt   # tree, fake pad, stance test hook
.\port\tools\dev\run.ps1 -Build stc1 -Name stc1 -Seconds 90 -Shots "60,85"
.\port\tools\dev\wsl.ps1 default.sh mywork-default  # the normal build still links
```

## Environment

| variable | used by | meaning |
| --- | --- | --- |
| `SOCOM_PCSX2` | pcsx2-boot, pcsx2-record, run, socom-run | PCSX2 executable or its folder (required to boot) |
| `SOCOM_DISC_IMAGE` | pcsx2-boot, pcsx2-record, run, socom-run, iso.py | the game disc image (required to boot) |
| `SOCOM_WSL_DISTRO` | all WSL calls | WSL distribution (default: WSL's default), as `tools/_socom/port_toolchain.py` |
| `SOCOM_PS2DEV` | Linux-side scripts | pinned toolchain, default `$HOME/.local/share/socom/ps2dev-v2.0.0` (`python tools/socom.py port toolchain bootstrap`) |
| `SOCOM_SCRATCH` | all | your scratch folder: absolute, or relative to the checkout; default `build/port/dev` |
| `SOCOM_NAME` | Linux-side scripts | short worker name; default the scratch folder name without `boot-` |
| `SOCOM_TREE` / `TREE` | tree, fake, hook, tb, ccm, laycheck | isolated tree path / tree name under `~/.cache/socom` (default `tree-<name>`) |
| `SHARED` | tree.sh | another shared-edit list instead of `<scratch>/shared.txt` |
| `SOCOM_ELF` | ELF tools | reference ELF, default `support/socom.elf` |
| `SOCOM_DEV_CACHE` | DWARF tools | cache folder for `types.pkl`, default `build/port/cache` |

Emulator, disc image and BIOS paths are user-local: set them in your own shell or profile, never in
a tracked file, log or note.

## Tools

Reference ELF (`support/socom.elf`, read-only):

- `dx.ps1 <start> [end|+len]` - annotated disassembly of a function (PowerShell; size from the symbol table).
- `dis.sh [-z] [-r] <start> <end>` - raw objdump range (`-z` zero blocks, `-r` raw words).
- `disx.py` - annotates objdump output on stdin: lui/addiu and `$gp` targets with symbols and strings.
- `cz.py [-t reg=Class,...]` - compacts annotated output and names DWARF members on typed registers.
- `z.sh <start> <end|+size> [reg=Class]` - `dis.sh | disx.py | cz.py` (WSL, Linux or Git Bash).
- `nd.py` - on `cz.py` output: branches whose nop delay slot is followed by a real instruction.
- `zs.sh [-F] [-f file] <pattern> [n]` - search the cached full disassembly, with the containing function.
- `bitrd.sh <offset>` - `lbu` + `dsll32` bitfield readers of an offset.
- `od.sh <start> <end>` / `od.sh -h` - hex dump of ELF data / section headers.
- `sym.py <regex> | 0xADDR [n] | -s 0xVA...` - symbol lookup, word dump with pointer symbols, C strings.
- `symsize.py 0xADDR` - size of the symbol at an address (1024 when unknown).
- `xref.py 0xADDR...` - `jal` callers with their containing functions.
- `addrref.py 0xADDR...` - lui/addiu (lui/ori) pairs that build an address.
- `strref.py <regex>...` - strings matching a regex, with their code references.
- `fstr.py 0xADDR [n]` - strings and symbols a function references (hi/lo pairs and `$gp`).
- `fl.py 0xVA...` - 4-byte value as float / int / hex.
- `vt.py <vtable> <nslots>` - vtable slots to symbols.
- `sinitvals.py <asm> <off> [base]` - emulates a straight-line `__sinit` and prints the stored words.
- `ctree.py <addr> [depth] [--all]` - direct call tree with sizes and port status (W written, S stub).
- `reach.py <addr>... [--depth N]` - stubs reached from roots through written port functions.
- `animenum.py <value|name>...` - AnimType enumerator lookup (`src/gamez/zAnim/zanim.h`).

DWARF (rows generated once from `python tools/socom.py debug import-plan --rows`, cached):

- `dw.py <type>... [-a]` - compact DWARF layout of a type.
- `off.py <Class> <off>...` / `mem.py <Class> [off...]` - member at an offset (bases flattened).
- `denum.py <Enum>...` - DWARF enumerators.
- `lay.py <Class> <header>...` + `laycheck.sh [-a] <name>...` - compile-time port vs DWARF layout table.

Port source status (`src/` skeleton fences):

- `fences.py <regex>` - fence status (W/S/?) of functions; importable by the other tools.
- `status.py <mangled>... | -f <asm>` - port status of functions.
- `stubchk.py <regex>...` - which matching fences are still empty.
- `survey.py [file-regex]` - per file: fences with ELF address, size and status.
- `incpath.py <from-header> <to-suffix>` - include chains between headers.

Edits (on your own files or the isolated tree; keep each file's line endings):

- `rep.py <defs> [--dry]` - replace whole function definitions by fence name (`SOCOM_REP_ROOT` = tree).
- `srep.py <root> <edits>` - literal `@@@ file / old / @@= / new` replacements (`SREP_TOUCH=1` records them).
- `ed.py <edits>` - `=== FILE` / `<<< OLD` / `>>> NEW` block edits.
- `multi_replace.py <file> <edits>` - several fence-region replacements in one file.
- `splice.py <file> <marker> <tail>` - replace from a unique marker line to the end of a file.
- `fixnl.py <file>...` - repair inline-asm `\n\t` escapes broken by a shell layer; uniform line endings.
- `squash.py <decompile.c>` - compress Ghidra VU0 loops and copies in a decompile listing.
- `diag.py <tree> <spec>` - test-tree-only trace statements at the start of fenced functions.
- `stubcmd.py <tree>` - test-tree-only: empty command-tick stubs trace and `return 1`.

Isolated tree and builds (Linux side; `env.sh` holds the shared settings):

- `tree.sh [--fresh]` - isolated tree = HEAD + `copy.txt` files + `shared.txt` edits (+ `base.txt`).
- `fake.sh <build> <pad|->` - configure and link a fake-pad (or plain) build of the tree.
- `hook.sh <build> <pad> <source>... [-- flags]` - fake-pad build plus test-hook sources with `--wrap`.
- `tb.sh [-d spec] [-s] [-k feature|source] <build> <pad> [edits] [-- flags]` - the whole test-build pipeline.
- `default.sh <build>` - fresh default tree and normal link (no hooks, no fake pad, no test edits).
- `ccm.sh [-r] <src files>` - syntax check with the port flags (errors only).
- `ccs.sh <file.cpp> [tree]` - one unit to assembly with the port flags.

Port build ELF (`<build>` = a name under `~/.cache/socom`, a build dir or an ELF path):

- `a2l.sh <build> <addr>...` - function and file:line of addresses.
- `pdis.sh <build> <start> <end> | <build> <regex>` - disassembly of a range or of matching functions.
- `pnm.sh [-m] <build> <a,b,c>` - symbols matching patterns (`-m` mangled, game library).
- `pword.sh <build> <addr> [n]` - words with the symbols they point to.
- `hdr.sh <build>` - section headers. `chk.sh <build>...` - wrap count and fake-pad setting.
- `flags.sh <build>` - the game library compile flags. `errctx.sh <build> <pattern> [n]` - lib.log context.

Emulator and data (Windows side):

- `run.ps1 -Build <b> -Name <run> [-Seconds n] [-Shots "t1,t2"]` - copy the ELF out of WSL and boot it once.
- `pcsx2-boot.ps1 -Elf <elf> -Log <log> [-Seconds] [-Shots] [-ShotPrefix]` - batch boot on the
  secondary monitor without taking focus (PrintWindow screenshots, watchdog, stale-run cleanup).
- `pcsx2-record.ps1 ... -Video <mp4> [-From] [-To] [-StartPattern]` - the same plus a window-only clip (ffmpeg).
- `set-appvolume.ps1 -ProcessId <pid> [-Level 0.15]` - one process's slider in the Windows mixer.
- `socom-run.ps1 [-WorkingTree] [-SkipBuild] [-Monitor2] [-NoLaunch]` - build the normal game from HEAD
  (or the working tree) and play it in PCSX2 (GUI left running; log `build/port/play/last-run.log`).
- `lg.sh <log> [n] [regex]` - interesting lines of a boot log.
- `zoom.py <png> <x0> <y0> <x1> <y1> [scale] [out]` - crop and upscale a screenshot region (Pillow).
- `iso.py [<image>] [ls [prefix] | get <path> <out>]` - read-only ISO9660 walk of the disc image.
- `zar.py <file> [tree|get|hex]`, `rdr.py <zar> <name>`, `zseq.py <zar> <anim>` - read game archives
  extracted to your scratch folder (never commit disc data).

Test-hook headers (include from a hook, see `port/test-hooks/README.md`):

- `hook_freecam.h` - test camera: look at a point or follow a node for chosen frames, then give it back.
- `hook_skipcams.h` - skip the m8 mission cameras with SELECT; tells a pad script to wait while they run.

Shared settings: `_dev.py` (Python: repo root, ELF, scratch, DWARF cache), `env.sh` (bash),
`_dev.ps1` (PowerShell: emulator, disc, WSL calls), `wsl.ps1` (run a Linux-side script).
