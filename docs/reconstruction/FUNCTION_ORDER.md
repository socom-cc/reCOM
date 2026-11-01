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
too (`order draft`, see [Source-order drafts](#source-order-drafts-and-the-calibration)),
and so are the stage's producer and its order plans, one per segment with
an independent review (`progress decompose-stage`, `order plan draft`,
`order plan decide`, `order plan validate`; capability
`function-order-plans`; see [Order plans](#order-plans)). A4, a governed
correction route for accepted stage 4 plans, is not built yet.

**Phase B, skeletons, no compiler (writes `src/`).** Split from the compile
work on 2026-11-01 at the user's request, so that the license blocks only
phase C. A skeleton generator writes each unit's source in the accepted
plan's order (B1). Every definition gets its exact signature. Existing
provisional bodies move into place, and stubs are marked. Static checks
(B2) confirm that signatures mangle back to the ELF's names, that the
written order predicts the target and that annotations are unchanged. Each
segment's apply runs both and is accepted by an independent verifier (B3).
These are not stage evidence. The mangler the signature check uses is
registered (see [Metrowerks name mangling](#metrowerks-name-mangling)), and so
are the generator's read-only inputs (`order skeleton manifest`, capability
`function-order-skeleton-inputs`; see [Skeleton manifests](#skeleton-manifests)).

**Phase C, needs the exact compiler.** A probe harness compiles a unit and
reads its object's section and symbol order (C1). The emission rule is
calibrated on the units whose source order DWARF records (C2). An
independent verifier builds each unit from a clean checkout (C3). `mwccps2`
stops at the FLEXlm check (blocker
`socom:blocker:metrowerks-flexlm-license`, the user's to resolve), so phase
C waits. The stage gate waits for every phase C item: the stage is not
accepted without the compiler.

The producer opens phase A only. The phase B items wait for
`socom:work:order-skeleton-route` (deferred capability
`function-order-skeletons`). The phase C items and the stage gate wait for
`socom:work:order-compile-route` (deferred capability
`function-order-compile`). No registered capability opens either gate yet.

## Metrowerks name mangling

`reference demangle` (capability `metrowerks-name-mangling`,
`tools/_socom/mw_mangle.py`) is read-only. It parses a symbol name into a
structured JSON form, renders it as C++ declaration text (scope, name,
parameter types, cv-qualifiers) and mangles the form back. `--all`
round-trips every ELF symbol, and `--output` writes every name's row under
`build/`:

```powershell
python tools/socom.py reference demangle Tick__10CZSealBodyFf __opf__6RfloatCFv
python tools/socom.py reference demangle --all --output build/stage5/demangle-all.json
```

The scheme is MW MIPS C Compiler 2.4.1.01's cfront/ARM mangling:

- `name__<scope><cv>F<params>` is a function and `name__<scope>` a static
  data member or namespace variable. `Q<k>` joins `k` length-prefixed names.
  Template arguments are written literally inside the length
  (`vector<i,Q23std12allocator<i>>`). `@unnamed@<file>@` is an unnamed
  namespace and `<name>$<n><file>` a function-local class.
- `C` before `F` makes a const member. The name does not encode the return
  type (`#pragma new_mangler` is off), `static` or `virtual`, or whether the
  scope is a class or a namespace. Those come from stage 3 prototypes, call
  sites and DWARF. `__ct`/`__dt` carry only the declared parameters, because
  the compiler adds the destructor's hidden flag itself. A skeleton therefore
  writes `CZSealBody::Tick(float)` as a member with an implicit `this`. The
  free function `Tick(CZSealBody *, float)` would mangle as
  `Tick__FP10CZSealBodyf`.
- Types: the builtins `v b c s i l x f d r w e`, with `U`/`S` for
  unsigned/signed. `1` is the 128-bit integer, rendered `unsigned __int128`
  as DWARF types it; whether a plain `__int128` also mangles as `1` needs a
  compiler probe. The qualifiers are `C`/`V`. Compound types are `P`
  (pointer), `R` (reference), `A<n>_` (array), `F<params>_<result>`
  (function) and `M<class>` (pointer to member). A pointer to member function's two
  hidden parameters (`PCv`, then `Pv`, or `PCv` for a const member) are kept
  out of its parameter list.
- Other symbols are classified, not mangled: vtables, RTTI, thunks
  `@<offset>@<function>`, `__sinit_`/`.p__sinit_`, `__arraydtor$N`, local
  statics `name$N` and `name$localstaticN$<function>` with their one-byte
  `init` flags, `__init__<data>`, `@N` literals, `$LN` and `_$name` labels,
  section symbols and plain C names.

Real data (2026-11-01): all 21,894 symbols (18,159 names) round-trip
exactly. Of these, 13,610 names parse into a Metrowerks form, including
6,813 C++ functions, 958 data, 248 vtables, 254 RTTI and 31 thunks. That
covers every authored function artifact of `source graph`: 6,565 artifacts,
of which 6,550 are C++ functions, 13 are array destructors, and `main` and
`TRC_PreparePowerOff` are C names. No name fails. Two cases stay ambiguous.
The 13 f2c constants `c__N` look mangled but are C names. A template
argument made only of digits is read as a value, so the 128-bit `1` in
`__vector_imp<1,...>` renders as `1`.

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
23 `.bss` and 24 COMMON. Labels stay evidence-based; phase C probes will name
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
source that the compiler (phase C) turns into it. `order draft` (read-only; it also
reads the source cache, `build/cache/source-graph.sqlite`) collects the
evidence for the **source** order of each unit's definitions, calibrates
it, and drafts a hypothesis source order for the A2 planners. It decides
nothing: compiler probes (phase C) settle the rule.

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

Open for phase C: whether in-class members and implicit members can be told
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

## Order plans

### The producer and the items

`progress decompose-stage --stage authored-function-order` (producer
`order-target`) runs once stage 4 is accepted with its file baseline and no
stage 4 amendment is open (an open amendment's plan is not accepted, so the
order target would miss its units). It reads the order target over the
accepted stage 4 plans and `build/source-graph/graph.json`, which must be
stage 4's decomposition graph and match the baseline. It replaces the stage
5 seed with:

| Item | Kind | Waits for | Owns |
| --- | --- | --- | --- |
| `socom:work:order-segment-NNN`, one per stage 4 segment holding authored units | `order-plan-segment` | the accepted stage 4 gate | `build/order-plans` |
| `socom:work:order-link` | `order-plan-link` | the accepted stage 4 gate | `build/order-plans` |
| `socom:work:order-segment-NNN-apply` (phase B: skeleton source and static checks, no compile) | `order-apply-segment` | its plan and the skeleton route | its units' `src/` directories |
| `socom:work:order-segment-NNN-compile` (phase C: exact-compiler build and object-order check) | `order-compile-segment` | its apply and the compile route | its units' `src/` directories |
| `socom:work:order-skeleton-route` | `capability-gate` | a registered skeleton generator | nothing |
| `socom:work:order-compile-route` | `capability-gate` | a registered compile route (the compiler license) | nothing |
| `socom:work:authored-function-order-seed`, now the gate | `stage-gate` | every compile item and the link plan | nothing |

A unit is planned once, in its `primary_segment`. A unit that owns data only
(its rows come from data reconciles, so it has no segment) is planned with
its nearest authored neighbour in link order; the item's batch lists it
under `units_by_neighbour` and the record lists every such unit. Item
batches record the segment's units, the order-target and stage 4 baseline
digests and `segment_target_sha256`, the digest of the part of the target the
plan orders. The compile route names the compiler blocker
`socom:blocker:metrowerks-flexlm-license`, and the decomposition adds this
stage to that blocker's `blocks`; the skeleton route waits for no external
input, only for its generator. No capability opens either route, so
`progress open-capability-gate` refuses both and phases B and C stay closed
and visibly blocked. Generic handoff and acceptance refuse the apply,
compile and gate items. The stage row's `decomposition` record carries
`producer_sha256`, the digest of the order target, the stage 4 baseline and
every segment item's units; the audit recomputes it.

### The plan

An order plan is `build/order-plans/<item>.json`, schema
`socom-order-plan` 1:

- `inputs`: `order_sha256`, `stage4_baseline_sha256`, `graph_sha256`,
  `evidence_sha256` (the draft evidence) and `segment_target_sha256`.
- `rule`: the rule the prediction applies (below).
- `units`, in link order, each with:
  - `functions`: the intended source order of the unit's out-of-line and
    in-class function definitions. A row is `{artifact, name, address,
    position, in_class, class, basis, evidence}`. `position` numbers the
    rows 1..k in source order. An `in_class` row is a member defined in its
    class body. It is emitted on demand, right after its first caller, so
    it is outside the file's out-of-line order, and its position may be
    null. `evidence` holds its DWARF `line`, `static_counter`,
    `literal_label` and `first_user`, the earliest-emitted definition of the
    unit that references it.
  - `data`: one entry per region, `rows` in declaration order with the
    same fields (no `in_class`; evidence `static_counter`, `sinit`,
    `variable`).
  - `not_placed`: the definitions without a source position (generated
    `__vt__`/`__RTTI__`/`__sinit_`/`.p__sinit_`, `__arraydtor$N`, `init$N`
    guards, members without a line in a line-numbered unit, COMMON).
  - `stage7_targets`: `copies` and `literals`, listed only. Stage 7 places
    them, when real bodies emit them (D3).
  - `open`: the rows that need a planner's judgment, each with a `kind` and
    a `reason`; `settled` holds the settled ones with their basis; `notes`.

A row's `class` is `proven` (its DWARF definition line), `constrained` (the
local-static counter, or for data the static initializer, orders it against
every other carrier as its position does) or `hypothesis` (only the rule
places it). Its `basis` says which (`dwarf-line 42`,
`local-static-counter 2609`, `static-initializer rank 3`,
`reverse-address rule`, `declaration-order rule (address order)`) or, after
a decision, the planner's evidence. A decided row also has `decision`
(by, at).

### Drafting, deciding and validating

```powershell
python tools/socom.py order plan draft --item socom:work:order-segment-064
python tools/socom.py order plan validate --plan build/order-plans/socom-work-order-segment-064.json
python tools/socom.py order plan decide --plan build/order-plans/socom-work-order-segment-064.json --lease-owner <worker> `
  --artifact <id> [--position N | --no-position] [--in-class | --out-of-line] [--class <class>] --basis "<evidence>"
python tools/socom.py order plan validate --plan build/order-plans/socom-work-order-segment-064.json --check [--output build/...]
python tools/socom.py order plan draft --item socom:work:order-link
```

`order plan draft` writes the item's plan at its packet path (or
`--output` under `build/`). In a unit with DWARF lines, positions follow
the lines, and every row is `proven`. Without lines, positions follow the
reverse address order (the rule), and the counter constrains the rows it
agrees with. Data rows follow the address order. It leaves open only:

| Open kind | When | The draft's row |
| --- | --- | --- |
| `out-of-rule` | a DWARF line places a function against the reverse-order rule (off the longest reverse chain), an in-class candidate; the reason names its first caller | drafted `in_class` at its line's position |
| `constraint-conflict` | the local-static counter or the static initializer orders two rows against the drafted order | kept in the rule's order |
| `interleaved` | a unit's stray artifact outside its main run (seal_ai.cpp's local-static copies at the head of `.sbss` and `.bss`) | a stage 7 copy, or the row |
| `deferred-in-span` | an unresolved stage 4 row (gate deferral) inside one of the unit's runs | none: another unit's or unowned row |

A re-draft (the plan file exists) keeps the planner's decisions: decided
rows get their final position, class, flag and basis again, in ascending
position, and settled rows whose open row recurs stay settled. A decision
that no longer applies is reported under `dropped_decisions`. Open rows the
fresh draft raises stay open. For `socom:work:order-link` the draft is the
`order link-spec` output (`socom-link-order`, which records the stage 4
baseline).

`order plan decide` settles one row as the worker holding the item's lease
(`--lease-owner`). It takes a new `--position` (the row moves, the others
are renumbered), or `--no-position` for an in-class member, the
`--in-class` or `--out-of-line` flag, a `--class` (`proven` only with a
DWARF line), and the `--basis` it rests on. It refuses the whole decision
when one check fails. It settles every open row of the artifact into
`settled`. An open row without a row of its own (a stray copy, a deferred
stage 4 row) is settled with `--basis` only.

`order plan validate` refuses a plan unless:

- it is a schema 1 plan of an `order-plan-segment` item for that segment,
  with no unknown field and no control character;
- its units are the segment's current units in link order, and equal the
  item's decomposed units;
- every definition of each unit is listed exactly once (a function row, a
  data row in its region, or `not_placed` with the derived reason), and
  `stage7_targets` lists exactly its copies and literals;
- positions number each scope 1..k (an out-of-line row or a data row always
  has one), names, addresses and evidence equal the current ones, a
  `proven` row has a DWARF line and agrees with the other lines, and a
  `constrained` row agrees with every other carrier of its evidence;
- the order the plan predicts under the rule equals the target order: the
  out-of-line rows in descending position are the target's address order;
  an in-class row with a first caller lies after it with no out-of-line
  row between (one without a caller among the unit's definitions is a note,
  unverified until phase C compiles it); data rows in ascending position are the
  region's address order. Every mismatch is listed with the two rows and
  their positions;
- every open row the drafter raises is still open or settled;
- the digests are current. A stale stage 4 baseline or order target says
  re-draft; the segment's target digest tells whether the segment itself
  changed.

`--check` also fails on open rows. A link plan must equal the current
`order link-spec` output with a clean static check.

`progress work handoff` of an `order-plan-segment` or `order-plan-link` item
re-runs `order plan validate --check` and needs `--evidence` citing the
plan's current SHA-256 (`<plan> sha256:<sha>`). `progress work accept`
re-runs it and refuses a plan whose SHA-256 is not the one the handoff
cited. The reviewer is an independent `socom-source-owner-scrutinizer`.
`order plan draft` refuses to rewrite the packet-path plan of a handed-off
or accepted item. An accepted plan whose inputs went stale (a new stage 4
baseline, say) returns to its planner with `progress work reopen` (not by
its handoff owner; its apply has not started), which keeps the review
history; the re-draft then keeps the decisions.

### Dry run (2026-11-01)

Measured over the main checkout at tracker revision 3668. Stage 4
amendments 001-006 were open, so segment 14's plan was not accepted and is
missing. Result: 45 segments with 219 units (two data-only units,
`ztwod_main.cpp` and `ztwod_bitmap.cpp`, planned in segment 41 by their link
neighbours). The drafts hold 6,436 rows: 4,589 function and 1,847 data rows
(466 proven, 799 constrained, 5,171 hypothesis), plus 1,190 not placed.

32 rows are open, in 9 segments:

| Open kind | Rows |
| --- | --- |
| `constraint-conflict` | 23 |
| `deferred-in-span` | 4 |
| `out-of-rule` | 3 |
| `interleaved` | 2 |

The `constraint-conflict` rows are 8 functions in seal_ai, seal_command and
seal_unit, plus 15 data rows, mostly static-initializer order. The
`deferred-in-span` rows sit in ent_main, seal and seal_ai. The `out-of-rule`
rows are hud_linemap's `CAiLinePtItr` members. The `interleaved` rows are
seal_ai's local-static copies. Every draft validates, with no mismatch
under the rule. The other 36 segments need only review.

## Skeleton manifests

Phase B round 1 registers the skeleton generator's inputs. The design is
`build/stage5/PHASE_B_DESIGN.md` with its decisions BD1-BD8.
`order skeleton manifest` is read-only. It writes nothing under `src/`
and changes no tracker state:

```powershell
python tools/socom.py order skeleton manifest --output build/stage5/skeleton-manifest.json
python tools/socom.py order skeleton manifest --segment 35 --output build/stage5/skeleton-035.json
```

It reads these inputs and refuses to run if any check fails:

- **Order plans.** It reads all 46 segment plans and the link plan. Each
  must be accepted, at the SHA-256 its acceptance evidence cites, and built
  against the current order target and stage 4 baseline.
- **Stage 3 facts.** It reads the cached closeout receipt
  `build/closeout-ghidra-reconstruction/receipt-stage-2.json` and its
  fingerprint `fp-closeout.json`.
  - The receipt's own digest must hold. Its function-index digest must equal
    the stage 3 baseline's.
  - The fingerprint's data digest must equal the baseline's.
  - `--receipt` reads a `ghidra receipt --scope` export instead; the same
    function-index check applies.
  - The digests are cached in `build/cache/skeleton-stage3-digests.json`,
    keyed by each file's SHA-256.
- **Graph and ELF facts.** It reads the source cache (artifacts, relocations,
  DWARF header units), DWARF 1 (variable types, class keys, inheritance) and
  the ELF image.
- **Source.** It scans every file under `src/` (`tools/_socom/cxx_scan.py`).
  `source_apply.parse_blocks` sets the stage 4 annotation blocks aside, so
  line numbers count the authored content only.

The scanner tokenizes each file and tracks its scopes: namespaces,
`extern "C"`, class bodies and their members, enums, typedefs, forward
declarations, definitions with exact spans, prototypes and file-scope
variables. Its lookup goes from the innermost scope outwards. It covers the
injected class name, the declarator's own scope for parameters, typedef
substitution, and the MSL `<cstdint>` names, `size_t` and newlib's `FILE`
(`__sFILE`, as the ELF spells it). The class and namespace chains the ELF's
names prove are entities too. Base-class scopes, template class members and
macros in declarators are not modelled. They show up as mismatches, never as
silent matches.

The manifest (`socom-order-skeleton-manifest`, with a `manifest_sha256` over
its canonical JSON) has four parts.

**Signatures.** One entry per planned function. It records the mangled name
and its structured form. Each scope component gets a kind: `namespace` only
where `src` declares that namespace, `anonymous-namespace`, otherwise `class`.
Member kind and return type each record a source (BD1):

- `stage3`: the receipt's prototype. An explicit `this` makes an instance
  member; no `this` with the mangled arity makes a static one.
- `rule`: constructors, destructors and vtable-slot targets are instance
  members. Constructors, destructors and conversions need no return type.
- `provisional`: the declaration `src` already has, matched by exact mangled
  name. A BD6 body's own return type counts here too.
- `unproven`: written as an instance member returning `void`.

The entry also records `const`, `extern "C"` for the two C-linkage rows, and
both texts: the in-class declaration and the out-of-line definition head.
Names in those texts are qualified so that lookup finds the intended entity.
That means a leading `::` where an inner scope would hide the name, and the
anonymous namespace left implicit (the head is written inside its unit's
`namespace { }`). **S1** parses the definition head back with `src`'s tables
and mangles it. The result must equal the ELF name, and every failure is
reported with its reason.

**Declarations.** One record per class the planned rows need:

- its existing body (path, lines, key), or, for a new body, where it goes.
  The places are tried in order: the DWARF header unit, a provisional
  forward declaration, the enclosing class's body, the unit's own source file
  (anonymous namespace), the directory's `_local.h` (a class only one unit
  uses), the header the directory's sources include most, or a new module
  header;
- its key (`src`, else DWARF);
- the members to add (BD2: additive);
- the in-class bodies of rows planned out of line;
- its vtable slots in order from the ELF relocations, each classed own,
  inherited, thunk or pure, and the virtuals to declare, new or override
  against the primary base's vtable;
- its bases, from the RTTI base list (offset, direct or indirect), with DWARF
  access, or from DWARF inheritance alone when the class has no RTTI;
- its static data members.

Per named type, a full definition is needed when the type is used by value or
as a scope; otherwise a forward declaration is enough.

**Bodies.** Every provisional definition is mapped by exact mangled name,
overloads included. That covers namespace-scope definitions in `.cpp` files
and in-class header bodies of out-of-line rows. Each gets one action:

| Action | When |
| --- | --- |
| `move-in-place` | its own unit's row |
| `cross-file-move` | another unit's row (`recipient`) |
| `move-out-of-line` | a header in-class body of an out-of-line row |
| `bd4-holding` | a copy-only body, an artifact no planned unit owns, or code with no ELF function that would emit one; it goes to the module's unbuilt `<module>_holding.cpp` |
| `bd6-declarator-rewrite` | the one unclaimed planned row of that scope and name; its declarator contradicts that row, and `rewrite` gives the declarator to write |
| `preamble` | inline or template code with no ELF function (it emits nothing) |
| `judgment` | an overload tie, an exact name in several other units, or an unparsed declarator |

Each file entry records:

- its unit, or that it is an orphan, and whether it would be empty after the
  moves;
- its stage 4 blocks and authored-content digest;
- its file-scope data definitions, mapped to data rows;
- its preamble counts.

The frozen snapshot `build/stage5/provisional-bodies.json`
(`socom-provisional-bodies`) holds every body's path, line span, SHA-256 and
text. Moves read from it, so donor and recipient applies stay independent.
It is written once; later runs only compare it. If it changed, the command
reports it stale and exits 1. `--refresh-snapshot` replaces it, before any
apply starts.

**Data.** One entry per planned data row, with its type and source (BD5).
Sources are tried in order: the DWARF variable record, the stage 3 type of
the same size, the provisional declaration of the same size, then a type
built from the direct load and store widths. That last one, and the byte
array used when nothing else applies, are flagged `unproven`. The entry also
records:

- the initializer from the ELF bytes: relocated words as `&symbol` (string
  literals as text), explicit zeros, none for nobits; rendered for scalars and
  arrays of scalars;
- `const` for `.rodata`;
- the storage: `static` (LOCAL), local static (with its owning function) or
  external;
- the expected section.

The report prints S1 and the judgment list first, then the counts in total
and per segment. Judgment kinds are S1 failures, overload ties, signature
contradictions, by-value types `src` does not declare, copy-only and unowned
bodies, ambiguous owners, unparsed bodies, and local statics without one
owning function.

**Measured (2026-11-01, tracker revision 3929, all 46 plans).** A full run
takes about 10 s once the stage 3 digests are cached.

- **S1:** 4,636 of 4,638 planned functions pass. The 2 failures are the
  members of zui_skb.cpp's function-local class `CSoftKeyboard::Local`
  (`Local$2354`), which cannot be defined out of line. Over every authored
  non-copy ELF function (4,822) these are the only failures.
- **Judgment (268 rows):**

  | Kind | Rows |
  | --- | --- |
  | signature contradictions (BD6) | 109 |
  | by-value types `src` does not declare | 70 |
  | unowned bodies | 36 |
  | copy-only bodies | 23 |
  | local statics without one owning function | 16 |
  | overload ties | 11 |
  | S1 failures | 2 |
  | unparsed body (`LOCALE_PARAM` macro in posix/strcasecmp.cpp) | 1 |

- **Bodies (898):** 846 namespace-scope definitions in 123 `.cpp` files, plus
  52 header in-class bodies. The design measured 606: its scan skipped
  definitions inside `namespace zar/zdb/sealai { }` blocks.

  | Action | Bodies |
  | --- | --- |
  | move in place | 464 |
  | cross-file move | 137 |
  | BD4 holding | 124 |
  | BD6 rewrite | 109 |
  | move out of line | 52 |
  | judgment | 12 |

  All 57 orphan `.cpp` files would be empty after the moves.
- **Classes (434):** 270 with a body and 164 new. They need 3,118 members
  added, 646 static data members and 870 virtual declarations.
- **Member kind:** 2,862 from stage 3, 574 by rule, 56 provisional and 394
  unproven; 752 functions are not members.
- **Return type:** 2,629 from stage 3, 279 provisional, 301 not needed and
  1,429 unproven.
- **Data (1,862):** types from DWARF 446, stage 3 83, provisional 65,
  access width 953 and unproven 315. Initializers: 443 from ELF bytes (409
  rendered), 71 explicit zeros and 1,348 nobits.
