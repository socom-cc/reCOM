# Functional port lane - proposal (2026-11-05)

Status: draft for the user. Nothing in src/, the tracker or AGENTS.md has changed for this yet.

## Goal

Build a working PS2 ELF from the reconstructed C/C++ in `src/` with the open-source ps2dev
toolchain (GCC 15.2.0 + ps2sdk, release v2.0.0). It runs in PCSX2 with the user's own disc data,
offline first. It is never byte-identical to `support/socom.elf` and claims nothing about order,
ABI or bytes.

## How it fits the existing plan

- A separate lane next to the matching chain, not a replacement. The Metrowerks license blocker
  stays visible; stage 5 Phase C and stages 6-10 stay blocked until lawful compiler access exists.
- `src/` stays the single game source shared by both lanes. Port-only code (SDK compatibility
  layer, CMake build, boot glue) lives in a new top-level `port/`. GCC-only fixes in `src/` go
  behind `#ifdef SOCOM_PORT` only where both compilers can't share one spelling.
- AGENTS.md amendment (needs your approval): add the lane and its done criteria; sanctioned
  compatibility shims live only under `port/` (`guard provider` keeps rejecting shims in `src/`);
  port evidence never counts as matching evidence.

## Facts gathered

- Toolchain installed in WSL Ubuntu at `$HOME/.local/share/socom/ps2dev-v2.0.0`, archive
  SHA-256 checked. A C++ probe (virtuals, global constructor, new/delete, float math) builds to an
  ELF32 LE R5900 image loading at 0x00100000 (the game's base too); two builds are identical.
  Your separate `/usr/local/ps2dev` is untouched. CLI commands `port toolchain bootstrap|verify`
  are being added.
- src/: 250 C/C++ files, 979 function bodies, 5,684 stubs (functions and data) from stage 5.
- Outside-library code linked into the game: 2,960 functions. Game code calls 440 of them
  directly: SCE 173, Medius 91, newlib 60, 989snd 41, libptt 21, speech middleware 18, MSL 13,
  MW runtime 11, libgcc 9, unidentified 2.
- IOP modules the game loads (29 names): Sony SIO2MAN/PADMAN/MCMAN/MCSERV/LIBSD/USBD/DEV9, the
  989 sound modules 989SND/989DSTRM/SDRDRV, the headset module lgAud, and 14 network modules
  under `run/irx/`.
- Source constructs that need GCC attention: 14 files use 128-bit types; no inline asm in the
  written bodies yet (the assembly-heavy functions are still stubs).

## Phases

P0 Environment (in progress). Pinned toolchain, `port toolchain verify`, PCSX2 path in env
`SOCOM_PCSX2` (never in tracked files), BIOS from your console as you already configure it.

P1 Everything compiles. `port/CMakeLists.txt` builds every src/ unit with GCC into one ELF, with
stubs as they are. Fix GCC incompatibilities in shared headers; fix the two known skeleton
defects first (dynamic initializers written as `= {0}`; float tables typed as byte arrays).
Layout check: generate `static_assert(sizeof/offsetof)` for every DWARF class and struct, so GCC
proves the same layouts the game's data files and code rely on. Output: the list of undefined
outside-library symbols = the compatibility layer's work list.

P2 Boots to main(). ps2sdk startup, IOP reset and module loading (ps2sdk's own SIO2MAN, PADMAN,
MCMAN, MCSERV, LIBSD), disc file access through ps2sdk cdvd, heap. Boot milestones are logged over
the EE debug output and checked in PCSX2.

P3 Compatibility layer `port/compat/`: the 173 SCE calls mapped onto ps2sdk; newlib/MSL/MW
runtime/libgcc replaced by GCC's own libraries; online (Medius, RSA, libptt) and voice (speech,
lgAud) as explicit offline stubs reporting "unavailable"; sound per decision 1.

P4 Function bodies, in boot order (main -> init -> front end -> mission load -> gameplay), callee
first. Bodies come from accepted Ghidra semantics and DWARF types, written for behaviour, not bytes.
Each unit must compile without warnings in a set we agree on; each milestone must run in PCSX2.

P5 Behaviour checks. Scripted PCSX2 runs per milestone (boot, front end, mission load, a short
scripted play) with logs and screenshots kept under build/; promoted to tracker evidence through
`socom-functional-targets`.

## Tracker and tools

- New lane producer and items (per P1 unit group, per compat library, per P4 unit, per P5
  milestone) via tool-maintainer work; same claim, handoff, independent-accept flow.
- Commands to add later: `port build`, `port layout-check`, `port run --milestone <m>`.

## Decisions for you

1. Sound: (a) re-implement the 41-function 989snd client against the disc's own 989SND.IRX
   (keeps original audio behaviour, harder), or (b) replace with ps2sdk audsrv (quicker, needs
   the game's sound banks converted or played differently). Recommended: start with silent stubs,
   decide at P4 front end.
2. Online and voice: stub out (recommended; the servers are gone).
3. Layout: `port/` for port-only code and `src/` shared (recommended).

## Risks

- Scale: about 5,600 functions to write. Boot order lets a partial port run early.
- Structure layout or alignment mismatches (64/128-bit members) break data loading; P1's layout
  check catches them before any run.
- Code that relies on Metrowerks-specific vtable, RTTI or calling details needs rewriting.
- The ELF needs your own disc data to run; nothing from the disc is committed.
