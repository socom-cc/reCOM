# Stage 5: authored function order

`authored-function-order` reproduces the authored physical contribution
order: every authored object file must compile to an object whose functions
and data appear in the same order as in `socom.elf`, and the authored objects
must link in the ELF's order. Calling conventions (stage 6), bytes (stage 7)
and provider order (stage 8) are later stages.

The design is the approved stage 5 proposal of 2026-11-01. The user's
decisions: start phase A now; stage 5 orders **definitions** only, the
functions and data a file defines (D3); inline, WEAK and template copies and
literals are recorded as targets and verified in stage 7, when real bodies
emit them; the 46 stage 4 segments are the item unit (D6).

## Phases

**Phase A, no compiler (file-only).** A1, the order target, and A3, the
link-order specification, are registered (`order target`,
`order link-spec`, `order sql`; capability `function-order-targets` in
[TOOL_COVERAGE.md](TOOL_COVERAGE.md)). A2's evidence drafts are registered
too (`order draft`, see [Source-order drafts](#source-order-drafts-and-the-calibration));
the order plans drafted from them and their independent review per segment,
and A4 (a governed correction route for accepted stage 4 plans), are not
built yet.

**Phase B, needs the exact compiler.** A probe harness compiles a unit and
reads its object's section and symbol order (B1), the emission rule is
calibrated on units whose source order DWARF records (B2), source is
arranged to the accepted plan (B3) and an independent verifier builds each
unit from a clean checkout (B4). `mwccps2` stops at the FLEXlm check
(blocker `socom:blocker:metrowerks-flexlm-license`, the user's to resolve),
so phase B waits.

None of these commands opens the stage. The stage 5 seed stays a closed
placeholder until its plan, compile and verify routes are registered.

## Inputs

- Every accepted stage 4 owner plan, read through the same check as the
  apply route: the plan's current SHA-256 must be one its accepted item
  cites. Segment plans and data reconciles give the authored units; one unit
  may be owned in several plans, and its rows are merged by translation unit;
  its `primary_segment` is the segment plan owning most of its artifacts
  (where a segment item plans it once).
  Provider plans give the provider objects: a GNU object (`<library>:gnu@<address>`)
  or a named member (`<library>:<object>`).
- Stage 4's decomposition graph (`build/source-graph/graph.json`; the
  command refuses another graph) and its artifacts.
- The gate's recorded deferrals (the `source_gate` record on the stage 4
  gate item): the deferral ID is the category of each unresolved row.
- The ELF's GLOBAL linker section symbols (`_dataStart`, `__data_start`,
  `__static_init`, `__static_init_end`, `__data_end`, `_fbss`,
  `__bss_start`, `__bss_end`, `_heapStart`, `_end`).

The target records the plan digests, the stage 4 file baseline and the plans
whose SHA-256 differs from the one that baseline records
(`changed_since_baseline`).

## Regions

`socom.elf` has one loaded section, `main`, so output sections are not named
in the file. A **region** is a run of artifacts with one graph window, one
input-section envelope (from the GNU objects' LOCAL section symbols: `.data`,
or `between .rodata and .sdata`) and one fill kind (file bytes or the
window's zero-fill tail). A linker section symbol opens a new region at the
artifact that holds or follows it. The label is the envelope text, with
`from <symbol>` when a symbol opened it and `#N` when it would repeat. A
region holding COMMON allocations is `common`: the linker places COMMON after
every input section, so it is not checked for object order.

Measured on the graph `c79d76e6...` (functions/data/gaps; objects present;
authored units present; `.text`-order drops):

| # | Region | Range | F/D/G | Objects | Units | Drops |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `between start and .text` | `0x100000`-`0x140008` | 0/2/1 | 1 | 1 | 0 |
| 2 | `.text` | `0x140008`-`0x425f68` | 9547/0/6397 | 607 | 216 | 0 |
| 3 | `between .text and .vutext` | `0x425f68`-`0x426464` | 8/0/4 | 1 | 0 | 0 |
| 4 | `between .text and .vutext #2` | `0x426464`-`0x426480` | 0/0/1 | 0 | 0 | 0 |
| 5 | `.vutext` | `0x426480`-`0x42af60` | 0/0/2 | 0 | 0 | 0 |
| 6 | `between .vutext and .data from _dataStart` | `0x42af60`-`0x42af61` | 0/1/0 | 0 | 0 | 0 |
| 7 | `between .vutext and .data from __data_start` | `0x42af61`-`0x42b290` | 0/5/3 | 2 | 0 | 0 |
| 8 | `.data` | `0x42b290`-`0x43e2e8` | 0/390/150 | 94 | 36 | 0 |
| 9 | `between .data and .vudata` | `0x43e2e8`-`0x43e300` | 0/1/1 | 1 | 0 | 0 |
| 10 | `.vudata` | `0x43e300`-`0x444480` | 0/0/3 | 0 | 0 | 0 |
| 11 | `between .vudata and .rodata` | `0x444480`-`0x4450d8` | 0/128/89 | 6 | 1 | 0 |
| 12 | `.rodata` | `0x4450d8`-`0x4692c8` | 0/6074/4919 | 310 | 196 | 0 |
| 13 | `.rodata #2` | `0x4692c8`-`0x469e80` | 0/0/4 | 4 | 0 | 0 |
| 14 | `between .rodata and .sdata` | `0x469e80`-`0x471258` | 148/0/87 | 148 | 146 | 0 |
| 15 | `between .rodata and .sdata #2` | `0x471258`-`0x471260` | 0/0/1 | 0 | 0 | 0 |
| 16 | `between .rodata and .sdata from __static_init` | `0x471260`-`0x4714b0` | 0/148/0 | 148 | 146 | 0 |
| 17 | `between .rodata and .sdata from __static_init_end` | `0x4714b0`-`0x474b7c` | 0/248/162 | 100 | 95 | 0 |
| 18 | `between .rodata and .sdata from __data_end` | `0x474b7c`-`0x4755d8` | 0/611/282 | 102 | 90 | 0 |
| 19 | `.sdata` | `0x4755d8`-`0x4755e4` | 0/2/1 | 2 | 0 | 0 |
| 20 | `between .sdata and .bss` | `0x4755e4`-`0x475600` | 0/0/1 | 1 | 0 | 0 |
| 21 | `between .sdata and .bss from _fbss` | `0x475600`-`0x476d25` | 0/1404/577 | 151 | 143 | 0 |
| 22 | `between .sdata and .bss from __bss_start` | `0x476d25`-`0x476d80` | 0/0/1 | 0 | 0 | 0 |
| 23 | `.bss` | `0x476d80`-`0x5b17c0` | 0/914/707 | 198 | 159 | 0 |
| 24 | `between .bss and .vubss` (COMMON) | `0x5b17c0`-`0x5e7e98` | 0/250/4 | 0 | 0 | skipped |
| 25 | `.vubss from __bss_end/_heapStart` | `0x5e7f00`-`0x5e7f04` | 0/1/0 | 0 | 0 | 0 |

Inference, not a tool fact: by their contents and the linker symbols, region
14 holds the `__sinit_*` static-initializer functions, 16 the `.p__sinit_*`
table (`__static_init`..`__static_init_end`), 17 the vtables up to
`__data_end`, 18 and 19 the small data, 21 `.sbss` (`_fbss`..`__bss_start`),
23 `.bss` and 24 COMMON. Labels stay evidence-based; phase B probes will name
the compiler's sections.

## Order classes

Each artifact a unit owns gets one class:

| Class | What | Verified in |
| --- | --- | --- |
| `definition` | a function or data object the unit defines (GLOBAL or LOCAL, not a copy); `generated: true` marks the compiler-emitted ones (`__vt__`, `__RTTI__`, `__sinit_`, `.p__sinit_`) | stage 5 |
| `copy` | a kept inline (binding 13, `@N@` this-adjusting thunks included) or WEAK copy, a header-emitted instance (its `header` is shown), or another template instance (a function template or a class template member, by its mangled name) | stage 7 |
| `literal` | a data object labelled `@N`: the literal pool (strings, floats, tables) | stage 7 |
| `compiler-generated` | fill and padding inside one of the unit's runs | stage 7 |

On the graph `c79d76e6...` the 219 authored units own 7,696 definitions
(4,801 functions and 2,895 data objects; 866 of them generated), 1,865
copies (1,734 functions), 5,742 literals and 10,661 fill gaps inside their
runs.

## Runs, the global order and the checks

An object's contribution to a region is a list of **runs**: consecutive
artifacts it owns, where fill and unresolved rows do not break a run. The
largest run (the first of equals) is the **main run**: it places the object
in the region; artifacts in other runs are **strays**. Each region's object
sequence is the objects ordered by main-run start.

The `.text` order ranks objects by main-run start in the first code window.
The **global object order** is that order, with every object that has no
code there (data-only objects, units whose only code is a static
initializer) inserted, in address order of its first appearance, right after
the latest object that precedes it in any region it shares (or before the
earliest that follows it). Every region is then checked:

- **object-order drops**: adjacent objects whose `.text` ranks decrease
  (`out_of_order` is how many objects a consistent order would drop);
- **link violations**: adjacent objects in reverse global order;
- **split contributions**: objects with more than one run.

Findings per authored unit:

- `interleaved`: the unit has more than one run in a region; the finding
  gives the strays' classes and the objects between the runs;
- `deferred-in-span`: an unresolved stage 4 row lies inside one of the unit's
  runs, named with its gate deferral category.

## Commands

```powershell
python tools/socom.py order target --output build/stage5/order-target.json
python tools/socom.py order target --unit database.cpp
python tools/socom.py order target --segment 13 --output build/stage5/segment-013.json
python tools/socom.py order link-spec --output build/stage5/link-order.json
python tools/socom.py order draft --output build/stage5/order-draft.json
python tools/socom.py order draft --unit hud_main.cpp
python tools/socom.py order sql "SELECT label, objects, drops, link_violations FROM checks WHERE objects > 0"
```

`order target` with no selection prints the counts and the first findings;
`--output` writes the whole target (or a selection's view: its units, the
regions they touch and their findings). The target's `order_sha256` is the
SHA-256 of its canonical JSON without that field, so it changes with any
input. `order link-spec` writes the `socom-link-order` JSON (objects in
order, each with its source path or archive member, `link_order_sha256`
over the list and the static check) and a plain list (`--text`, default the
output with `.txt`: one source path or `library(member)` per line); it exits
1 when a region violates the order. `order sql` runs one read-only
SELECT/WITH over `build/cache/order-target.sqlite`, rebuilt when the graph
file, the cited plans or the gate deferrals change:

| Table | Rows |
| --- | --- |
| `regions` | `region`, `label`, `window`, `window_kind`, `start`, `end`, `nobits`, `common`, `opened_by`, `functions`, `data`, `gaps` |
| `objects` | link `position`, `object`, `kind` (authored or provider), `library`, `workspace_path`, `original_path`, `member`, link-list `entry`, `plans`, `segments`, `primary_segment` (the segment plan owning most of its artifacts), `text_position` |
| `contributions` | `object`, `position`, `region`, `label`, `first`, `end`, `count`, `runs` |
| `targets` | every artifact a unit owns, and its interior fill: `artifact`, `unit`, `region`, `label`, `ordinal`, `address`, `size`, `kind`, `name`, `binding`, `class`, `generated`, `header`, `plan` |
| `findings` | `kind`, `unit`, `region`, `label`, `artifact`, `category`, `item`, `runs`, `intruders`, `drops`, `out_of_order` |
| `checks` | per region: `checked`, `objects`, `compared`, `drops`, `out_of_order`, `link_violations`, `split_objects`, `reason` |

## Measured order evidence

From stage 4 (the proposal):

- **Source order from DWARF lines.** The proposal's figure (43 units, 75%
  of neighbour steps backwards, a tendency rather than a rule) is
  superseded by the [calibration](#source-order-drafts-and-the-calibration),
  which reads each definition's own line (the first row of its line table)
  and leaves copies out: out-of-line definitions run in exact reverse
  source order.
- **Literal label numbers** (`@N`, a per-unit compiler counter) never drop
  by more than 51 within one unit along `.rodata` (0 of 4,550 pairs), so they
  record the order the compiler emitted code (the calibration shows that
  this is the address order, not the source order).
- **Data order**: `.sdata`, `.sbss` and `.bss` keep link order; LOCAL symbol
  names keep one order across objects (6,970 of 6,970 shared pairs);
  static-initializer order is known for 148 units.
- **Copies**: WEAK copies sit at the end of their object (161 of 162); a
  kept inline copy comes from the first unit in link order that defines it
  (0 counterexamples in 2,609).

From `order target` on the graph `c79d76e6...` and the 62 accepted plans
(order digest `4c79cd00...`):

- 219 authored units and 402 provider objects (621 objects) in 25 regions;
  no artifact is outside every plan and none is owned twice.
- **Object order is one sequence.** No region's main-run order disagrees
  with `.text` (0 drops), and the merged order has 0 link violations in the
  24 checked regions, so the link-order file is consistent with the ELF.
- **Two split contributions, both copies.** seal_ai.cpp's kept local-static
  copies of the inline `CAiPath::next()`, `init$localstatic4$next__7CAiPathFv`
  (0x475600, the first `.sbss` object) and `dummy$localstatic3$next__7CAiPathFv`
  (0x476ec8, before main.cpp's `.bss`), lie at the head of their regions,
  ahead of every object. No definition is interleaved. A kept binding-13
  data copy may be placed by the linker rather than with its object; stage 7
  must settle it.
- **Four deferred rows inside units' runs**, all `data-link-order`: 0x44cd78
  and 0x44cd80 inside ent_main.cpp's `.rodata` run, 0x450d30 inside
  seal.cpp's and 0x474f60 inside seal_ai.cpp's small-data run. The other
  557 unresolved rows (160 boundary functions, 250 COMMON variables, 95
  data-link-order, 8 microcode/fill/linker, 44 unproven-object functions)
  lie between units.

## Source-order drafts and the calibration

The order target fixes the order the ELF requires; phase B must write
source that the compiler turns into it. `order draft` (read-only; it also
reads the source cache, `build/cache/source-graph.sqlite`) collects the
evidence for the **source** order of each unit's definitions, calibrates
it, and drafts a hypothesis source order for the A2 planners. It decides
nothing: compiler probes (phase B) settle the rule.

### Evidence

| Evidence | What it is |
| --- | --- |
| DWARF lines | each function's definition line: the first row of its line table (only in its own unit's compile units) |
| local-static counter | function-local statics are named `name$N` (with a guard `init$N` when dynamically initialized), N a per-unit counter; a function's value is the lowest N among the statics no other function of its unit references; a static's own name carries its N |
| literal labels | the highest `@N` among the literals only that function references (the same counter) |
| static initializer | the order in which the unit's `__sinit_` function first references each data definition (C++ initializes a unit's objects in definition order) |
| DWARF variable order | file-scope variable DIEs of the unit's object contribution, in DIE order |

`$localstatic` names (`init$localstatic4$next__7CAiPathFv`) number the
statics of one inline function and belong to copies; `@unnamed@` tags name
a file's anonymous namespace without a counter. Neither orders definitions.

### Calibration

Measured over the target `4c79cd00...` (graph `c79d76e6...`). DWARF lines
order 464 definitions in 36 units (35 with three or more): 4,268 pairs,
428 neighbour steps.

| Evidence | Relation tested | Agreement |
| --- | --- | --- |
| reverse address order | a lower address is later in source | 4,251/4,268 pairs (99.6%), 426/428 steps, 35/36 units exact |
| forward address order | a lower address is earlier in source | 17/4,268 |
| local-static counter | a lower N is earlier in source | 16/16 pairs |
| literal labels | a lower `@N` is earlier in source | 3/102 (99/102 reversed) |
| local-static counter, every unit | a lower address has a higher N | 374/378 pairs |
| literal labels, every unit | a lower address has a lower `@N` | 3,783/4,087 pairs (92.6%) |
| data: own local-static N | a lower N lies at a lower address | 2,974/2,974 pairs |
| data: static initializer | initialized earlier lies at a lower address | 2,241/2,268 pairs (98.8%) |
| data: DWARF variable order | an earlier DIE lies at a lower address | 868/868 pairs |
| function compile-unit DIEs | an earlier DIE has a lower address | 800/800 steps |

The rule this supports (`calibration.best_rule` in the draft):

1. **Out-of-line function definitions are emitted in reverse source
   order.** The local-static counter confirms it on units without DWARF
   (374/378).
2. **Functions emitted on demand have no source position.** All 17
   discordant pairs involve three of the four LOCAL members of
   hud_linemap.cpp's anonymous-namespace class `CAiLinePtItr`, each defined
   on one line (lines 36-42: in-class bodies). `FindValid` (42) and
   `IsValid` (38) sit right after `TickLine`, FindValid's first user;
   `Advance` (36) and `GetPt` (37) follow the unit's last out-of-line
   definition, in forward order. They behave like kept inline copies: 609
   of the 668 binding-13 copies
   with a user in their unit sit right after the first function that
   uses it (56 before it). The nine definitions without a DWARF line in
   line-numbered units are compiler-generated: five `__arraydtor$N` and
   four implicit destructors of file-local classes.
3. **Counters.** The local-static counter follows source order. Literal
   labels follow the emission order (they run opposite to the source
   order), so they corroborate the address order but are not independent
   source evidence; neither is DIE order, which is the emission order for
   functions.
4. **Data definitions are laid out in source (declaration) order** within
   each region (local statics by their counter; the static initializer's
   order with some scheduling noise, e.g. `unit_nz` initialized before
   `unit_x` in zmath_pnt3d.cpp).

Open for phase B: whether in-class members and implicit members can be told
apart without DWARF (they cannot today: a file-local LOCAL member is only
flagged `file_local`), how a unit's functions and data interleave in source
(the sections order them independently; declarations must precede uses),
and the literal-pool and copy positions (stage 7).

### Drafts

For each unit, `functions` holds the hypothesis source order (`basis`
`dwarf-lines` where the unit has line tables, else `reverse-address`) and
`data` one entry per region (`basis` `address`). Each adjacency is classed:

| Class | Meaning |
| --- | --- |
| `proven` | the DWARF lines of both definitions record this order |
| `constrained` | the local-static counter (functions, data) or the static initializer (data) orders the pair this way |
| `hypothesis` | only the calibrated rule places it |

An adjacency lists its `basis`, the evidence against it (`conflicts`; the
rule's order is kept), and the non-constraining evidence that agrees or
disagrees (`corroborated_by`, `contradicted_by`: literal labels for
functions, DWARF variable order for data). `constraints` lists the counter
and initializer chains (consecutive pairs in evidence order, implying every
pair) with `agrees`. `not_placed` holds definitions without a source
position: `generated` (`__vt__`, `__RTTI__`, `__sinit_`, `.p__sinit_`),
`compiler-generated` (`__arraydtor$N`), `static-guard` (`init$N`),
`no-dwarf-line` (a function without a line in a line-numbered unit),
`common` (COMMON allocations) and `outside-code`. A unit's `status` per
scope (functions, data, unit) is `proven` (every adjacency proven),
`constrained` (some proven or constrained), `hypothesis` or `trivial` (no
adjacency).

On the current inputs (219 units, 39 with line tables):

| Scope | Placed | Proven | Constrained | Hypothesis | Against the draft |
| --- | --- | --- | --- | --- | --- |
| functions | 4,638 | 428 | 15 | 3,979 | 0 adjacencies, 3 of 86 chain constraints |
| data | 1,860 | 0 | 562 | 883 | 9 adjacencies, 9 of 597 chain constraints |

| Status | Proven | Constrained | Hypothesis | Trivial |
| --- | --- | --- | --- | --- |
| functions | 36 | 7 | 163 | 13 |
| data | 0 | 101 | 36 | 82 |
| unit | 6 | 110 | 95 | 8 |

Not placed: 866 generated, 315 static guards, 13 `__arraydtor$N`, 4
functions without a line.
