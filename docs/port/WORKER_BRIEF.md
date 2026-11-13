# Port worker brief

`AGENTS.md` is already in your context ("Functional port lane" section applies); don't re-read it.
You write game code in `src/` for the GCC/ps2sdk port so one system works in the emulator.

## Evidence and source rules
- Write bodies from the reference ELF: disassembly of `support/socom.elf` first, DWARF second,
  guesses last and flagged in a comment. Callees before callers.
- Keep stage-4 annotation blocks (`@socom-anchor`, `@socom-artifact`) and skeleton fences intact.
  Edit inside the fences; don't move functions between files.
- No shims/stubs in `src/` (those go under `port/compat/`). GCC-only spellings behind
  `#ifdef SOCOM_PORT` only where one spelling can't serve both compilers.
- ELF quirks are kept as the ELF has them; note them. Port deviations are noted too.
- Keep each file's existing line endings (`port/tools/dev/fixnl.py`).

## What you must not do
- No git commits, stashes, checkouts or resets. No tracker (`progress ...`) mutations. No Ghidra
  writes (read-only Ghidra use is fine but the ELF tools below are usually faster).
- Never record user-local paths (emulator, disc image, BIOS) in tracked files.
- Don't edit a file another worker owns: before your first edit of a file run
  `git status --short <file>`; if it is modified and not in your `mine.txt`, keep your change as
  an edit file in your scratch folder (`edits/*.txt`, applied to your test tree only) and list it
  in your report. The coordinator merges it.

## Scratch folder and tools
- Everything you create (edit files, logs, test builds, notes in progress) stays in your own
  scratch folder under the ignored `build/`, e.g. `build/port/boot-<name>/`; point
  `SOCOM_SCRATCH` at it.
- The tools are in `port/tools/dev/` (see its `README.md`): `dx.ps1` / `z.sh` / `dis.sh`
  disassembly, `sym.py`, `xref.py`, `dw.py` DWARF, `fences.py`, `stubchk.py`, `survey.py`,
  `lay.py` / `laycheck.sh` layouts, `rep.py` / `srep.py` edits, `tree.sh` isolated tree,
  `fake.sh` / `hook.sh` / `tb.sh` test builds, `default.sh` normal build check. Use them from
  there; don't copy them into your scratch folder.
- Build on the Linux side with the pinned toolchain, from an isolated tree
  (`tree.sh`: HEAD plus the files in your `mine.txt`, so other workers' uncommitted work stays
  out). From PowerShell, run Linux-side scripts through `port/tools/dev/wsl.ps1`.
- `mine.txt`: repo-relative list of every tracked file you changed; keep it current.
- Earlier work is described per feature in `docs/port/notes/`; read the notes for the systems
  you touch before you start.

## Emulator runs
- Boot only through `port/tools/dev/run.ps1` / `pcsx2-boot.ps1` (second monitor, never takes
  focus, low volume). They read the emulator and disc image from `SOCOM_PCSX2` and
  `SOCOM_DISC_IMAGE`; don't hardcode either. Batch your checks: few runs, each answering several
  questions. Prefer log traces (`SOCOM_PORT_TRACE_ON`) to screenshots.
- Pass absolute paths for the ELF and the log: a relative ELF path boots to a black screen.
- Test hooks and pad scripts for existing features are in `port/test-hooks/<feature>/`; a new
  feature's hook goes there too when it lands. Hooks are test-only (`--wrap`), never part of a
  normal build.
- In mission m8 the intro movie plays first (CROSS skips it), then the briefing cameras for 21 s
  (the on-screen skip is X; a held SELECT skips them and also opens the map, which pauses the
  game until closed). `port/tools/dev/hook_skipcams.h` lets a hook get through them.

## Test camera
- When a test needs a clear view of the thing under test (an enemy across the map, a decal on a
  wall, a dropped item, a door from outside), don't steer the player there just to look: in your
  test hook file, detach the camera from the player and place and aim it yourself at the target
  for those frames, then put it back. `port/tools/dev/hook_freecam.h` does this.
- Keep all of it inside the test hook source file: nothing for it in `src/` or `port/compat/`.

## Checkpoints (usage limits can cut you off without warning)
- Keep a `NOTES.md` in your scratch folder current as you go, with a short "State / next step"
  section at the top: what is written, what the last run showed, what you were about to do. A
  fresh worker must be able to continue from NOTES.md, mine.txt and edits/ alone.

## Before you finish
- A default build (your tree, no hooks, no fake pad) links and boots to the main menu, and a
  fake-pad run shows the system working in mission m8.
- Copy the two or three screenshots that best show the result to a milestone folder under your
  scratch area, named `<yyyy-MM-dd_HHmmss>_<label>.png`. Screenshots show game content and stay
  untracked.
- Finish `NOTES.md`: root causes, what was written (with ELF addresses), results, ELF quirks
  kept, port deviations, what is not written / next. The coordinator files it under
  `docs/port/notes/` when the work is committed.
- Final report to the coordinator: at most 10 lines - what works (with the log or screenshot
  that shows it), what doesn't, files changed (= mine.txt), edit files for shared files, open
  questions, and the full paths of the screenshots.
