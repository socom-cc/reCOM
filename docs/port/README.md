# Functional port documentation

The functional port builds the game from `src/` with the open-source ps2dev
toolchain (see [PORT_TOOLCHAIN.md](../reconstruction/PORT_TOOLCHAIN.md) and the
"Functional port lane" section of `AGENTS.md`). It is a separate lane from the
matching stages and never substitutes for their evidence.

| File | What it is |
| --- | --- |
| [PROPOSAL.md](PROPOSAL.md) | The original plan for the port lane. |
| [WORKER_BRIEF.md](WORKER_BRIEF.md) | The rules every port worker follows. |
| [notes/](notes/) | One note per feature, written by the worker that built it. |

## Reading a feature note

Each note records the root causes found, the functions written with their
addresses in the reference executable, the results of the test runs, quirks of
the original that were kept on purpose, deviations the port makes, and what is
not written yet.

The notes were written in each worker's scratch folder, so they name files that
are **not in the repository**: emulator logs (`ec3.log`), screenshots, test
builds, and paths such as `build/port/boot-<feature>/`. `build/` is ignored;
those files are local evidence from the machine the work was done on. Treat the
log names and timestamps as a record of what was observed, not as something you
can open.

The tools and test hooks the notes mention live under `port/tools/dev/` and
`port/test-hooks/`.

## Test data

The disc image used for all of this work is a demo with a single mission,
`run/sp/m8`. Anything that needs another mission (ladders, night vision,
next-mission unlock) is written but untested.
