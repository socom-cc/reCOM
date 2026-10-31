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
member. The artifact basis is the census-derived set that `source graph`
produces ([SOURCE_TRACEABILITY.md](SOURCE_TRACEABILITY.md)).

Planning is active. The route that applies an accepted plan's files and
annotations under `src/`, and the gate check, are not registered yet. The
apply items wait on a capability gate, and the stage stays deferred in
[TOOL_COVERAGE.md](TOOL_COVERAGE.md).

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
list, and counts. Apply batches also list the `src/` directories they
reserve. A unit's directory is the existing spelling of its original
`Z:\dev` module, or else the directory of a provisional file of the same
name. A segment with no such directory reserves `src`. A provider reserves
`src/providers/<library>`.

Dependencies:

- every plan waits for the accepted `socom:work:ghidra-reconstruction-seed`;
- every data reconcile waits for every segment and provider plan, because
  cross-unit data order is checked against the planned text order;
- every apply waits for its plan, every data reconcile, and
  `socom:work:source-correlation-apply-route`. That `capability-gate` item
  cannot be claimed, handed off, or accepted by a worker. It stays blocked
  until the guarded apply route is registered, which writes the plan's
  files and annotations, including the data its reconciles assign;
- the seed keeps its ID and becomes the stage gate over every apply and data
  reconcile.

For the reference graph (`a3ce2165...`, 76 segments) this gives 46 segment
plans and applies, 12 provider plans and applies (MW runtime, MSL, SCE,
unidentified GNU object, newlib, libgcc, 989snd, speech middleware, Medius,
lgAud, libptt, RSA), 3 data reconciles, the route gate, and the stage gate.
The 58 plans are ready at once. `progress audit` holds the items to these
rules and to the stage's decomposition record.

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
provisional files whose names match a unit. The skeleton lists every slice
artifact as unresolved with the placeholder reason `not yet planned`, which
validation refuses. The command never overwrites an existing plan.

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
  "notes": []
}
```

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
  row cites, with a reason and evidence. The apply deletes it with history.

The report also lists review notes: owned artifacts whose classification
differs from the graph's candidate, and uncertain GNU object ends. These are
for the scrutinizer and do not make the plan invalid.

Cross-plan consistency is the gate's job. A unit owned in several plans (its
text, its `__sinit` function in the static-initializer segment, its data in
a reconcile) must keep one workspace path, one original path and one
classification.

## Apply items and the gate

Apply items use the role `socom-source-worker`. Their allowed paths are the
reserved `src/` directories. Their packets name the accepted plan, its
`--check` validation, the source audits (`audit docblocks`,
`audit source-trace`, `guard source-placement`), and the apply route, which
is not registered yet.

The stage gate is reviewed by `socom-verifier`. Its packet shows the stage
is file-only: the `ghidra-reconstruction` stage scope must still produce
that stage's baseline receipt. Every accepted plan must pass `--check`, and
`audit source-trace --require-complete` must pass.
