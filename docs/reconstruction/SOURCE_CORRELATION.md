# Stage 4: source correlation

`source-correlation` maps every artifact of the reference ELF to one owner:
an authored translation unit with a workspace file, a provider archive
member without a source body, or compiler/linker output that no unit
defines. The stage is file-only. No item owns a Ghidra resource, and the live
program must still produce the `ghidra-reconstruction` baseline receipt when
the gate closes.

The producer is lean (user decisions of 2026-10-30). Owner maps live in plan
files under `build/source-plans/` and in tracker evidence. There is no tracker
schema migration. Annotations are written only for named artifacts;
compiler-generated artifacts are owned through their owner row's artifact
list. Placement keeps `src/<Apps|gamez>/<module>/` and records the original
`Z:\dev` path on the owner row. Provisional files stay in place, and files
with no evidence are left unowned (they are deleted only through an accepted
plan). Each provider library is one item, with one owner row per archive
member. A provider writes nothing under `src/`: its apply records each
archive member's ownership (library and GNU object or object name) in
tracker evidence only (user decision of 2026-10-31). The artifact basis is
the census-derived set that `source graph` produces
([SOURCE_TRACEABILITY.md](SOURCE_TRACEABILITY.md)).

Planning, the apply route and the gate route are active
([TOOL_COVERAGE.md](TOOL_COVERAGE.md)). `progress apply-source-plan`
applies an accepted plan (a segment's files and annotations under `src/`, a
provider's evidence in the tracker), and `progress open-capability-gate`
opens the capability gate the apply items wait on. An independent reviewer
and accepter close the stage gate with `progress handoff-source-gate` and
`progress accept-source-gate`, which record the file-stage baseline (see
[The stage gate](#the-stage-gate)).

## Decomposition

`python tools/socom.py progress decompose-stage --stage source-correlation
--expected-revision <n> [--dry-run]` replaces the stage seed once
`ghidra-reconstruction` is accepted with a recorded baseline. It regenerates
`source graph` from the ELF. Every artifact lies in exactly one planning
scope:

| Scope | Slice | Plan item | Apply item |
| --- | --- | --- | --- |
| authored segment | the segment's artifacts, the code gaps up to the next segment of its window, and its data slice | `socom:work:source-segment-NNN` (`source-plan-segment`) | `...-apply` (`source-apply-segment`) |
| provider library | the same, over every segment where that library holds a strict majority of the functions | `socom:work:source-provider-<library>` (`source-plan-provider`) | `...-apply` (`source-apply-provider`) |
| data kind | every artifact in no segment slice, by its input section, or the next section when it lies outside every envelope: `rodata`, `data`, or `bss` (`.bss`, `.sbss`, `.vubss`) | `socom:work:source-data-<kind>` (`source-data-reconcile`) | none |

A segment of mostly compiler-generated functions (the static-initializer
window) is an authored segment, because its units own what they emit. An
artifact the graph proves provider code of a library (a provider
classification that is not weak, or a compiler-generated artifact whose
strong primary unit has a provider path) is planned by that library's item
wherever it lies: crt0's unsymbolled object (gap `0x140008`) has its own
item `socom:work:source-provider-crt0`, and MSL plans its units'
`__sinit_` functions from the static-initializer segment. Such a batch lists
`moved_from_segments`; a library with no segment of its own has empty
`segment_numbers` and takes its batch number from the first of them. Each
batch records the scope, `graph_sha256`, the `slice_sha256` of its artifact
list, and counts.

A segment apply reserves `src/` directories; its batch lists them as
`directories` and records `resource_inferred`, `resource_reason` and
`resource_basis` (`path`, `provisional-name`, `neighbour-prefix` or
`fallback`). A unit's directory is the existing spelling of its original
`Z:\dev` module, or else the directory of a provisional file of the same
name. A segment reserves its units' directories. A directory that rests only
on a provisional file's name (the unit has no original ELF path) is an
inference too (`provisional-name`, reason `inferred by name: ...`): the
plan must confirm or correct it (user decision of 2026-10-31). When none of
its units has such evidence, the directory is inferred from its neighbours
(user decision of 2026-10-31). For each unit, the
nearest segments of the same window that have evidence are searched outward
on both sides in segment order. Their units with the same TU-name prefix
(the stem up to the first `_`: `zui_skb.cpp` and `zui.cpp` give `zui`) give
the directories those units resolve to. The batch then has
`resource_inferred: true` and a reason naming the supporting segments and
units, and the segment's plan must confirm or correct the inference. Only a
segment with no inference reserves all of `src`, with the reason in
`resource_reason`. The decomposition record lists both kinds as
`inferred_reservations` and `fallback_reservations`. A provider apply
reserves nothing: it writes no file, and tracker writes are serialized by
the tracker lock.

Dependencies:

- every plan waits for the accepted `socom:work:ghidra-reconstruction-seed`;
- every data reconcile waits for every segment and provider plan, because
  cross-unit data order is checked against the planned text order;
- every apply waits for its plan, every data reconcile, and
  `socom:work:source-correlation-apply-route`. That `capability-gate` item
  cannot be claimed, handed off, or accepted by a worker. It stays blocked
  until `progress open-capability-gate` accepts it, which needs the
  registered apply route (see [Opening the route gate](#opening-the-route-gate)).
  That route writes a segment plan's files and annotations, including the
  data its reconciles assign, and records a provider plan's archive members
  in tracker evidence;
- the seed keeps its ID and becomes the stage gate over every apply and data
  reconcile.

For the reference graph (`c79d76e6...`, 76 segments, as for `7bd4e540...`)
this gives 46 segment plans and applies, 13 provider plans and applies (crt0, MW runtime, MSL,
SCE, unidentified GNU object, newlib, libgcc, 989snd, speech middleware,
Medius, lgAud, libptt, RSA), 3 data reconciles, the route gate, and the
stage gate. The 62 plans are ready at once. 39 reservations are inferred:
38 rest on provisional file names, and segment 057 (`zui_skb.cpp`, 88
functions, no path or provisional file) reserves `src/gamez/zUI`, where the
`zui_` units of segment 056 (`zui_cleanup.cpp`, `zui_spec.cpp`) lie. Only 7
segments rest on original paths alone. No segment falls back to all of
`src`. `progress audit` holds the items to these rules and to the stage's
decomposition record.

### Graph refinements (round m14)

The graph `7bd4e540...` adds these rules to `837c03c4...`; the segments, and
so every item ID, are unchanged:

- **Gaps split at input sections.** A gap is split wherever a LOCAL SECTION
  symbol opens an input section inside it, so no gap spans two objects'
  sections (`0x466fa0` was puts.o's and strtod.o's `.rodata`; `0x466c89`
  now ends at `0x466c90`). 96 section symbols split gaps (13,301 gaps become 13,397).
- **Member-identity rules.** `GNU_MEMBER_RULES` (libgcc's fp-bit GOFAST
  names `dpadd`, `dpsub`, `dpmul`, `dpdiv`, `dpcmp`, `litodp`, `dptoli`,
  `dptoul`, `dptofp`, `fptodp`, `__thenan_df`, ...) refine an object's
  library: `dptofp` `0x16e398` and `dptoul` `0x16e3f0` (`_df_to_sf.o`,
  `_df_to_usi.o`) are libgcc's.
- **Coupling.** A GNU object whose library rests on archive-contiguity
  alone (or that has none) joins library L when everything outside it that
  references it (callers, and functions sharing its data) is code of GNU
  objects of L, at least two such artifacts, none of its current library,
  and it uses L itself (calls L's code or shares L's data). The reference
  moves two objects (`rules.coupling_moves`): `0x3b7248` (SidInit ..
  SidAdvanceBuffer: called only by `gsapi_*`, `StartListening`,
  `StopListening`, `ProcessAudio`, and calling `heap_Alloc`/`heap_Free`)
  from lgAud to speech middleware, and the unidentified `0x3aae18` to Medius.
- **Stable segmentation.** Segment cuts follow the library rules of the
  first decomposition (`segment_library`, recorded on a GNU object when a
  refinement changed it); the refined `library` is the classification. A
  segment whose mix a refinement changed records the mix its cuts followed
  as `cut_classification_mix`, and the refined artifacts move to their
  library's scope like any other proven provider artifact (`moved_from`):
  segment 011 (the two GOFAST objects) joins the libgcc item, the Sid
  functions in segment 062 move to speech middleware.
- **Data-only members.** A run of LOCAL symbols that no object with
  functions claims, between two GNU objects' blocks, split where a section
  name repeats, is a data-only member when it opens data sections only,
  its sections hold no artifact of a neighbour's cluster, and a neighbour
  that could take it (repeating none of its section names, the previous one
  only when its block does not end with `gcc2_compiled.`) does not
  reference its data. Its GNU object (`data_only`, `data`, `sections`,
  `local_symbols`, `symtab_neighbours`) is the lowest address it opens and
  owns its data and non-padding gaps; its library is that of both symbol
  neighbours, else the one library referencing it. The reference has 11:
  newlib's impure.o `0x43bc88`, ctype_.o `0x466cc0` and s_infconst.o
  `0x447c00`, libgcc's _thenan_df.o `0x448090`, two SCE and five speech
  middleware members.
- **Section runs.** Each GNU object lists `sections`: every data input
  section its LOCAL SECTION symbols open, from the symbol to the next input
  section (`end_basis` `next section symbol`), or cut short by another
  object's artifact (a Metrowerks unit's evidence, another cluster with
  functions, a non-weak classification of another library) or the window
  end. Draft rules version 3 use them.

A unit's data does not follow the segment holding its text in this graph:
data only a unit's `__sinit_` function references stays in the
static-initializer segment (zsnd_csnd.cpp's `.bss` `@1459` at `0x50e660`
stays in segment 076, its text in 039). Every form of that rule also moves
data of `main.cpp` (+4 into segment 001) and of the zAnim units (+4 into
segment 017), whose plans are accepted, so it waits for their review.

### Graph refinements (round m15a)

The graph `c79d76e6...` adds these rules to `7bd4e540...`; the segments,
the item IDs and every slice but four are unchanged:

- **Section-run ends.** A run also ends where its fill changes between file
  bytes and zero fill (an input section is all one or all the other) and at
  the first COMMON allocation. COMMON allocations are the GLOBAL zero-fill
  data that end the last zero-fill data window, back to the first artifact
  that holds a LOCAL or SECTION symbol, holds file bytes or is an
  unsymbolled non-padding gap: GCC emits an uninitialized global as a
  COMMON symbol, which the linker places after every input section. Each is
  tagged `common: true` with a `common` hint signal (cache column
  `artifacts.common`, `common` in plan evidence); the tag changes neither
  its classification nor its slice. The reference has 250 (`0x5b17c0` to
  `0x5e7e94`: Medius `PacketType*`, newlib `errno` `0x5b1aa4`, ...). SCE
  object `0x425ea0`'s `.bss` run ends at `0x5b17c0` (was `0x5e7f00`), its
  `.sdata` run at `0x475600`, where the file bytes end (was `0x47560c`, over
  CAiPath's `init$localstatic4$next` and MSL's `ninit_cnt_s`/`winit_cnt_s`).
- **Object padding.** The alignment padding of a GNU function object's text
  (between its functions, and after its last one up to the next artifact
  unless an input section starts there) takes the object's provider
  classification (1,047 gaps). It gets no `gnu_object` field, so plans keep
  owning padding through compiler-generated rows. The 7 padding gaps of the
  Sid object `0x3b7248` move with its functions from lgAud to speech
  middleware.
- **Run-placed data.** An unreferenced datum that no cluster with functions
  holds and no other rule classifies, inside a GNU function object's run
  that reaches the next input section, is that object's: it takes the
  object's library and follows the object's functions into their segment's
  data slice. The reference has one: Medius
  `RT_MSG_CLIENT_MAX_AGGREGATION_LEN` `0x468af2` (object `0x40c000`'s
  `.rodata`) moves from the rodata reconcile to Medius. Data another rule
  classifies, even weakly, keep their slice: the 48 newlib LOCAL constants
  in their objects' `.rodata` runs (`twom1000` `0x446ec8`, ...) stay in the
  rodata reconcile, as the accepted newlib plan has them.
- **Attached LOCAL blocks.** A LOCAL block between two GNU objects' blocks
  whose sections hold artifacts of exactly one neighbour that could take it
  (the data-only conditions) is that neighbour's leading or trailing block:
  its section symbols open the neighbour's runs (`attached_blocks`), its
  data symbols keep their clusters. The reference has one: newlib's
  locale.o `0x3e1a70` gains its `.data` run `0x43bf78`-`0x43bf90` (symbol
  10768); `last_lc_ctype.4` stays in the data reconcile.

On this graph draft rules version 3 decide 527 of MSL's 529 (`ninit_cnt_s`
and `winit_cnt_s`, no longer inside SCE's `.sdata` run, by `D-referenced`)
and 450 of newlib's 452 (`__mb_cur_max` `0x43bf78` by `P-gnu-data` in
locale.o's `.data` run).

### Refresh after a graph change

```powershell
python tools/socom.py progress decompose-stage --stage source-correlation --refresh `
  --expected-revision <n> [--dry-run]
```

A fix to `source graph` changes the graph digest, so every item's batch is
stale. The refresh rebuilds every batch from the regenerated graph with the
same producer, while no stage 4 item is leased and no apply has started. An
item whose scope the new graph still gives keeps its ID, status, history
and evidence. An accepted plan item keeps its acceptance only when the new
graph gives it the same scope and a byte-identical slice: its batch then
records the graph its accepted plan cites as `plan_graph_sha256`, which
`source plan validate` (and so the apply route) accepts in place of the
batch's `graph_sha256`, so the accepted plan file keeps validating
unchanged. A later refresh keeps that digest. When the new graph changes
the slice of an accepted plan, or drops its scope, the refresh is refused
and names those plans: only review replaces an accepted plan (reopen it
first, see [Reopening an accepted plan](#reopening-an-accepted-plan)). A handed-off
plan returns to `ready`; its handoff moves to a `review_history` note
`graph refreshed <old> -> <new>; replan`, which says whether its slice
changed (if not, the plan only re-cites the digests). New scopes add items;
items whose scope is gone are removed. The decomposition record is replaced
and lists every refresh under `refreshes` (`added`, `removed`, `replan`,
`slice_changed`, `reservation_changed`, `kept_accepted`). On the tracker of
revision 2852 (graph `a3ce2165...` to `837c03c4...`) the dry run added
`source-provider-crt0` and its apply, removed nothing, returned segments 001
and 017 and the MW runtime plan to planning, and changed the slices of
segments 001 and 076, MW runtime, MSL and the rodata and data reconciles.

On a copy of the tracker of revision 2877 (graph `837c03c4...` to
`7bd4e540...`) the dry run passes the strict audit, adds and removes
nothing, keeps the five accepted plans (segments 001 and 017, crt0, MW
runtime, 989snd: same slices, `plan_graph_sha256` `837c03c4...`; each
validates and draft-checks exactly as before), returns the handed-off
newlib, libgcc and lgAud plans to planning, and changes the slices of 14
plan items (newlib, libgcc, lgAud, speech middleware, Medius, RSA, SCE,
unidentified GNU object, segments 026, 029 and 076, and the three data
reconciles) and their applies; no reservation changes.

On a copy of the tracker of revision 2930 (graph `7bd4e540...` to
`c79d76e6...`) the dry run adds and removes nothing and keeps the twelve
accepted plans (segments 001 and 017; crt0, MW runtime, MSL, SCE, newlib,
libgcc, unidentified GNU object, 989snd, libptt and RSA: same slices; each
validates and draft-checks as before). It returns the handed-off segments
027 and 040 (digest only) and the speech middleware, Medius and lgAud plans
to planning, and changes the slices of speech middleware, Medius and lgAud
(and their applies) and of the rodata reconcile; no reservation changes.

## Plan items

The role is `socom-source-owner-mapper`, which may write only the packet's
paths under `build/source-plans/`: the evidence file, the plan, and its
scratch directory `build/source-plans/<owner>/` for notes and queries. The
packet also gives the apply's `reservation` (directories, whether inferred,
reason). The skill is `socom-source-model-recovery`, or
`socom-provider-boundary` for a provider. An independent
`socom-source-owner-scrutinizer` reviews the plan.

```powershell
python tools/socom.py source graph --output build/source-graph/graph.json   # once per graph, shared
python tools/socom.py source plan evidence --item <item> --output build/source-plans/<slug>-evidence.json
python tools/socom.py source plan draft --item <item> --output build/source-plans/<slug>.json
python tools/socom.py source plan open --plan build/source-plans/<slug>.json [--limit N] [--format json] [--output build/...]
python tools/socom.py source plan decide --plan build/source-plans/<slug>.json --lease-owner <worker> --artifact <id> [--artifact <id> ...] `
  (--owner <unit | 0xGNU | object | library:object> --confidence <c> --basis "<evidence>" | --unresolved "<reason>" | --accept-suggestion) `
  [--override --evidence "<why the draft rule is wrong>"]
python tools/socom.py source plan decide --plan <plan> --lease-owner <worker> --artifact <id> --contradiction <kind> `
  --provisional-file src/... [--line N] --elf-evidence "<line>" [--elf-evidence ...] [--override --evidence "<why>"]
python tools/socom.py source plan decide --plan <plan> --lease-owner <worker> --artifact <id> --remove-contradiction --provisional-file src/... [--line N]
python tools/socom.py source plan decide --plan <plan> --lease-owner <worker> --artifact <id> --header-emit <src/...h | <name>> [--library <lib>] `
  --reason <template|inline|weak> --emit-evidence "<line>" [--emit-evidence ...] [--override --evidence "<why>"]
python tools/socom.py source sql "SELECT ..." [--output build/...]   # questions about the open rows
python tools/socom.py source plan emit-check (--plan build/source-plans/<slug>.json | --all) [--output build/...]
python tools/socom.py source plan validate --plan build/source-plans/<slug>.json --check --fill-annotations
python tools/socom.py source plan validate --plan build/source-plans/<slug>.json --check [--output build/...]
python tools/socom.py source plan draft --check build/source-plans/<slug>.json
python tools/socom.py provider archive --lib <path> [--member <name>] [--format text]   # provider plans
```

`source plan open` prints only what is still open in a drafted plan: each
open unresolved artifact (up to `--limit`, default 40) with its kind,
size, names, binding, input section, classification, top unit candidates,
GNU object, cluster, `__FILE__` strings and its first callers and callees
(each with the owner this plan gives it, or the item holding it), then the
open owner rows, open header emits (the draft's, less those a header-emit
row now records), drafted paths outside the reservation, an inferred
reservation and the owner keys `decide` accepts. For an open function it
also shows both flanks: `before: <anchor> < <copies> < this` and `after:
this < <copies> < <anchor>`, where the anchor is the nearest function (up
to 256 away in the window) that a unit owns and that is not a WEAK or
binding-13 copy (the plan's owner, or outside the plan a strong unit
candidate), and the copies are the WEAK and binding-13 copies between,
consecutive copies of one holder collapsed into a run (`WEAK/13 x80
0x18a540..0x1934f0 [ai_mapio.cpp]`; `[open]` marks this plan's open rows),
with the count of other unanchored functions between. A row before a
unit's WEAK tail therefore reads as inside that unit's object, a row after
it as past it. An open WEAK or binding-13 copy also lists its
`referencing_units` (each referencing artifact's unit, `open` or `?`) and,
when they are all one unit, its `sole_referencing_unit`. A row's `suggest`
(below) is shown as `suggest: <owner> <confidence> (<rule>): <basis>`. It
reads the query cache (`--graph`) and notes when the cache holds another
graph than the plan cites. `--output <file under build/>` writes the view
(text, or JSON with `--format json`) there and prints a JSON summary
instead.

`source plan decide` records one decision: it moves the artifacts into an
existing owner row as `{artifact, confidence, basis}` entries
(hand-written, without `draft_rule`) or into `unresolved` with the reason,
keeps the row's confidence its weakest entry's, drops an owner row the
call empties (the change list says `row_removed`) but keeps one that was
already empty, and re-derives `annotations` when the cache holds the
plan's graph. Only the worker holding the plan item's lease may decide:
`--lease-owner` must name the owner of the item's active lease (`progress
work claim`); another worker, an expired lease or an unclaimed item is
refused before the plan is touched. An artifact a decision puts in an
authored row also gets the draft's `draft.open_row_header_emits` row
(rules 6), unchanged and with its `draft_rule`, unless a header-emit row
records one already (the change says `copied`), so planners no longer
re-enter it; moving the artifact out of the authored rows again removes
that copied row (`header_emit_removed`) and leaves hand rows alone.
`source plan draft --check` proves the copied row like a drafted one.
It loads and dumps JSON (never text), refuses control characters and
schema 1 plans, and refuses to move an artifact a draft rule decided unless
`--override` gives `--evidence`, which it keeps as a plan note `override
<artifact>: the draft gave <owner> (<rule>); <evidence>`. Add a new owner
row by hand once (with empty `artifacts`), then decide its artifacts: the
empty row survives other decisions until then, and `source plan validate`
reports it while it lists none. Each call records exactly one kind of
decision; options of another kind are refused.

- `--accept-suggestion` records each named open row's `suggest`
  `{owner, rule, confidence, basis}` (written by the drafter on rows it
  leaves open) as a hand entry of the owner row `suggest.owner` names (an
  owner key, as `--owner` takes): confidence and basis are copied, no
  `draft_rule` is written, and the reviewer reviews it like any hand entry.
  The change list names the suggestion's rule. A row without a suggestion,
  or whose suggested owner row does not exist, is refused.
- `--contradiction <kind>` adds one `contradictions` row per artifact with
  `--provisional-file`, `--line` (omit it for a file-level contradiction)
  and one or more `--elf-evidence` lines; the file must exist exactly and
  hold that line, and a repeated row is refused. The artifact is listed in
  the plan, or lies outside it when the file is one this plan's authored
  rows own (a `provisional_file` or `workspace_path`) and the artifact is
  in the cache's graph: an owned `game_main.cpp:22` that defines
  `StartPlay`, which the ELF places in another segment. With `--override
  --evidence` the new row replaces the artifact's rows at that file and
  line, whatever their kind, kept as a plan note `override contradiction
  <artifact> in <file>[:<line>]: the plan gave <kinds>; <evidence>`.
- `--remove-contradiction` removes each artifact's `contradictions` rows at
  `--provisional-file` and `--line` (omitted: its file-level rows); the
  rows are the planner's own, so no evidence is asked. An artifact without
  such a row is refused.
- `--header-emit <header>` adds one hand `header_emits` row per artifact
  (owned by an authored row of the plan) with `--reason` and one or more
  `--emit-evidence` lines: a header under `src/`, or `<name>` with
  `--library` for a provider header. An artifact that already has a
  header-emit row is replaced only with `--override --evidence`, kept as a
  plan note `override header emit <artifact>: the plan gave <header>
  (<rule>); <evidence>`. Binding, letter case and reservation are left to
  `source plan validate`.

Neither command loads the whole plan into the planner's context.

`source plan emit-check` (read-only) computes the header-emit rulings of
2026-10-31 that reviewers used to find one at a time. For every inline
(binding 13) or WEAK function an authored row of the plan owns, except
this-adjusting thunks (`@N@...`) and MSL instances (`H-template-family`
covers those), it collects the units involved: the unit holding the copy,
the unit of every function or data artifact whose relocations reference
it, and, when its own class's vtable references it, every unit that reads
that vtable or calls a constructor of the class. A unit comes from the
decisions in every plan file under `build/source-plans/` (so a data site
counts by its own plan owner), else from the whole-graph draft decision
(the draft's anchors and containment rules); referencers neither places are
listed as `unknown_referencers`. It expects an emit for

- an implicit special member (a destructor, a default or copy
  constructor or a copy assignment without a DWARF compile unit of its own
  whose body shape is `implicit`, below) when a header declares its class,
  whatever the unit count;
- a copy that two or more units involve (ODR: a shared header);
- an authored template instance (a class-template member such as
  `RTArray<...>::GetNext` or a function template instance such as
  `ai::_max<f>`), whatever the unit count: the template's definition has
  to be visible where it is instantiated.

The body shape of such a special member is read from `support/socom.elf`
(its instructions, in address order, and the cache's relocations):
`implicit` when it does only what the compiler generates (a destructor:
vptr stores, base and member destructor calls on `this`, the delete-flag
test and its operator delete; a constructor: base and member constructor
calls, vptr stores, member zero or copy initialization; an assignment:
member-wise copies and member `operator=` calls; a loop only when every
store and call in it is such a copy, construction or destruction),
`user-written` when it does anything else (a call of another function, a
destructor or operator delete on a loaded pointer, a non-zero constant or
another member stored, a global read or written, a virtual call), and
`unknown` when the scan cannot tell (a call into `std`/`Metrowerks` or
other library code an inlined member may have made, a value it does not
track, a loop that stores and calls nothing). Three stretches are not
the member's own and are not judged: the deleting tail after the
delete-flag test; an inlined base (or member) destructor or constructor,
which starts at the store of a vtable that is not the class's own (in a
destructor up to the delete-flag test, in a constructor up to the store of
its own vptr); and, in a destructor, a stretch the compiler skips when
`this+N` is null (`addiu v0,s1,N; beq v0,zero,...`, N > 0: the inlined
member or base destructor's own `this` test) that the ELF identifies as
that destructor: (b) its stores and calls, rebased by N (the receiver,
an address second argument such as a `__FILE__` literal, stored members
and values; stores between two calls in any order), equal those of an
out-of-line destructor outside its deleting tail, or (a) it passes a
`__FILE__` literal (the cache's `file_strings`) naming a header that is
not one of the class's headers (its DWARF header units and the
provisional headers declaring it; no verdict when none is known). An
unidentified null test leaves the stretch judged. `CAiEvent::~CAiEvent`
0x17fc20 inlines `CBits::~CBits` at `this+0x20`: equal to the out-of-line
0x17f440 and passing `zmath_bits.h` (CAiEvent is zai.h's), so it is
`implicit`; each such row lists the stretches in `body_inlined`. A
user-written special member that one unit involves
expects no emit; an `unknown` one is listed in `unknown_shape` (the copy,
its units, the class header and whether the plan emits it) and never
expected; a header-emit row on a user-written single-unit copy (not a
template instance) is listed in `user_written_emits`. Neither list is a
finding: the counts `shape_implicit`, `shape_user_written`,
`shape_unknown`, `unknown_shape` and `user_written_emits` report them.

The header is the class's (template's) DWARF header unit: its own, else the
one most of the class's members name. A `Z:\dev` path maps to the
workspace like the plans write it: the direct `src/<module>/<file>` when it
exists, else the one file of that name in the module tree
(`Z:\dev\Apps\FTS\hud.h` is `src/Apps/FTS/hud/hud.h`), else the path the
plans already emit to (`src/gamez/zMath/zmath_matrix.h`), else the direct
path as a new header. Without a header unit it is the provisional header
under `src/` that defines the class (`class|struct <Name>`; a nested class
inside its enclosing scope, and a nested class no header declares by
itself through its enclosing class; a `template` declaration for a
template; a function declaration for a free function), with its line.
When two or more units are involved or the copy is a template instance and
no header is evidenced, the plan needs a note that names the artifact (its
ID or address) and says that no header declares it (`no header declares
<Class>`, `no provisional header under src/ declares ...`) in the same
clause group: a clause naming no address belongs to the clause before it.
Each workspace header-emit row whose evidence cites `<header>:<line>` must
cite at least one line that declares the artifact's class (or template, or
free function); a row citing only member lines (`member line`), another
class's line or a forward declaration (`another line`) or a line past the
end of the file is listed.

The report lists per plan `missing_emits` (artifact, name, class, units,
unknown referencers, the vtable reached, basis, `suggested` header with
line and source, the emit reason), `missing_notes` (with the note text to
add), `wrong_citations` (each citation's line text and kind, and where the
class is declared) and `undetermined` copies (one known unit plus unknown
referencers), `unknown_shape` and `user_written_emits` (each copy with
its `body_shape`, the first `body_reasons` and any `body_inlined`) and
`special_members` (the
shape and unit counts of every owned special member without a DWARF unit
of its own), with counts and the item's tracker status. `--plan` (repeat)
checks those plan files, `--all` every plan; `--output <file under
build/>` writes the JSON and prints the counts and the plans with findings.
The parent hands that file to sweep agents. It reads the query cache of
`--graph`, the plan files and the ELF, and writes nothing else.

`<slug>` is the item ID with `:` replaced by `-`. The draft decides every
artifact its rules settle (below) and leaves the rest as `unresolved` rows
marked `"draft": "open"`; the planner works only on those, on owner rows
marked `"draft": "open"` (paths no rule decides), on header emits the draft
could not resolve (`draft.open_header_emits`) and on the reservation
(`draft.outside_reservation` lists drafted paths outside it). Validation
refuses every open marker. The command never overwrites an existing plan.

The evidence file lists the slice with each artifact's names and bindings
(`weak`, `inline` for Metrowerks binding 13), its loaded section, whether it
is named, its classification candidate with the graph's evidence lines and
`weak` flag, unit candidates, input section (or `between <a> and <b>`), GNU
object and DWARF paths. It also lists the segments with their
`internal_boundaries` (each unit change inside a segment with the
unanchored functions between the two anchors), `moved_from_segments`, the
units, the GNU objects whose functions or gaps lie in the slice, and the
provisional files whose names match a unit. For a segment it also shows the
apply's `reservation`. `--skeleton` still writes a plan listing every slice
artifact unresolved with the placeholder reason `not yet planned`, which
validation refuses. For an inferred reservation the skeleton and the draft
carry a `reservation` row with status `inferred`, which validation refuses
too.

`provider archive` lists an external provider library (`ar` format: `.a`,
CodeWarrior `.LIB`) read-only: each member's header name as the archive
writes it (16 bytes, so an archiver without a long-name table truncates it;
`possibly_truncated` flags a full header field or a longer source file
symbol), its resolved name, size, SHA-256, sections, the archive symbol
table's entries for it, and its defined (binding, type, section, value,
size) and undefined ELF symbols. `--member` keeps the named members. It
writes nothing and names the archive by file name, size and SHA-256 only;
never copy the archive's path into a plan, note or other tracked file.

Without `--check`, evidence and validate read `--graph`
(`build/source-graph/graph.json` by default); the draft reads it unless
`--from-elf` is given. They recompute its digest and refuse a graph that
differs from the one the item was decomposed from. `--check` (evidence,
validate) regenerates the graph from the ELF instead.

### Draft rules (versions 1 to 7)

`source plan draft --item <item> --output <plan> [--rules 1|2|3|4|5|6|7]` writes a
schema 2 plan under version 7 unless `--rules` says otherwise. Each decided
artifact is an entry `{artifact, confidence, basis, draft_rule}`; each owner
row's confidence is its weakest entry's. The rules are conservative: when
any condition fails the artifact stays open. Their exact statement is in
`tools/_socom/source_draft.py`. Version 2 extends `A-between` and
`P-gnu-object` (marked *v2* below); version 3 adds provider-scope unit
rules and LOCAL section containment (marked *v3*); version 4 decides
unanchored runs between two units by ELF regularities, adds suggestions
and header emits for instances without a header compile unit (marked
*v4*); version 5 keeps version 4 except that `D-referenced` and the
"referenced only by" fallback of `P-gnu-data` never decide a COMMON
variable (the graph's `common`: linker-allocated, no defining section), which
stays open with that reason (from version 6, authored plans: an
`S-sole-referencer` suggestion); version 6 decides GLOBAL data by a sole
referrer only inside that referrer's own data run, tightens three
suggestions and extends `H-template-family` to LOCAL MSL function
templates (marked *v6*; see [Version 6](#version-6)); version 7 keeps
version 6 except that `P-gnu-data` passes over a named datum only foreign
code reads (marked *v7*; see [Version 7](#version-7)); every other rule is
version 1's. A plan is checked under the version it was drafted with.

| Rule | Decides | Confidence |
| --- | --- | --- |
| `A-dwarf-cu` | a source compile unit's pc range covers the artifact | high |
| `A-dwarf-header` | a header compile unit covers the function and lies in one object's `.debug` contribution (the object DIE before it names the unit; the reference holds this for all 573 source units) | high |
| `A-sinit`, `A-unnamed`, `A-dwarf-static` | `__sinit_<file>`/`.p__sinit_<file>`, an `@unnamed@<file>@` tag, a DWARF static of one CU | high |
| `A-file-string` | a `__FILE__` literal of the unit, or a function whose relocations reach one | high |
| `A-local-block` | the object cluster (LOCAL relocations, section symbols, LOCAL symbol order) names exactly this unit, strong | high |
| `A-between` | an unanchored function strictly between the nearest anchors of its window, both one unit, no GNU object start or other unit's candidate between; a WEAK or binding-13 instance only when everything referencing it is anchored to that unit. *v2*: also such an instance that other units call, when it is a single copy (no other function has one of its names) and no function between the two anchors is provider-proven or has a strong or medium candidate of another unit | medium |
| `A-kept-copy` *v4* | R1: every function of a span from a caller to an inline/WEAK copy placed after it (spans sharing a function merged) takes the one unit decided inside the span | medium |
| `A-vtable-key` *v4* | R3: the one own non-inline virtual of an anchored GLOBAL vtable that no rule places in another unit is the vtable's unit; an unanchored GLOBAL vtable whose own non-inline virtuals are all decided for one unit is that unit | medium |
| `A-contiguity` *v4* | R4: a function strictly between two functions decided for the same unit | medium |
| `D-referenced` | unanchored data whose referencing functions (followed through data) are all decided for one unit. *v6*: GLOBAL data only when it lies strictly inside that unit's own data run (see [Version 6](#version-6)) | medium |
| `C-fill` | the graph's alignment padding: the compiler-generated row. *v4*: also zero (or `.bss`) fill of any size, without labels or relocations, that ends exactly at a GNU object start or LOCAL section run start and is smaller than that address's alignment | high |
| `P-gnu-object` | a function or gap of a GNU object of the plan's library: one provider row per object. *v2*: when a DWARF compile unit of the object has a project-toolchain (Metrowerks) producer, such as crt0.s's `Metrowerks MW GAS R5900 Assembler`, the row records `archive_member.linked: "object"` | high, medium past an uncertain object end |
| `P-gnu-data` | data in a GNU object's cluster (high) or referenced only by its functions (medium). *v3*: data in no cluster but inside one GNU object's LOCAL section run (`gnu_objects[].sections`) is that object's before the "referenced only by" fallback (high; medium when the run was cut short); a cluster and a run naming different objects leave it open. *v6*: the "referenced only by" fallback decides GLOBAL data only strictly inside the object's own data run. *v7*: never a named datum (GLOBAL, or LOCAL or WEAK with a symbol) that code reads when no code of that object reads it (see [Version 7](#version-7)) | high / medium |
| `P-gnu-section` *v3* | a non-padding gap inside one GNU object's LOCAL section run whose every relocation comes from that object's functions through its own LOCAL section symbols. *v4*: or from data inside the object's own LOCAL section runs | high |
| `P-mw-unit` *v3* (row) | in a provider plan, a Metrowerks-compiled provider unit of the plan's library (a provider path, or a known name such as `989snd.c`) whose artifacts `A-dwarf-cu` .. `A-local-block`, `A-between` or `D-referenced` decide: a provider row with the unit, its single provider path, `archive_member.object` `<stem>.o` and `linked: "unknown"`. The provider-scope `A-between` accepts functions the graph proves of that same library, and `D-referenced` data that is not another library's | - (entries keep their rule) |
| `O-provisional` (row) | exactly one file under `src/` has the unit's exact name: `provisional_file` and `workspace_path` | - |
| `O-path` (row) | no file of that name in any case; the single `Z:\dev` path names an existing module directory | - |
| `H-dwarf-header` | a decided authored function's header compile unit: an existing `Z:\dev` header under its module directory, or a provider header `<name>` with its library; reason `template`, `weak` or `inline` | - |
| `H-template-family` *v4* | an owned MSL template instance (inline or WEAK; MSL-classified or `std`/`Metrowerks`-qualified) without a header compile unit of its own: the one MSL header `<name>` that every instance of its class (or function) template with a header compile unit names. Several headers, or no such instance, leave the emit open with that reason. *v6*: also LOCAL MSL function template instances; a function template's family is its overload (see [Version 6](#version-6)) | - |
| `H-class-header` *v4* | an owned implicit special member (`__ct__`, `__dt__`, `__as__`; inline or WEAK) of an authored class without a header compile unit of its own: the one existing workspace header the header compile units of the class's other members name. A class whose members have none is defined in its source file (no emit); a provisional header declaration is not evidence | - |

Boundary functions between two units that no version 4 rule reaches,
functions with no anchor on one side, conflicting anchors, non-padding gaps
outside a GNU section run, MW-compiled provider members without a unit
anchor (no GNU object) and provider units in authored scopes stay open.

Version 4 rests on three regularities of the reference ELF, measured on the
graph `7bd4e540...` with the version 3 anchors (`A-dwarf-cu` ..
`A-local-block`) as ground truth; each rule is a proof given its
regularity, which has no counterexample:

- R1 kept copy: no reference to an inline (binding 13) or WEAK function
  comes from a function of another object placed before it (0 of 2,609
  cross-unit references between anchored functions; 496 same-unit
  references run forwards). The linker keeps the first definer's copy, so
  a caller placed before the copy is in the copy's object, and contiguity
  puts everything between them there too. A caller placed after the copy
  proves nothing.
- R3 key function: a GLOBAL vtable is emitted with its key function, one of
  its class's own non-inline virtuals (all 162 GLOBAL vtables have one; the
  75 without one are binding 13; 11 of 11 anchored single-candidate pairs
  agree; an anchored vtable's unit is among its anchored candidates' units
  78 of 78 times). A vtable decided by `D-referenced` does not count: 3 of
  56 anchored vtables are read only by another unit's inline ctor/dtor
  copies.
- R4 contiguity: an object's `.text` is contiguous (0 interleavings among
  2,836 anchored functions).

Each rule needs an authored unit and, for every function it decides or
spans, no GNU object start, no conflicting anchors, no provider-proven
function and no strong or medium candidate of another unit. The three run
to a fixed point after `A-between`; `D-referenced` then runs on the result
(it feeds nothing back). On the whole graph no kept-copy span holds two
decided units and no anchored vtable has all its candidates elsewhere.

R2 (a WEAK copy closes its object) is not a rule. It has a counterexample:
`swap<Ui>` 0x172ac0, WEAK and DWARF-placed in database.cpp, precedes
database.cpp's GLOBAL `LoadWorld` 0x172b60 (1 of 162 anchored WEAK
functions). And none of its positive uses excludes a third object: a
GLOBAL after a unit's WEAK tail may start an unnamed object (segment 027
has one), and a WEAK copy after a unit's last anchor may belong to an
object without GLOBAL functions. It only feeds the `S-weak-order`
suggestion.

#### Suggestions (version 4)

Every still-open function or data row of an authored or data scope may
carry `suggest`: `{"owner": "<unit>", "rule": "<rule>", "confidence":
"medium|low", "basis": "<one line>"}`. A suggestion is never a decision:
the planner accepts it (`source plan decide`) or decides otherwise, and
`draft --check` ignores suggestions. `draft.suggested` counts them.

| Suggestion | Owner | Confidence |
| --- | --- | --- |
| `S-sole-referencer` | an inline/WEAK copy every referencing function of which (through data, so its `__sinit` and vtables count) is decided for one unit; for data, every referencing function is decided or suggested for one unit. *v6*: a decided data site (a GLOBAL vtable emitted with its key function) counts by its own unit, the copy's own references back to itself do not count, and a copy placed before the unit's first decided function is suggested only when that function is the next decided one; data that v6 withholds (COMMON, or GLOBAL outside the run) gets one with the flanks in `basis` | medium when the unit flanks the copy's run (data: the weakest suggestion; withheld data: low when a flank names another owner), else low |
| `S-class-flank` | the function's mangled class has decided members in exactly one of the two flanking units. *v6*: not past an undecided function of a unit-less cluster between the function and that flank | medium when the class has no decided member elsewhere, else low |
| `S-weak-order` | a WEAK copy with only inline/WEAK copies between it and the left unit's last decided function: the left unit; a GLOBAL after such a WEAK copy: the right unit, unless an unnamed object lies between. *v6*: neither points past an undecided function of a unit-less cluster | low |

Suggestions that disagree keep the first in that order at low confidence
and name the others in `basis`. On the wave-1 plans (segments 013, 015,
018, 019, 023, 027 and 040), 30 of the 86 suggestions on rows the v4 draft
leaves open name the planner's owner and none names another; the other 56
are rows the planners kept unresolved.

`draft.open_header_emits` lists decided instances whose emit no rule
resolves; version 4 adds `draft.open_header_emit_reasons` (artifact ->
why).

Version 4 was measured on the graph `7bd4e540...`. Over the 46 segment
plans it leaves 2,285 artifacts open against version 3's 2,604
(`A-kept-copy` 297, `A-contiguity` 7, `A-vtable-key` 4, then
`D-referenced` 10 and `P-gnu-section` 1 more); 1,043 open rows carry a
suggestion. The 9 segments not yet planned (014, 016, 020, 021, 022, 024,
025, 026, 039) go from 1,124 to 995 open. Every decision agrees with the
23 existing plans (8,369 artifacts, 0 disagreements), including the 43
rows of the wave-1 plans that the three new rules decide, all of which
their planners had decided the same way by hand. It adds 605
`H-template-family` and 6 `H-class-header` emits; 138 emits stay open with
a reason (119 because no instance of the template has a header unit, e.g.
`std::deque`, `std::__list_imp`, `std::remove_copy`; 19 header units with
no existing workspace header). The emits agree with all 17 of accepted
segment 001's; version 4 adds two that 001 lacks, the implicit
destructors of `CMenuState` 0x140940 (`fts_state.h`) and `CSaferStr`
0x140ab0 (`zutil.h`), whose other members' header units name those
headers (001 is a version 1 plan, so its check is unchanged). Of the
provider plans, SCE goes from 4 to 0 open (`P-gnu-section` 3, `C-fill`
1: 0x15b0cc), the unidentified GNU objects from 2 to 1 (`C-fill`
0x163ddc), newlib from 3 to 2 (`P-gnu-section` 0x466e60) and Medius from
122 to 119.

#### Version 6

Being read by one unit does not make a GLOBAL that unit's: a GLOBAL can be
defined in a file that never reads it. CVisual's statics
(`m_specMapTexture` 0x476610 ...), read only by database.cpp, lie between
zvid_init.cpp and vis_main.cpp data; the CSnd statics `m_DisplaySounds`
0x47644c and `m_debugMusic` 0x476450, read only by options.cpp, inside
zsnd_csnd.o's run; MSL's `id__Q23std8ctype<c>` 0x475660, read only by
iostream.cpp, after locale.cpp's `.sbss` data. Data sections keep link
order (each object's contribution to an output section is contiguous), so
version 6 decides GLOBAL data by `D-referenced` (authored and
provider-unit) or by the "referenced only by" fallback of `P-gnu-data`
only when it lies strictly inside the referrer's own data run: the nearest
data artifacts before and after it in its output-section region that an
anchor or containment rule places (unit anchors; a GNU object's cluster,
LOCAL section run or data-only object) both name that unit or object. A
region ends at a data-window edge, where the GNU section envelope (or the
pair around it) changes, at a linker section symbol (`__data_end`,
`__bss_start`, ...) and where file bytes end (the end of the last
file-backed gap before a window's first NOBITS gap). LOCAL and binding-13
data are decided as before. Otherwise the row stays open; its reason names
both flanks, and in authored plans it carries an `S-sole-referencer`
suggestion (low when a flank names another owner). Authored COMMON rows
now get that suggestion too (low).

The suggestions change in three ways. A copy's referrers count a decided
data site by its own unit: an inline destructor read only through its
class's GLOBAL vtable (emitted with the key function, anchored to the
class's unit) is that unit's, not that of the factory that reads the vtable,
and the copy's own references back to itself no longer block it. The first
definer keeps a copy, so a copy placed before its referencing unit's first
decided function gets the suggestion only when that function is the next
decided one, since the unit's object can start at the copy
(`erase<CAiEventHandle>` 0x180520, read only by seal_ai.cpp, is
ai_events.o's and now gets none). And `S-class-flank` and `S-weak-order`
never point past an undecided function of a unit-less (unnamed) cluster
between the function and that flank.

`H-template-family` also covers LOCAL MSL function template instances
(`find`, `remove_copy`, `swap`, ...). A function template's family is its
overload: each parameter's class template, `*` for any other type, so
`swap(__vector_deleter&, __vector_deleter&)` takes `<vector>` (its
instance 0x3cbf20 has that header unit) and the generic `swap(T&, T&)`
takes `<msl_utility>` (0x172ac0). When no instance of the overload has a
header unit, the emit is MSL's defining header (`MSL_FUNCTION_TEMPLATE_HEADERS`:
`find`, `find_if`, `remove_copy`, `remove_copy_if`, `remove_if`, `transform`,
the sort and heap helpers and `lower_bound` in `<algorithm>`, `__advance` in
`<iterator>`), provided every instance of the template that has a header
unit names that header too. In authored scopes `draft.open_row_header_emits`
lists the emit each open function takes once a planner owns it in an
authored unit (the header rules do not depend on which unit), and
`--check` proves such an emit row with its `draft_rule` for a hand-owned
authored function as it proves a drafted one. Accepted segment 027's
LOCAL `std::find` copy 0x229fc0, open at draft time, has `<algorithm>`
there, and segment 023's seven open `__list_deleter` copies have `<list>`.
`source plan decide` copies such an emit when it puts the function in an
authored row (round m17; before, the planner added the row).

Version 6 was measured on the graph `c79d76e6...` against the 44 plan files
under `build/source-plans/`. Of their 259 drafted `D-referenced` (or
referenced-only `P-gnu-data`) GLOBAL rows, 103 lie inside their unit's run
and 156 stay open (152 between two different owners, 3 in a region with no
placed data, 1, `aiCameraRangeFilter__11CSealCtrlAi` 0x474f60, inside
seal_ai.cpp's run); 67 of the 156 are segment 024's fts_net_* statics,
whose `.sbss` stretch has no anchored data but whose referrers form
contiguous per-unit groups. Every version 6 decision agrees with the plans
(17,044 artifacts, 0 disagreements; version 5 disagreed on 10, all GLOBAL
`D-referenced` rows the planners had overridden). Of the suggestions on
rows the planners decided, 585 name the planner's unit and 80 another
(version 5: 444 and 306). The drafts emit 41 more headers, and 157 open
rows carry an open-row emit. Versions 1 to 5 draft byte-identically.

#### Version 7

A GNU object's LOCAL section run (or cluster) can reach over another
object's data: `gopt` 0x438750 lies inside SCE libmc 0x171070's `.data`
run (cut at a foreign artifact, not at a section symbol) and is read by
database, options, main, st_core, thezoom and two hud units, never by
libmc; `team_table` 0x438770 after it only by orders.cpp. Version 7
therefore never decides by `P-gnu-data` (cluster, run or the "referenced
only by" fallback) a named datum (GLOBAL, or LOCAL or WEAK with a symbol)
that code reads (functions or gaps, followed through data) when no code
of that GNU object, and no code of another GNU object of the same library
(newlib's `__mprec_bigtens` read by dtoa), reads it. The datum is not given to the object; the
later rules still see it (`D-referenced` with its version 6 position test
in authored and data scopes, the provider-unit rules in provider plans),
and when it stays open its reason starts with why `P-gnu-data` passed it
over: `GLOBAL gopt is read by 11 function(s) (thezoom.cpp 3, ...) but by no
code of GNU object 0x171070On the graph `c79d76e6...` the guard passes over 1 of the 445 drafted
`P-gnu-data` rows of the plan files: `gopt` 0x438750 in the data plan, read
by game code and by no libmc code. Without the same-library exemption it
also passed over 8 GLOBALs read only by other objects of the same provider
library (newlib's `__mprec_bigtens`/`__mprec_tinytens` and
`__malloc_trim_threshold`, libcdvd's `_sceCd_*` data, the asrspi callback
tables), which their runs' owners keep. Every plan keeps checking under its
own version; `--rules 7` lists such rows as drafted rows the rules leave open.

ecking under its own version; `--rules 7` lists those rows as drafted
rows the rules leave open.

Version 3 was measured on the graph `7bd4e540...`. It decides 84 of
989snd's 110 artifacts against version 2's 26 (`989snd.c` as one
`P-mw-unit` member: 20 anchors, 17 `A-between`, 21 `D-referenced`); all 84
agree with the accepted hand plan, so 58 of its 84 hand rows are drafted
and 26 stay open (the 20 leading API functions before the first LOCAL
anchor and 6 data objects). It decides 525 of MSL's 529 against 133. Of the MW
runtime's 64 hand member rows it decides 3 (`gcc_wrapper.c` by its DWARF
unit); the other members have no unit anchor. newlib goes from 428 to 449
of 452, agreeing with the hand plan on `__mprec_tinytens` (mprec.o),
`__malloc_trim_threshold` (mallocr.o) and `__infinity` (the data-only
s_infconst.o, now GNU object `0x447c00`), and decides 20 non-padding `.rodata`
gaps (`P-gnu-section`; its planner placed 19 by hand before the split); lgAud's two out-of-slice
storage gaps (now in its slice) are `P-gnu-section` too. libgcc's two GOFAST
objects are `P-gnu-object` rows in its slice.

`source plan draft --check <plan>` re-drafts under the rules the plan was
drafted with (its `draft.rules_version`; a plan with no recorded version
predates version 2 and is checked under 1), or under `--rules`, and refuses
any entry, owner row or header-emit row that keeps a `draft_rule` but
differs from the rules (or that the rules leave open). A version 1 plan
therefore keeps checking exactly as it did; `--rules 2` shows what version 2
would decide (as overrides). Likewise every plan drafted under version 3
keeps checking under version 3 (versions 1 to 3 draft exactly as before
version 4), and `--rules 4` lists version 4's new decisions as overrides
for the reviewer; a planner who wants them redrafts or accepts them by
hand. To decide such a row differently, remove its
`draft_rule`: it becomes hand-written. The report counts `drafted_entries`,
`hand_entries` and `open_rows`, and lists `overrides` (artifacts the rules
decide that the plan places elsewhere), `owner_changes` and
`header_emit_changes`. Those list every row that differs from the fresh
draft: a row whose `draft_rule` was removed (`draft_rule-removed`), a row
the draft left open that the plan decided (`decided-open-row`), changed
fields (`fields` maps each, an `archive_member` key as
`archive_member.<key>`, to its draft and plan value), a plan row the draft
has no row for (`hand-row`) and a draft row the plan dropped (`dropped`).
The scrutinizer reviews the hand-written rows, the overrides and these
changes without regenerating the draft; the drafted rows are proven.

On the reference graph `837c03c4...` version 1 decides 88 of segment 001's
89 artifacts (open: `0x142130`, between main.cpp and gcc_wrapper.c), 144 of
segment 017's 147 (open: the inline `GetBBox` and `Rotate` copies other units
call, and `zAnimQuadAlignTick` on the tick/load boundary; the
`zanim_load.cpp` row needs its path), and the 31 alignment gaps of the MW
runtime plan (its 64 MW-compiled members stay open). Every decided artifact
agrees with the planners' hand plans of these items.

Version 2 was measured on the 322 WEAK or binding-13 functions that DWARF
places (`A-dwarf-cu` or `A-dwarf-header`). Every one is a single copy. 128
are provider-proven (MSL), so the rule never reaches them. Of the 194 in
authored code, 172 lie strictly between two anchors of one unit with
nothing of another unit between, and all 172 belong to that unit (68 of
them are called from other units, so version 1 would leave them open);
none lies between another unit's anchors. The other 22 sit at a unit edge
(16 belong to the unit before, 6 to the unit after) and stay open. Over the
46 segment plans version 2 decides 17,013 artifacts and leaves 2,602 open,
against version 1's 16,671 and 2,944 (342 more decided, in 33 segments).
It decides segment 017's `GetBBox` and `Rotate` copies for
`zanim_cmd_tick.cpp`, as its planner did by hand, and gives crt0's row
`linked: "object"`; the 13 provider plans' counts are unchanged.

### Plan schema `socom-source-owner-plan` v2

Schema 2 adds optional fields to schema 1; a schema 1 plan stays valid as
written and may not use them. The values below are illustrative.

```json
{
  "kind": "socom-source-owner-plan",
  "schema_version": 2,
  "work_item_id": "socom:work:source-segment-001",
  "scope": {"kind": "segment", "segment_id": "socom:source-segment:<id>", "segment_number": 1},
  "graph_sha256": "<the item's batch graph_sha256>",
  "slice_sha256": "<the item's batch slice_sha256>",
  "target": {"source_sha256": "00c9cee7f75b921fda1e848d04f64881b5a0b7841300591cac91371bb23d4f8a"},
  "owners": [
    {
      "translation_unit": "main.cpp",
      "classification": "authored",
      "workspace_path": "src/Apps/FTS/main.cpp",
      "original_path": "Z:\\dev\\Apps\\FTS\\main.cpp",
      "provisional_file": "src/Apps/FTS/main.cpp",
      "library": null,
      "archive_member": null,
      "confidence": "medium",
      "draft_rule": "O-provisional",
      "evidence": ["original path Z:\\dev\\Apps\\FTS\\main.cpp", "draft rules A-dwarf-cu 17, A-local-block 20"],
      "artifacts": [
        {"artifact": "socom:function:0x140460", "confidence": "high", "basis": "dwarf-cu ... pc 0x140460-0x1404ac", "draft_rule": "A-dwarf-cu"},
        {"artifact": "socom:function:0x142130", "confidence": "medium", "basis": "called from CMenuState's ctor; 16-aligned after allocate<char>"},
        "socom:data:0x4444b8"
      ]
    },
    {
      "translation_unit": "gcc_wrapper.c",
      "classification": "provider",
      "workspace_path": null,
      "original_path": "<the gcc_wrapper.c DWARF path>",
      "provisional_file": null,
      "library": "MW runtime",
      "archive_member": {"gnu_object": null, "object": "gcc_wrapper.o", "linked": "object"},
      "confidence": "high",
      "evidence": ["PS2 Support source compiled with the project, not an archive member"],
      "artifacts": ["socom:function:0x142140"]
    }
  ],
  "header_emits": [
    {"artifact": "socom:function:0x140bc0", "header": "src/gamez/zGame/zgame.h", "reason": "inline", "evidence": ["dwarf-cu-header zgame.h"], "draft_rule": "H-dwarf-header"},
    {"artifact": "socom:function:0x1410f0", "header": "<string>", "library": "MSL", "reason": "template", "evidence": ["dwarf-cu-header ...\\Include\\string"]}
  ],
  "annotations": [
    {"artifact": "socom:function:0x140460", "relation": "defines", "section": "main", "path": "src/Apps/FTS/main.cpp"},
    {"artifact": "socom:function:0x1410f0", "relation": "emits", "section": "main", "path": "src/Apps/FTS/main.cpp"}
  ],
  "unresolved": [{"artifact": "socom:gap:0x1421a0", "reason": "fill between objects; no owner evidence"}],
  "retire_files": [{"path": "src/Apps/FTS/empty.cpp", "reason": "empty, no evidence", "evidence": ["0 bytes"]}],
  "contradictions": [
    {"artifact": "socom:function:0x140d00", "provisional_file": "src/Apps/FTS/main.cpp", "line": 42, "kind": "signature",
     "elf_evidence": ["main 0x140d00 reads $a0/$a1: int main(int, char **)"]}
  ],
  "notes": [],
  "reservation": {"directories": ["src/Apps/FTS"], "status": "confirmed", "reason": "main.cpp's Z:\\dev module", "evidence": ["Z:\\dev\\Apps\\FTS\\main.cpp"]},
  "draft": {"rules_version": 1, "graph_sha256": "<graph>", "decided": 88, "open": 1, "rules": {"A-dwarf-cu": 17}}
}
```

Schema 2 additions (each optional):

- an `artifacts` entry may be an object `{artifact, confidence, basis,
  draft_rule}`: `confidence` and `basis` come together; the row's
  `confidence` may not be stronger than its weakest entry's and equals it
  when every entry carries one. Consumers read entries through
  `source_plan.artifact_ids(owner)`;
- an owner row's `draft_rule` (its paths come from that rule) or `"draft":
  "open"` (refused: the planner must decide its paths); an unresolved row's
  `"draft": "open"` (refused: own it, or keep it with a real reason and drop
  the marker); a header-emit row's `draft_rule`; the plan's `draft` block;
- `archive_member.linked`: `archive` (the default), `object`, a toolchain
  or SDK object compiled with the project rather than taken from an archive
  (crt0.s, PS2 Support `gcc_wrapper.c`), or `unknown` when the evidence does
  not say (so the archive default is not a claim). `library` still names the
  provider family the plan covers;
- `archive_member.archive`: the archive the member came from, by file name
  only (`liblgaud.a`; never a path), and `archive_member.version`, its
  version string (`1.06`), when the ELF evidences them (lgAud's own
  `liblgaud.a is version %d.%02d` literal);
- a provider header: a header-emit row with `library` and a header spelled
  `<name>` (MSL `<string>`). The owner's file emits the template or inline
  body by including it, so its annotation is an `emits` edge in the owner's
  workspace file instead of `defines`; no workspace header is written;
- `contradictions`: each place where existing provisional source disagrees
  with what the ELF decides, as `{artifact, provisional_file, line, kind,
  elf_evidence}`. The artifact lies in the plan's slice, or is another
  artifact of the graph when `provisional_file` is a file an authored row
  of this plan owns (its `provisional_file` or `workspace_path`: the plan
  owns what that file defines); `provisional_file`
  names an existing file under `src/` exactly (checked at its new path once
  the apply moved it; a retired one is accepted); `line` is a line of that
  file or null for a file-level contradiction; `kind` is a lowercase slug
  (`defined-elsewhere`, `signature`, `missing`, ...); `elf_evidence` lists
  the ELF evidence lines. Plans written before the field record
  contradictions as `notes` lines starting `contradiction:`, which stay
  valid (the report notes them);
- an owner row's `name_basis`: where an authored row's unit name comes
  from. `evidence` (the default when absent) means the ELF names it: the
  graph knows the unit. An authored object the ELF does not name (no DWARF
  unit, `__FILE__` string or static initializer; its object cluster names
  neither a unit nor a library) is still owned, not left unresolved (user
  decision of 2026-10-31): when exactly one existing provisional file of
  the module already defines its functions, the row takes that file's name
  with `name_basis: "provisional"`, cites it as `provisional_file` and has
  confidence `medium` (at most); otherwise the planner invents a
  descriptive file name from the object's main class (`zsys_spr.cpp`) with
  `name_basis: "invented"` and confidence `low`. When one object or two is
  unproven, one row covers them and a note says so. The object need not
  have a LOCAL cluster in the slice: a proven object with none (an
  unnamed run of functions, a `.vutext` gap) or whose clusters lie outside
  the slice (its RTTI and vtables in `.rodata`) is owned the same way;
- an unresolved row's `suggest` `{owner, rule, confidence, basis}`: the
  drafter's suggestion for a row it leaves open (`owner` is an owner key of
  the plan). `source plan decide --accept-suggestion` records it as a hand
  entry; a row the planner keeps unresolved may keep it for the reviewer.

`reservation` is optional, and only a segment plan has one. It is required
when the apply's reservation is inferred.

### Validation

`source plan validate` refuses a plan unless all of the following hold:

- no string of the plan (key or value, anywhere) holds a control character
  U+0000-U+001F, with no exception: a path whose `\apps` went through a
  string escape holds BEL (U+0007) and `pps` instead, which is corrupted
  evidence.
  Each is reported by its JSON path (`$.owners[0].evidence[1]`);
- its work item is a stage 4 plan item, and its scope, graph digest and slice
  digest are the item's. The graph's own digest must hold, and the slice
  regenerated from the graph must equal the decomposed slice;
- every slice artifact is in exactly one owner row's `artifacts` or in one
  `unresolved` row with a real reason, and nothing outside the slice is
  listed;
- an owner row has a classification (`authored`, `provider` or
  `compiler-generated`), a confidence (`high`, `medium` or `low`), and
  evidence lines. An `original_path` must be a path the graph's evidence
  quotes, naming the same unit;
- an authored row names a source unit. Its `workspace_path` lies under
  `src/`, is a source file (headers only declare or emit), and keeps the
  unit's file name and the letter case of existing directories. A path that
  already exists must be cited as `provisional_file`, and a
  `provisional_file` must name an existing source file exactly. A different
  workspace path is a move. One row per unit and per file;
- a provider row has its library and an `archive_member` (a GNU object
  address of the graph and/or an object name), and no workspace or
  provisional file. In a provider plan its library is the plan's library.
  One row per archive member. A function or gap of a GNU object must be
  owned by the provider row naming that object. When the graph marks the
  object's end uncertain, a mismatch is a review note instead. A provider
  row in a segment or data plan is a review note: that plan's apply records
  it in tracker evidence as a provider apply does and writes nothing for it
  under `src/`;
- a compiler-generated row (fill or output no unit defines) carries no path,
  library or member;
- a header-emit row names an artifact owned by an authored row and a header
  under `src/` (in its existing letter case and, in a segment plan, inside
  the reservation, because the apply writes the `emits` edge there) or a
  provider header (`<name>` with its library), with a reason that matches
  the symbol: `weak` (WEAK binding), `inline` (Metrowerks binding 13 or
  WEAK) or `template` (template arguments in the name);
- no `"draft": "open"` marker remains;
- `annotations` equals the derived set exactly. That set is a `defines` edge
  in the owner's workspace file for every named artifact of an authored row
  (an `emits` edge there for a provider-header row's artifact), and an
  `emits` edge in the header of every workspace header-emit row. An artifact is
  named when one of its names is not compiler-invented (`@N`, `@N@` thunks,
  `__RTTI__`, `__vt__`, `__sinit_`, `.p__sinit_`). The section is the census
  section that opens the artifact's load segment (`main`; `heap` for
  `0x5e7f00`). `--fill-annotations` writes the derived set into the plan
  first (and reports `mutation_performed: true` when that changes the file);
- a `retire_files` row names an existing file under `src/` exactly that no
  row cites, with a reason and evidence. The apply deletes it with history;
- a `contradictions` row (schema 2) has exactly its five fields as above,
  and is not listed twice. An artifact outside the slice must be an
  artifact of the graph, and its `provisional_file` a file this plan's
  authored rows own;
- `name_basis` (schema 2) is `evidence`, `provisional` or `invented`. An
  `evidence` authored row of a schema 2 plan names a unit the graph knows
  (in a schema 1 plan another name is a review note). A `provisional` or
  `invented` row is authored; its unit is no unit the graph knows; none of
  its artifacts lies in a cluster that names a unit or library or has a
  strong or medium unit candidate (when none lies in a cluster at all, a
  review note says so); `invented` has confidence `low`; `provisional` cites the
  provisional file it is named after as `provisional_file` and has
  confidence `medium` or `low`. Its paths, reservation and annotations are
  checked as for any authored row;
- an unresolved row's `suggest` (schema 2) has exactly `owner`, `rule`
  and `basis` strings and a `confidence`;
- a unit (an authored or provider row's `translation_unit`) that another
  plan also names, among the plans of plan items awaiting acceptance or
  accepted (read at their packet path `build/source-plans/<slug>.json`),
  has the same `classification`, `workspace_path` and `original_path`
  there: one unit is one file whichever plans own its artifacts. A
  disagreement with an accepted plan is a problem; with a plan still
  awaiting acceptance it is a review note, because whichever is accepted
  first decides and the other then fails. An `original_path` only one of
  the two rows cites (the other null) names no other file, so it is a
  review note either way. Such a plan whose file is missing or unreadable
  is a review note. The report lists `shared_units`
  `{unit, item, status, agrees}`;
- in a segment plan, every authored row's `workspace_path` and
  `provisional_file` lie in a directory the plan's apply reserves, because
  the apply may write (or move from) nowhere else. A plan that places an
  owner elsewhere records the correction in `reservation`, with status
  `corrected`, the directories the apply needs, a reason and evidence
  lines. Status `confirmed` must repeat the reservation exactly. An inferred
  reservation must be confirmed or corrected; its skeleton status
  `inferred` is refused. Directories are `src` or paths under `src/`, in the
  letter case of existing directories. A provider or data plan has no
  `reservation`.

The report also gives the `reservation` the plan's owners were checked
against and, for a segment plan, `reservation_shared_with`: for each of
those directories, the other segment apply items whose reservation is the
same directory, contains it or lies inside it (their current `resources`).
Such applies write the same directories, so the coordinator runs them one
at a time. It also lists review notes: owned artifacts whose classification
differs from the graph's candidate or that have no candidate (`unknown`),
uncertain GNU object ends, provider rows outside a provider plan, owned
inline (binding 13) or WEAK functions that no header-emit row emits (their
owner's file defines them), `provisional` or `invented` rows none of
whose artifacts lies in a cluster, contradictions about artifacts outside
the slice, and `contradiction:` notes that a new plan records in
`contradictions`. A plan with contradictions counts them in
`summary.contradictions`. The `source plan emit-check` of the plan (above;
the plan as given, the other plan files for unit decisions) adds its counts
as `summary.emit_check` (`missing_emits`, `missing_notes`,
`wrong_citations`, `undetermined`) and, when any of the first three is not
zero, one review note naming the first artifacts and the command that
lists them; when the query cache cannot be built the note says the check
was not run. These are for the scrutinizer and do not make
the plan invalid. `--output <file under build/>` writes the whole report
there (JSON) and prints only its verdict, summary and the counts of
problems and review notes; the exit status is the same.

### Reopening an accepted plan

```powershell
python tools/socom.py progress reopen-source-plan --item <socom:work:source-segment-NNN | source-provider-...> `
  --by <name> --reason "<why the plan must change>" --evidence "<line>" [--evidence ...] `
  --expected-revision <n> [--dry-run]
```

This sends an accepted segment or provider plan back to its planner. A
reason and at least one evidence line are required. The reopener may not
be the plan's handoff owner. The command holds the tracker lock and
refuses a stale revision, like every mutation. It is refused when:

- the item is not an accepted `source-plan-segment` or
  `source-plan-provider` item (a data reconcile is not reopened), or it
  is leased;
- its `-apply` item has started: it is leased, `in_progress`,
  `awaiting_acceptance` or `accepted`, or it has an apply record, a
  handoff, an acceptance, review history or a reservation correction;
- another item that waits for the plan has started. The data reconciles
  wait for every plan, so once one is claimed, handed off or accepted, no
  plan is reopened.

The item returns to `ready` with its ID, batch and evidence. Its handoff
and acceptance move to a `review_history` entry (`reopened_by`,
`reopened_at`, `reason`, `evidence`, `accepted`, `handoff`,
`handoff_evidence`), which `progress show` displays. The apply and any
ready data reconcile return to `blocked`. The plan file is not touched.
The planner revises it, revalidates it and hands off again. The independent
accepter must differ from that new handoff's owner.

Once the stage gate is accepted, an accepted plan or data reconcile is
corrected through an amendment instead
([Amending an accepted plan](#amending-an-accepted-plan)).

## Query cache (`source sql`)

```powershell
python tools/socom.py source sql "SELECT id, name, tu, tu_strength FROM artifacts WHERE item = 'socom:work:source-segment-017' AND kind = 'function' AND tu IS NULL"
python tools/socom.py source sql "SELECT r.site_artifact, a.tu FROM refs r JOIN artifacts a ON a.id = r.site_artifact WHERE r.target_artifact = 'socom:function:0x1bfe80'" --format json
```

One read-only `SELECT` or `WITH` statement (`--limit`, default 200;
`--format text|json`) over `build/cache/source-graph.sqlite`. A `;` inside
a string literal (`'a;b'`), a quoted identifier or a comment belongs to the
statement; only a separator followed by another statement is refused. The cache is
derived from `--graph` (default `build/source-graph/graph.json`, written
from the ELF when missing or with `--from-elf`), the ELF facts the graph
does not store, the census and the `src/` file list, and is rebuilt whenever
one of them changes. Addresses are integers (`printf('0x%x', address)`
prints hex); IDs spell them in hex. `--output <file under build/>` writes
the result (in `--format`) there and prints only its columns and row count.

| Table | Rows |
| --- | --- |
| `artifacts` | every artifact: `id`, `kind`, `address`, `end`, `size`, `name`, `names`, `binding`, `weak`, `inline`, `named`, `section`, `input_section`, `window`, `cluster`, `gnu_object`, `classification`, `library`, `class_weak`, `class_evidence`, primary `tu`/`tu_strength`/`tu_via`, `emitted_from_header`, gap `fill`/`padding`/`labels`, `segment`, slice `item`, `common` (a COMMON allocation) |
| `names` | each symbol name of an artifact with `binding` and `symbol_index` |
| `tu_candidates` | each unit candidate (`rank` 0 is primary) with `strength`, `via`, `sinit_order` |
| `signals` | each graph signal with `signal`, `strength`, `tu`, `path`, `text`, full `json` |
| `units` | each unit with its `paths`, provider `library`, `sinit_order`, anchored counts and first/last function |
| `gnu_objects` | each GNU object: `address`, `gcc_compiled`, `end_basis`, `library`, `library_basis`, function and gap counts, `anchor`, `data_only`, `data_count`, `segment_library` (the library the cuts follow, when refined) |
| `object_sections` | per-object LOCAL-bracketed section runs: `gnu_object`, `library`, `data_only`, section `name`, `symbol_index`, `start`, `end`, `end_basis`, `next_start` (the next input section), `artifacts`, first `named` artifacts, and `room_for_member`: 0 when the run reaches the next input section (no room for a separate member), 1 when another object's artifact, a COMMON allocation, a file-bytes/zero-fill change or the window end cut it short |
| `clusters` | each multi-member object cluster: `member_count`, `units`, `libraries`, LOCAL symbol range |
| `segments`, `internal_boundaries` | each segment (family, library, item, edges, unanchored counts) and each unit change inside it with its unanchored functions |
| `scopes`, `slices` | each plan item's scope and counts, and its slice in order |
| `refs` | every relocation: `site`, `site_artifact`, `target`, `target_artifact`, `type`, and its symbol (`symbol_binding` LOCAL ties site and target to one object) |
| `dwarf_cus`, `dwarf_lines` | every compile-unit DIE (`kind` object, function, header or other; `object_unit` whose `.debug` contribution holds it) and every `.line` row |
| `file_strings`, `sinit` | `__FILE__`-like strings per referencing artifact; `__sinit_`/`.p__sinit_` artifacts with their order |
| `local_symbols` | every LOCAL symbol in symbol-table order with its artifact and cluster: index runs are local-symbol blocks |
| `contradictions`, `provisional_files`, `meta` | graph contradictions, `src/` files, and the cache's input digests |

## Notes for the apply route

- Read owner entries through `source_plan.artifact_ids(owner)`: schema 2
  entries may be objects.
- A provider-header emit has no workspace header: its artifact's edge is
  the `emits` edge in the owner's workspace file that `annotations` lists.
- A segment or data plan may own provider rows; the route records them in
  tracker evidence as for a provider plan.
- `archive_member.linked: "object"` marks an object linked directly (crt0,
  `gcc_wrapper.c`), not an archive member; `"unknown"` makes no claim.
  A provider apply records `linked`, `archive` and `version` with each
  member when the plan gives them (`source-provider-member ... archive:<name>
  version:<v> linked:<kind>`), and counts schema 2 entry objects.

Cross-plan consistency is the gate's job. A unit owned in several plans (its
text, its `__sinit` function in the static-initializer segment, its data in
a reconcile) must keep one workspace path, one original path and one
classification.

## Apply items and the gate

Apply items use the role `socom-source-worker`. A segment apply's allowed
paths are its reserved `src/` directories (or the accepted plan's corrected
`reservation`). A provider apply (skill `socom-provider-boundary`) writes no
file and has no allowed path. Both packets name the accepted plan's
`--check` validation, the apply route with `--dry-run` first, the source
audits (`audit docblocks`, `audit source-trace`, `guard source-placement`)
or `guard provider`, and the acceptance commands for the verifier.

### Opening the route gate

```powershell
python tools/socom.py progress open-capability-gate `
  --item socom:work:source-correlation-apply-route --expected-revision <n> [--dry-run]
```

A `capability-gate` item is accepted only by this command. It needs an
active row of the capability registry (`source-correlation-apply` in
[TOOL_COVERAGE.md](TOOL_COVERAGE.md)) that lists the gate under `opens`,
serves the gate's stage, and whose commands are all registered. The item
becomes `accepted` by `progress open-capability-gate`, with the capability,
its digest and its commands as evidence. `progress audit` refuses a gate
accepted any other way. The applies then become ready as their plans and
the data reconciles are accepted.

### The apply route

```powershell
python tools/socom.py progress apply-source-plan --item <socom:work:...-apply> `
  --owner <lease-owner> --expected-revision <n> [--check] [--dry-run]
```

The command works under the apply item's lease. The paired plan item must
be accepted, and the plan file at the packet's path
(`build/source-plans/<slug>.json`) must have a SHA-256 that the accepted
item's evidence cites. A plan edited after acceptance is refused as stale.
The plan must still validate against the graph (`--graph`, or `--check` to
regenerate it from the ELF) and the current workspace. A segment apply
then, in one locked tracker mutation:

1. moves each authored row's `provisional_file` to its `workspace_path`
   when they differ;
2. deletes the `retire_files`, recording each path, size and content
   SHA-256 (git history keeps the content);
3. writes the generated annotations with `source annotate` (below), creating
   a missing owner file or emit header with the docblock only;
4. refuses before writing anything if any moved, created, written or
   deleted path lies outside the reservation. A `corrected` plan
   reservation is re-reserved on the item (`resources` and
   `batch.directories`), and the decomposed directories are kept in
   `batch.reservation_correction`;
5. records `source_apply` on the item: the plan path and SHA-256, an
   owner-map digest (scope, owner rows, header emits, unresolved rows), the
   annotation digest and count, the reservation, the moves, creates and
   retired files, and every file it leaves written with its SHA-256. The
   record's lines (`source-plan`, `source-owner-map-sha256:`,
   `source-file`, `source-moved`, `source-created`, `source-retired`,
   `source-reservation`) are added to the item's evidence.

If the tracker write fails, every file is restored. A rerun under the lease
is idempotent: moved, created and retired files that the record names are
taken as done, and only drifted blocks are rewritten.

A provider apply refuses a plan with authored rows, header emits,
annotations or retired files. It writes no file and records each provider
row's archive member as `source-provider-member <library> gnu_object:<addr>
object:<name> artifacts:<n>`.

`progress work handoff` keeps the record and its evidence lines, and refuses
a source apply that has no record. It also refuses one whose files no longer
match the record, and `progress work accept` does the same. A rejected
apply keeps its record (with a copy in the review history), because its
files stay applied, so the rework reapplies the same plan idempotently.
Once the record names the plan file's SHA-256, `source plan validate`
checks the files the apply moved, created and retired in their applied
state. Every other check is unchanged.

### Generated annotations

```powershell
python tools/socom.py source annotate --plan <accepted plan> --check
python tools/socom.py source annotate --plan <accepted plan> --write --owner <lease-owner>
```

The command writes exactly the accepted plan's `annotations`. For a segment
plan it also writes the accepted data reconciles' annotations into the
segment's own files (its authored workspace files and emit headers). Each
plan's annotations for one file form one block, and a block of the plan in
any other file is removed:

```c
/* socom-owner-annotations begin socom:work:source-segment-001
 * Generated by source annotate from the accepted owner plan; do not edit.
 * @socom-artifact defines main socom:function:0x1401e0
 * socom-owner-annotations end socom:work:source-segment-001 */
```

Assembly (`.s`) files use `#` comments. A file gets a plan's block where the
plan has annotations in it. A file the plan creates always gets its block,
which is empty when the file defines no named artifact. Blocks go to the top
of the file in plan-ID order, followed by one blank line and the file's own
content, which is kept byte for byte (newline style and byte-order mark
included). Rewriting is idempotent. The begin and end lines carry no
`@socom-` token, so `audit docblocks` and `audit source-trace` parse only the
artifact lines.

A unit owned in several plans keeps one file. For example, a unit's text
segment and its static-initializer segment both name the same workspace
path. The second apply finds the move, create or retire already recorded by
the first apply's record and does not repeat it, and `source plan validate`
checks those paths in their applied state too. Each apply then adds only its
own block. A recorded file whose whole SHA-256 changed is still accepted
when its content outside the generated blocks (`content_sha256`) is
unchanged and the apply's own blocks have not drifted.

`--check` reports drift (`missing-file`, `differs`, `stale-block`,
`pending-move`, `pending-retire`) without writing, and exits 1 on drift.
`--write` needs the lease owner of the plan's apply item. It refuses while
a move is pending, because the apply route moves files before it annotates.
Every target must lie in the apply's reservation. A data reconcile has no
annotate step of its own.

### Acceptance

The worker hands off with `progress work handoff`. An independent
`socom-verifier` runs:

```powershell
python tools/socom.py source apply-check --item <socom:work:...-apply>
python tools/socom.py source plan validate --plan <plan> --check
python tools/socom.py source annotate --plan <plan> --check
python tools/socom.py audit source-trace
```

It then accepts with `progress work accept`. `source apply-check` is
read-only. It checks that the accepted plan is unchanged, the owner-map
digest matches, every recorded file still has its SHA-256, moved-from and
retired files are gone, every recorded path lies in the reservation, and
the annotations have not drifted. For a provider apply it checks that no
file is recorded and that the archive members match the plan.

### The stage gate

The stage gate (`socom:work:source-correlation-seed`) closes the stage. It
mirrors the stage 3 close-out for a file-only stage: an independent reviewer
hands it off, a different accepter accepts it, and the acceptance records a
baseline. The generic `progress work handoff` and `progress work accept`
refuse it. `progress record-stage-baseline` refuses the stage, because the
acceptance records its baseline.

```powershell
python tools/socom.py source gate-check `
  --deferrals build/closeout-source-correlation/deferrals.json `
  --output build/closeout-source-correlation/gate-check.json [--skip-receipt]
python tools/socom.py progress work claim --item socom:work:source-correlation-seed `
  --owner <reviewer> --lease-minutes 60 --expected-revision <n>
python tools/socom.py progress handoff-source-gate --item socom:work:source-correlation-seed `
  --owner <reviewer> --summary <summary> `
  --deferrals build/closeout-source-correlation/deferrals.json `
  [--evidence <line>] --expected-revision <n> [--dry-run]
python tools/socom.py progress accept-source-gate --item socom:work:source-correlation-seed `
  --accepter <accepter> --evidence <review evidence> --expected-revision <n> [--dry-run]
```

The gate becomes ready once every apply and data reconcile is accepted.
Both routes accept `--graph` (default `build/source-graph/graph.json`),
`--check` (regenerate the graph from the ELF) and `--bridge-url`.

**Independence.** The reviewer (the gate's lease owner) and the accepter
must not have handed off any stage 4 item, including entries in the review
history. That covers planners, data reconcilers and apply workers. Neither
may be a tool maintainer (a name containing `tool-maintainer`), and the
accepter must differ from the reviewer.

**Checks.** `source gate-check` runs every check read-only and writes the
full report under `build/`, including every problem and every unresolved
artifact with the deferral that covers it. Both routes re-run the same
checks and refuse while any of them fails. The checks are:

1. preconditions, checked before Ghidra is read: the stage is decomposed;
   every other stage 4 item is accepted; the route gate was accepted by
   `progress open-capability-gate`; no item is leased except the gate,
   held by its reviewer; and no open tracker blocker names the stage;
2. strict audits and current generated metadata: `progress audit --strict`
   (with the reference census), a fresh README progress snapshot, and a
   valid issue ledger;
3. reproducible evidence: the graph is the decomposition's
   (`graph_sha256`) and verifies;
4. every accepted plan: it is unchanged (its SHA-256 is cited), it passes
   `source plan validate` in its applied state, and its apply (segment or
   provider) is accepted with a record of that plan and its owner map and
   passes `source apply-check`. A segment plan must also pass
   `source annotate --check` with no drift;
5. no blocking conflicts: across plans, a translation unit keeps one
   workspace path and one classification, and so does a workspace path. Two
   different stated original paths conflict, while a null original path
   (a data reconcile's row) agrees with any;
6. `audit docblocks` and `audit source-trace --require-complete`, whose only
   permitted error is the line listing exactly the unresolved rows;
7. the deferrals (below);
8. the live receipt over the `ghidra-reconstruction` stage scope
   (`progress stage-scope`, then `ghidra receipt`), read without saving. It
   must equal that stage's baseline receipt (`f8912398...`) and scope
   digest. An unreachable bridge or a failed preflight refuses with
   nothing recorded.

**Deferrals.** The gate decides no unresolved row. Each unresolved artifact
of an accepted plan must be covered by exactly one deferral, and a deferral
may not name any artifact that is not unresolved. The reviewer supplies
them in a deferral file:

```json
{
  "kind": "socom-source-gate-deferrals",
  "schema_version": 1,
  "deferrals": [
    {"id": "speech-gaps", "artifacts": ["socom:gap:0x2a1c40"], "reason": "fill between objects; no owner evidence",
     "issue": "socom:workspace-issue:<id>"},
    {"id": "data-literals", "artifacts": ["socom:data:0x4444b8"], "reason": "no referencing unit",
     "approval": {"by": "user", "at": "2026-11-02", "decision": "<the user's words>"}}
  ]
}
```

Each deferral has a lowercase-slug `id`, its artifacts, a reason and
exactly one basis. The basis is either `issue`, an open workspace issue
that records the user's decision (as the stage 3 deferrals were recorded),
or `approval`, the user's decision given at gate time, quoted with its
date. The handoff records the normalized deferrals on the gate. The
accepter re-checks those recorded deferrals, not a file, and each cited
issue must still be open.

**Records.** The handoff stores a `source_gate` record on the gate. It holds
the reviewer, the graph origin, the deferrals, and the candidate baseline
`state` with its digest. The handoff adds evidence lines for the baseline
(`source-file-baseline-sha256:`), the kept stage 3 receipt, the deferrals
digest and the counts. The acceptance recomputes the state, requires the
reviewed digest, and accepts the gate with `route: progress
accept-source-gate`. It moves the state to the stage row's `baseline`
(kind `source-file-baseline`), which also names the reviewer, the accepter
and their evidence, and the stage's `accepted_evidence` cites the baseline
and the receipt. A rejected review (`progress work reject`) moves the
record to the gate's review history.

The baseline state records:

- the graph digest;
- each accepted plan: its path, SHA-256 and owner-map digest, its owner,
  owned and unresolved counts, its apply, and its annotation digest and
  count;
- the `@socom-artifact` edges under `src/`, as a count and a digest;
- every applied file's current SHA-256, as a count and a digest;
- the unresolved rows: their count, their kinds and a digest;
- the deferrals: their count, artifact count, bases and digest;
- the kept stage 3 receipt and scope digest.

`progress audit` checks the record on every mutation. A gate in
`awaiting_acceptance` or `accepted` needs a review record. An accepted gate
needs `route: progress accept-source-gate` and a baseline whose digest
matches its state and the reviewed digest. The audit also checks:

- the stage 3 receipt it kept;
- that each plan's SHA-256 is cited by its item;
- that each apply record names the plan and owner map;
- that the deferrals cover exactly the unresolved count;
- the reviewer and accepter independence.

`audit source-baseline [--strict]` also checks the workspace. The
`@socom-artifact` edges under `src/` must still match the baseline, because
annotations change only through accepted stage 4 work, and an accepted plan
file must not have changed. A missing plan file (under the disposable
`build/`) is reported as unavailable, and is an error with `--strict`.
Applied files are reported (`apply_files_unchanged`) but never fail,
because later stages edit source bodies. Both audits use the stage's
current baseline, which an accepted amendment replaces (below).

**Stage 5 skeleton writes.** A file that an accepted stage 5 skeleton item
wrote counts as its stage 4 state in `source apply-check`, in the gate's
recomputed state and in `audit source-baseline` when three things hold: the
file is still that record's after-content, its stage 4 blocks are
byte-identical, and the record's before digest is one that stage 4 recorded.
So the baseline digest still holds. An orphan the item deleted counts as a
retired file in `source plan validate`'s applied state. `progress
apply-source-plan` and `source annotate --write` refuse a file that a
skeleton item in review or accepted wrote, until that item is reopened
([Skeleton route](FUNCTION_ORDER.md#skeleton-route)).

### Amending an accepted plan

```powershell
python tools/socom.py progress amend-source-plan --item <accepted plan or data reconcile> `
  --by <name> --reason "<why the plan must change>" --evidence "<line>" [--evidence ...] `
  [--reapply <segment apply>] --expected-revision <n> [--dry-run]
python tools/socom.py progress accept-source-amendment --amendment socom:source-amendment:NNN `
  --accepter <name> --evidence "<review evidence>" [--deferrals <file>] `
  --expected-revision <n> [--dry-run]
```

Once the stage gate is accepted, `progress reopen-source-plan` refuses every
plan, because its applies, the data reconciles and the gate have started.
An amendment corrects an accepted segment plan, provider plan or data
reconcile instead, and invalidates explicitly what was built on it. Before
the gate is accepted the amendment route refuses: use
`progress reopen-source-plan` or `progress work reject`.

**Opening.** `progress amend-source-plan` needs a reason and at least one
evidence line, and the opener may not be the item's handoff owner. It
refuses an item of another stage, a leased item, an item that is not
accepted, a second amendment on an item whose amendment is open, a marked
apply that is leased or awaiting acceptance, and a stale revision. In one
locked mutation it then:

1. sends the item back for revision. Its handoff and acceptance move to a
   review-history entry (`amendment`, `amended_by`, `amended_at`, `reason`,
   `evidence`, `handoff`, `handoff_evidence`, `accepted`). The item becomes
   `ready`, or `blocked` while a plan it waits for is itself amended (a
   data reconcile waits for every plan);
2. marks the applies to re-apply: a plan's own `-apply`, or for a data
   reconcile every segment apply whose record lists it under `reconciles`,
   plus each `--reapply` segment apply whose files the revision will
   annotate. Each returns to `blocked` with a review-history entry and keeps
   its record until the re-apply replaces it;
3. records the amendment under the stage row's `amendments`: ID
   `socom:source-amendment:NNN`, status `open`, the item and its kind, the
   applies, the opener, reason and evidence, the plan's accepted SHA-256 and
   the baseline it amends.

The stage stays `accepted`. Accepted stage 4 items that wait for an amended
item (the gate, the other applies, the data reconciles) keep their
acceptance. The plan file is not touched.

**Revision and re-apply.** The planner revises the plan, validates it and
hands it off with `progress work handoff`, citing the new SHA-256. An
independent reviewer accepts it with `progress work accept`. Each marked
apply becomes `ready` once the plans and reconciles are accepted. Its
worker claims it and runs `progress apply-source-plan`. The route starts
from the files the previous apply left: its moves, creates and retired
files count as done, and `source plan validate` checks the revised plan in
that applied state. It rewrites the generated blocks, makes any move or
create the revised plan adds, and replaces the record. The new record names
the amendments (`amendments`, evidence line `source-reapply`). The previous
record moves to the review history (`replaced_at`). A marked apply is not
handed off or accepted until it is re-applied, and the verifier accepts it
through the usual route (`source apply-check`, `progress work accept`). If
a reconcile's revision annotates the files of a segment that was not
marked, the acceptance refuses with that segment's annotation drift: open
an amendment on that segment's plan (handed off unchanged) and accept both
together.

**Acceptance.** `progress accept-source-amendment` names every open
amendment (`--amendment` is repeatable), because the baseline covers the
whole stage. It refuses until every amended plan and apply is accepted and
every marked apply was re-applied for the amendment. The accepter must not
have opened any of the amendments or handed off an amended item (the
planners and re-apply workers, review history included), and must not be a
tool maintainer. It re-runs every gate check (preconditions, strict audits,
plans, applies, annotations, cross-plan consistency, completeness) with the
deferrals in force. It reads the live receipt over the stage 3 scope, which
must still equal that stage's baseline (`f8912398...`). An unreachable
bridge or a failed preflight refuses with nothing recorded.

The acceptance records the recomputed file baseline as the stage row's
`baseline`, with `amendments`, `previous_baseline_sha256`, the accepter and
the evidence. The previous baseline moves to `baseline_history` with
`superseded_at` and `superseded_by` (each amendment and its reason). The
stage's `accepted_evidence` also cites the new
`source-file-baseline-sha256:` digest. Each amendment becomes `accepted`,
with `route: progress accept-source-amendment` and the new digest.

**Deferrals.** The gate's recorded deferrals are never rewritten. The
deferrals in force are the gate's, with each amendment baseline's
`deferrals_resolved` and `deferrals_added` applied in order. A deferred
artifact that no accepted plan leaves unresolved leaves the deferrals in
force with a note naming the amendment, and a deferral left empty is
dropped. An amendment may not add an unresolved row without a basis: each
new unresolved artifact needs a new deferral in `--deferrals` (a
`socom-source-gate-deferrals` file whose IDs are new), citing an open
workspace issue or the user's decision as at the gate.

**Audits.** While an amendment is open, `progress audit --strict` lists it
under `open_amendments`; it is not an error. `audit source-baseline` lists
it too, with the amended plan files (which may change) and the re-applied
applies. Until one of its applies is re-applied, the annotation edges must
still match the baseline. After that, an edge difference is reported as
`annotation_edges_pending_amendment`, not an error, until the acceptance
records the next baseline and its checks cover every edge. `progress audit`
also validates the chain: the first entry is the gate's reviewed baseline;
each later one follows the one before, names the amendments accepted with
it, keeps the stage 3 receipt and records the deferrals in force; each
superseded entry names the amendments that replaced it, with their reasons.
A gate's reviewer and accepter stay independent of the work they reviewed:
handoffs made after the gate's acceptance do not count against them.
