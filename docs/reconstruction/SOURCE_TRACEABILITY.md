# Source traceability

Source filenames and current code are provisional. Traceability begins with an
accepted physical artifact in the ELF and connects it to one source owner only
after debug, relocation, symbol, assembly/xref, and compiler evidence agree.

The minimum trace row should retain:

- artifact identity and exact section/range;
- symbol aliases and relocation coverage;
- original compile-unit path and line evidence;
- current owner candidate and confidence;
- authored, compiler-generated, SDK/runtime, or middleware classification;
- dependencies and contradictions;
- tracker evidence/work-item IDs.

Source annotations use the forms defined in `AGENTS.md`. `defines` identifies
the single physical owner; `emits` records a contribution. Headers may declare
an artifact but cannot become duplicate owners.

Review source placement with:

```powershell
python tools/socom.py source owners
python tools/socom.py source artifacts
python tools/socom.py audit docblocks
python tools/socom.py audit source-trace
python tools/socom.py guard source-placement
python tools/socom.py source annotate --plan <accepted plan> --check
```

Annotation artifact IDs must be exact IDs already present in tracker or
reference-census evidence, and section names must match the reference census.
The census-derived artifact IDs that owner plans own resolve too: one
`socom:function:0x...` or `socom:data:0x...` per start address of a sized
`FUNC` or `OBJECT` census symbol. `audit source-trace` checks one defining edge
per annotated physical artifact.

`--require-complete` follows the lean model (user decision of 2026-10-30).
It checks completeness against the accepted stage 4 owner plans and their
generated annotations, not against tracker span IDs that annotations never
cite. It requires:

- every planning scope's plan item is accepted, and its plan file is
  unchanged (its SHA-256 is cited by the item);
- every segment and provider apply is accepted, with a `source_apply`
  record of that plan;
- every artifact of a scope is in an owner row (an `unresolved` row is
  incomplete), and each plan lists as many artifacts as its scope;
- every annotation an accepted plan implies is in the source: one `defines`
  per named artifact of an authored row, in its owner's file, and one
  `emits` per header emit;
- no `@socom-artifact` line in the source that no accepted plan implies.

Compiler-generated artifacts (`@N` literals, RTTI, vtables, static-init
words, padding), unnamed artifacts and provider archive members are covered
by their owner rows' artifact lists. The report gives the owned artifact
count, the plan counts and the IDs that are missing or unresolved.

Original `Z:\dev\...` strings are quoted evidence, not active paths and not
instructions to reproduce the original drive tree. Source-correlation changes
go through reviewed owner plans ([SOURCE_CORRELATION.md](SOURCE_CORRELATION.md)).
The stage is decomposed, and its plans validated, by registered commands.
`progress apply-source-plan` applies an accepted plan's moves, creates,
retired files and generated annotations (`source annotate`). It records the
retired files' paths and content SHA-256s in tracker evidence, and git
history keeps their content. The stage gate closes through
`progress handoff-source-gate` and `progress accept-source-gate`. Any
unresolved artifact must be covered by a recorded deferral, and
`audit source-baseline` then holds the annotation edges under `src/` to the
recorded file-stage baseline.

## Translation-unit evidence: `source graph`

```powershell
python tools/socom.py source graph `
  --output build/source-graph/graph.json `
  --markdown build/source-graph/SEGMENTS.md
```

`source graph` is the stage 4 evidence producer. It reads only the immutable
ELF (symbols, relocations, bytes, DWARF 1 `.debug` and `.line`), never Ghidra,
the tracker or `src/`, and writes only the files named under `build/`. Its
output is deterministic and carries `graph_sha256` over the canonical content,
like `recon graph`. Everything in it is a candidate and it owns nothing.
`progress decompose-stage --stage source-correlation` builds the stage's
owner-plan items from it ([SOURCE_CORRELATION.md](SOURCE_CORRELATION.md)), and
its gate route closes the stage.

Artifacts are the census-derived set: one row per start address of the sized
`FUNC` (`socom:function:0x...`) and `OBJECT` (`socom:data:0x...`) symbols,
aliases kept with their census symbol IDs and bindings, plus every unsymbolled
gap between neighbours of one ELF section (`socom:gap:0x...`, with its fill,
labels and whether it is alignment padding). The input-section kind comes from
the envelope of the surviving SECTION symbols of that name; artifacts outside
every envelope say so. Code and data windows are maximal runs of one artifact
kind; a gap between runs of different kinds opens the run after it.

Signals, each kept on the artifact with its provenance:

| Signal | Strength | Meaning |
| --- | --- | --- |
| `dwarf-cu` | strong | a compile-unit DIE's pc range covers the artifact; a source path names the unit, with its `.line` range |
| `dwarf-cu-header` | hint | the covering CU is a header: the artifact was emitted from it |
| `dwarf-variable` | strong / weak | a static local's location names its CU; a global is listed by every CU that uses it |
| `file-string` | strong / medium | a `__FILE__`-like string: a whole `@N` literal (strong) or a string inside other data, with the artifacts whose relocations reach it |
| `unnamed-namespace` | strong | an `@unnamed@<file>@` tag in a symbol name |
| `sinit` | strong | `__sinit_<file>` and `.p__sinit_<file>`; the table's address order is reported as `sinit_order` |
| `libinfo` | strong | `__ps2_libinfo__` names an SCE library |
| `literal-pool` | weak | the artifact sits in a run of rising `@N` numbers whose anchored members name one unit |
| `class-hint` | weak | the demangled qualifier's anchored methods all sit in one unit |

Clusters are object files proven by union: a relocation against a LOCAL symbol
or a section symbol ties its site to the target (gaps never join, since one
gap may hold several objects' bytes); a GNU-toolchain object opened by a
`gcc2_compiled.` marker or `.text` section symbol holds the functions up to the
next GNU anchor or the first function with Metrowerks evidence (a C++ symbol,
binding 13, an `@N` reference or a Metrowerks CU); clusters whose LOCAL symbol
index ranges overlap are one object (`symtab-local-order`), because the linker
writes each object's locals contiguously; and a function between two members of
one cluster joins it (`text-contiguity`). A cluster whose strong signals name
exactly one unit gives that unit to every member, strong, or medium when the
member joined only by text contiguity. Two names in one cluster, or interleaved
objects, are recorded under `contradictions` and never merged.

Classification candidates (`authored`, `provider` with a library,
`compiler-generated`, `unknown`) are decided per cluster, then per artifact, and
each lists the evidence that drove it: a GNU object (library from
`__ps2_libinfo__`, the majority of its function names, the coordinator's
speech window `0x336ef0-0x3788a0`, or its archive neighbours); a DWARF source
path (MSL, MW runtime, crt0, libptt, SCE; `Z:\dev` is authored); a unit name
with a known library or DWARF path; Metrowerks name rules (C++ runtime entry
points, the `snd_` prefix of 989snd); and otherwise an authored Metrowerks
unit. Compiler-emitted symbols (`@N`, `__RTTI__`, `__vt__`, `__sinit_`,
`.p__sinit_`, adjustor thunks) and alignment padding outside provider objects
are `compiler-generated`. Weak results (contiguity between two artifacts of one
class, C++ outside the `std` and `Metrowerks` namespaces) are marked `weak`.
The rules themselves are echoed under `rules`.

Segments are contiguous runs of at most `--segment-size` functions (default
200) inside one code window. They always cut where the classification changes
(compiler-generated and unknown functions are neutral) and otherwise at the
last strong anchor (a GNU anchor or a change between anchored units), then the
last medium one (the edge of an anchored unit or an object-cluster change), and
only then at the size limit. Each segment lists its artifacts (with the
window's leading and trailing gaps on its outer segments), the data slice
referenced only from it (followed through referencing data; unreferenced data
follows its cluster), its classification mix, the unit candidates seen inside
it with their `sinit_order`, and each boundary's strength, reason and run of
unanchored functions. `summary` counts artifacts per classification, signal
coverage, cluster edges, contradictions, segments, and the functions without a
strong or medium unit anchor (by class and outside GNU objects).
