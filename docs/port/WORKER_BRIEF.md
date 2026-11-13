# Port worker brief (functional port lane; untracked helper)

AGENTS.md is already in your context ("Functional port lane" section applies); don't re-read it.
You write game code in `src/` for the GCC/ps2sdk port so one system works in the emulator.

## Evidence and source rules
- Write bodies from the reference ELF: disassembly of `support/socom.elf` first, DWARF second,
  guesses last and flagged in a comment. Callees before callers.
- Keep stage-4 annotation blocks (`@socom-anchor`, `@socom-artifact`) and skeleton fences intact.
  Edit inside the fences; don't move functions between files.
- No shims/stubs in `src/` (those go under `port/compat/`). GCC-only spellings behind
  `#ifdef SOCOM_PORT` only where one spelling can't serve both compilers.
- ELF quirks are kept as the ELF has them; note them. Port deviations are noted too.
- Keep each file's existing line endings (`fixnl.py` in the tool folders).

## What you must not do
- No git commits, stashes, checkouts or resets. No tracker (`progress ...`) mutations. No Ghidra
  writes (read-only Ghidra use is fine but the ELF tools below are usually faster).
- Never record user-local paths (emulator, disc image, BIOS) in tracked files.
- Don't edit a file another worker owns: before your first edit of a file run
  `git status --short <file>`; if it is modified and not in your `mine.txt`, keep your change as
  an edit file in your scratch folder (`edits/*.txt`, applied to your test tree only) and list it
  in your report. The coordinator merges it.

## Scratch folder and tools
- Everything you create (scripts, logs, ELFs, notes) stays in your own folder
  `build/port/boot-<name>/`. Copy the tool set from `build/port/boot-fx/` or
  `build/port/boot-actions/` and fix the paths inside the scripts; their use is described in
  `build/port/boot-fx/NOTES.md` and `build/port/boot-weaponsel/NOTES.md` (dx.ps1/dis.sh/disx.py
  disassembly, sym.py, xref.py, dw.py DWARF, fences.py, lay.py/laycheck.sh layouts, rep.py edits,
  tree.sh isolated tree, fake.sh/hook.sh fake-pad builds, pad scripts).
- Build in WSL Ubuntu with the pinned toolchain (`$HOME/.local/share/socom/ps2dev-v2.0.0`), from an
  isolated tree `~/.cache/socom/tree-<name>` = HEAD (`git archive`) + the files in your `mine.txt`
  (so other workers' uncommitted work stays out). Call WSL from PowerShell:
  `wsl.exe -d Ubuntu -- bash <script>`.
- `mine.txt`: repo-relative list of every tracked file you changed; keep it current.

## Emulator runs
- Boot only through `build/port/tools/pcsx2-boot.ps1` (second monitor, never takes focus, low
  volume). Copy the ELF out of WSL first. Never call SetForegroundWindow. Batch your checks: few
  runs, each answering several questions. Prefer log traces (`SOCOM_PORT_TRACE_ON`) to screenshots.
- The disc image argument and PCSX2 path come from the helper/environment; don't hardcode them.

## Before you finish
- A default build (your tree, no hooks, no fake pad) links and boots to the main menu, and a
  fake-pad run shows the system working in mission m8 (the standard START path pad is in the notes).
- Copy the few screenshots that show the result to `build/port/screenshots/<NN-milestone>/` as
  `<yyyy-MM-dd_HHmmss>_<label>.png` (next free number for a new milestone).
- Write `NOTES.md` in your scratch folder: root causes, what was written (with ELF addresses),
  results, ELF quirks kept, port deviations, what is not written / next.
- Final report to the coordinator: at most 10 lines - what works (with the log/screenshot that
  shows it), what doesn't, files changed (= mine.txt), edit files for shared files, open questions.

## Checkpoints (usage limits can cut you off without warning)
- Keep `NOTES.md` current as you go, with a short "State / next step" section at the top: what
  is written, what the last run showed, what you were about to do. A fresh worker must be able to
  continue from NOTES.md, mine.txt and edits/ alone.
- In the final report list the full paths of the 3-6 screenshots that best show the result (the
  coordinator uploads them to the user).

## Feature clip: not wanted any more (user, 2026-11-12)
- Don't record clips. Screenshots in the milestone folder are the visual record; list the full
  paths of the 2-3 that best show the result in your final report.

## Test camera (user, 2026-11-12)
- When a test needs a clear view of the thing under test (an enemy across the map, a decal on a
  wall, a dropped item, a door from outside), don't steer the player there just to look: in your
  test hook file, detach the camera from the player (unparent the camera node from the player node
  / stop the follow camera driving it) and place and aim it yourself at the target for those frames,
  then put it back.
- Keep all of it inside the test hook source file you already use (`hook_*.cpp`, scratch only,
  linked with --wrap): nothing for it in `src/` or `port/`. If you write a reusable piece (e.g.
  "look at node/point from offset"), put it in `build/port/tools/hook_freecam.h` so the next
  worker includes it instead of rewriting it, and say so in NOTES.md.
