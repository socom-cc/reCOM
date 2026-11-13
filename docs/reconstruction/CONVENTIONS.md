# Project conventions

Decisions the maintainer has made that are not derivable from the executable or
from the tools, and working practices that proved themselves. `AGENTS.md` stays
authoritative; this file records choices made within its rules. Each entry
gives the date it was settled.

## Naming

- **Original spellings win.** DWARF and symbol-table names are kept exactly.
  The rules below apply only to names that had to be invented.
- **Invented members** are `m_` plus lower snake case, with short forms:
  `m_ref_count`, `m_clone_src`, `m_mesh_decals`. `m_vtype` is the one accepted
  exception (2026-10-23).
- **Unknown members** stay `m_unk<offset>` until someone names them. When
  proposing a name, show every read and write of the field (site, instruction,
  function, constants).
- **Byte flags are `bool`.** A one-byte global or member that is only tested
  against zero, stored 0/1 or a comparison result, or passed as a bool
  parameter is typed `bool`, not `uchar`. Counts and bytes used in arithmetic
  stay `uchar`/`char` (2026-10-24).
- **Base-class components** are named after the base type alone (`CGame`), not
  `super_CGame` (2026-10-09). Components created earlier with the prefix are
  renamed only through a governed change.
- **Virtual table pointer members** are named `__vt` in every class
  (2026-10-16). The vtable struct type is `<Class>_vtbl` by default.
- **Node types.** `zdb::tag_NODE_PARAMS::m_type` values are proven from code;
  the enum names are provisional: 1 `NODE_DEFAULT`, 2 `NODE_INSTANCE`,
  3 `NODE_XREF`, 6 `NODE_WORLD`, 7 `NODE_MODEL`, 8 `NODE_LIGHT`,
  9 `NODE_LENSFLARE`, 10 `NODE_CELL`; 4 and 5 appear only in level data.

## Source tree placement

- **Mirror the original tree.** Surviving debug paths have the form
  `Z:\dev\gamez\<module>\<file>`; a file such as `node_main.cpp` from module
  `znode` belongs at `src/gamez/znode/node_main.cpp`, lower case (2026-10-18).
  The application layer keeps its `src/Apps/FTS/{hud,game,state}/` subfolders.
- **Headers.** The module's public header is `z<module>.h`. Topic headers
  (`zmath_matrix.h`) and private headers (`zrdr_local.h`) exist where the
  executable shows them. Do not invent per-file headers: DWARF 1 has no include
  list, so a missing header is unknown, not disproven. A header that holds
  inline code is a hard constraint.
- **A `__FILE__` string names its file.** Example: `CNodeAction`'s functions
  live in `fts_action.cpp` because one of them references that literal.
- **Classes get class-named files.** Most classes are split into a file named
  after the class in the module's style: `C2DBitmap` in `ztwod_bitmap.cpp`.
  Suggest that file before falling back to address neighbours (2026-11-05).
  Inline compiler copies are the exception: they belong to the object that
  used them.
- **Objects with no recoverable name are still owned** (2026-10-31). If exactly
  one existing file in the module already defines the functions, use it
  (confidence medium). Otherwise invent a descriptive name from the main class
  (confidence low, marked invented). One file with a note when one-versus-two
  objects is unproven.
- **Placement changes are governed.** Moving an owner or a header goes through
  a source-correlation amendment and is checked against the binary.

## Type recovery

- **No DWARF class means code-derived layout.** `zdb::CVisual` and its family
  have no class record; their layouts come from instruction evidence, with
  invented provisional names, and the maintainer reviews such a layout before
  it is applied.
- **Sub-word returns need proof inside the callee.** Metrowerks narrows byte
  and short returns in the callee, so narrowing in a caller only shows the
  destination's width. Entries of one function-pointer table share a declared
  type: one entry's own narrowing proves the width for all, unless another
  entry contradicts it (2026-10-24).
- **zAnim command records.** The begin, tick and end handlers of each command
  cast the `_zanim_cmd_hdr *` they receive to a per-command record. Those
  record types are recovered per layout family from the parser's allocation
  size and the offsets the handlers use.
- **Vtables.** Layout is RTTI pointer, offset-to-top, destructor, then the
  virtuals in order; 21 vtables carry a secondary sub-table. The vptr offset
  varies per class and is proven per class from the constructor's store.

## Ghidra bridge

- **Measure an endpoint's effect before relying on it.** Read the plugin's
  implementation or compare state before and after. `run_analysis` reanalyses
  all initialised memory; treat every POST endpoint as a write.

## Test data

- **The disc image used for the port is a demo** (May 2002) with one mission,
  `run/sp/m8`. It has no ladders, no restrainable enemy, no night mission and
  no smoke or tear-gas grenade in its kit, so code for those is marked
  "written, untested" where it exists.

## Working with sub-agents

- **At most three at once**, each with a small scope and a fresh context.
- **Every agent gets its own scratch folder** under the ignored `build/`.
  Shared scratch let one agent's script overwrite another's.
- **Workers never commit and never accept their own work.** The coordinator
  reviews, commits by the worker's file list, and builds from the commit.
- **Shared files between running workers** are handled with edit files: the
  worker keeps its change as a replacement block applied to its own test tree,
  and the coordinator merges it when the file's owner has landed.
- **Port test boots** go through the boot helper: second monitor, never take
  focus, reduced volume, few and batched runs.
- **Test hooks may move the camera.** A test hook can detach the camera from
  the player and aim it at the thing under test. That code stays in the hook
  file.
- **Decision sheets** for placement questions are Markdown files with one
  `##` heading per destination file; lines are moved between headings.
