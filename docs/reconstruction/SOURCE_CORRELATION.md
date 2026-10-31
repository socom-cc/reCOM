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

Planning and the apply route are active. `progress apply-source-plan`
applies an accepted plan (a segment's files and annotations under `src/`, a
provider's evidence in the tracker), and `progress open-capability-gate`
opens the capability gate the apply items wait on. The route that reviews
and closes the stage gate is not registered yet, so the stage stays deferred
in [TOOL_COVERAGE.md](TOOL_COVERAGE.md).

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
window) is an authored segment, because its units own what they emit. Each
batch records the scope, `graph_sha256`, the `slice_sha256` of its artifact
list, and counts.

A segment apply reserves `src/` directories; its batch lists them as
`directories` and records `resource_inferred` and `resource_reason`. A
unit's directory is the existing spelling of its original `Z:\dev` module,
or else the directory of a provisional file of the same name. A segment
reserves its units' directories. When none of its units has such evidence,
the directory is inferred (user decision of 2026-10-31). For each unit, the
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

For the reference graph (`a3ce2165...`, 76 segments) this gives 46 segment
plans and applies, 12 provider plans and applies (MW runtime, MSL, SCE,
unidentified GNU object, newlib, libgcc, 989snd, speech middleware, Medius,
lgAud, libptt, RSA), 3 data reconciles, the route gate, and the stage gate.
The 58 plans are ready at once. One reservation is inferred: segment 057
(`zui_skb.cpp`, 88 functions, no path or provisional file) reserves
`src/gamez/zUI`, where the `zui_` units of segment 056 (`zui_cleanup.cpp`,
`zui_spec.cpp`) lie. No segment falls back to all of `src`. `progress audit`
holds the items to these rules and to the stage's decomposition record.

## Plan items

The role is `socom-source-owner-mapper`, which may write only the packet's
two paths under `build/source-plans/`. The skill is
`socom-source-model-recovery`, or `socom-provider-boundary` for a provider.
An independent `socom-source-owner-scrutinizer` reviews the plan.

```powershell
python tools/socom.py source plan evidence --item <item> --check `
  --output build/source-plans/<slug>-evidence.json --skeleton build/source-plans/<slug>.json
python tools/socom.py source plan validate --plan build/source-plans/<slug>.json --check --fill-annotations
python tools/socom.py source plan validate --plan build/source-plans/<slug>.json --check
```

`<slug>` is the item ID with `:` replaced by `-`. The evidence file lists the
slice with each artifact's names and bindings, its loaded section, whether
it is named, its classification candidate, unit candidates, input section,
GNU object and DWARF paths. It also lists the units, the GNU objects, and the
provisional files whose names match a unit. For a segment it also shows the
apply's `reservation`: its directories, whether they are inferred, and the
reason. The skeleton lists every slice artifact as unresolved with the
placeholder reason `not yet planned`, which validation refuses. For an
inferred reservation the skeleton also carries a `reservation` row with
status `inferred`, which validation refuses too. The packet of such a
segment says which directories the plan must confirm or correct. The
command never overwrites an existing plan.

Without `--check`, both commands read `--graph`
(`build/source-graph/graph.json` by default). They recompute its digest and
refuse a graph that differs from the one the item was decomposed from.
`--check` regenerates the graph from the ELF instead.

### Plan schema `socom-source-owner-plan` v1

The values below are illustrative.

```json
{
  "kind": "socom-source-owner-plan",
  "schema_version": 1,
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
      "confidence": "high",
      "evidence": ["dwarf-cu 0x140008-0x1401e0 ...", "__sinit_main.cpp, sinit order 1"],
      "artifacts": ["socom:function:0x1401e0", "socom:data:0x4445d0"]
    },
    {
      "translation_unit": null,
      "classification": "provider",
      "workspace_path": null,
      "original_path": null,
      "provisional_file": null,
      "library": "SCE",
      "archive_member": {"gnu_object": "0x14df58", "object": null},
      "confidence": "high",
      "evidence": ["gcc2_compiled. at 0x14df58", "__ps2_libinfo__ libgraph"],
      "artifacts": ["socom:function:0x14df58"]
    }
  ],
  "header_emits": [
    {"artifact": "socom:function:0x140bc0", "header": "src/gamez/zGame/zgame.h", "reason": "inline", "evidence": ["dwarf-cu-header zgame.h"]}
  ],
  "annotations": [
    {"artifact": "socom:function:0x1401e0", "relation": "defines", "section": "main", "path": "src/Apps/FTS/main.cpp"}
  ],
  "unresolved": [{"artifact": "socom:gap:0x142130", "reason": "fill between objects; no owner evidence"}],
  "retire_files": [{"path": "src/Apps/FTS/empty.cpp", "reason": "empty, no evidence", "evidence": ["0 bytes"]}],
  "notes": [],
  "reservation": {"directories": ["src/Apps/FTS"], "status": "confirmed", "reason": "main.cpp's Z:\\dev module", "evidence": ["Z:\\dev\\Apps\\FTS\\main.cpp"]}
}
```

`reservation` is optional, and only a segment plan has one. It is required
when the apply's reservation is inferred.

### Validation

`source plan validate` refuses a plan unless all of the following hold:

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
  provisional file. One row per archive member. A function of a GNU object
  must be owned by the provider row naming that object. When the graph marks
  the object's end uncertain, a mismatch is a review note instead;
- a compiler-generated row (fill or output no unit defines) carries no path,
  library or member;
- a header-emit row names an artifact owned by an authored row and a header
  under `src/` (in its existing letter case), with a reason that matches the
  symbol: `weak` (WEAK binding), `inline` (Metrowerks binding 13 or WEAK) or
  `template` (template arguments in the name);
- `annotations` equals the derived set exactly. That set is a `defines` edge
  in the owner's workspace file for every named artifact of an authored row,
  and an `emits` edge in the header of every header-emit row. An artifact is
  named when one of its names is not compiler-invented (`@N`, `@N@` thunks,
  `__RTTI__`, `__vt__`, `__sinit_`, `.p__sinit_`). The section is the census
  section that opens the artifact's load segment (`main`; `heap` for
  `0x5e7f00`). `--fill-annotations` writes the derived set into the plan
  first;
- a `retire_files` row names an existing file under `src/` exactly that no
  row cites, with a reason and evidence. The apply deletes it with history;
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
against. It also lists review notes: owned artifacts whose classification
differs from the graph's candidate, and uncertain GNU object ends. These are
for the scrutinizer and do not make the plan invalid.

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

The stage gate is reviewed by `socom-verifier`. Its packet shows the stage
is file-only: the `ghidra-reconstruction` stage scope must still produce
that stage's baseline receipt. Every accepted plan must pass `--check`, and
`audit source-trace --require-complete` must pass. Under the lean model,
that audit checks completeness against the accepted owner plans and their
generated annotations ([SOURCE_TRACEABILITY.md](SOURCE_TRACEABILITY.md)).
The route that reviews and accepts the gate, including cross-plan unit
consistency, is not registered yet.
