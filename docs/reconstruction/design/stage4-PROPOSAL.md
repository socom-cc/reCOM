# Stage 4 (`source-correlation`) decomposition proposal

Status: proposal for user review (2026-10-30). Nothing has been built or changed.
Research: read-only (docs, tracker, census, `src/`); counts spot-checked by the coordinator.

## 1. What stage 4 must produce

- Every accepted physical artifact mapped to exactly one translation-unit owner, keeping logical
  source ownership separate from physical ELF storage and provider contribution (AGENTS.md stage
  list, "Source matching"; WORKFLOW.md stage gates). Workspace placement is decided here.
- One `@socom-artifact defines` edge per artifact (headers declare or `emits` only); IDs resolve
  in tracker evidence; section names match the census. Annotations change only through accepted
  stage-4 work.
- Trace rows (SOURCE_TRACEABILITY.md): range/section, aliases, relocations, CU path/line, owner and
  confidence, classification (authored / compiler-generated / SDK-runtime / middleware),
  contradictions, work-item IDs.
- Gate: reproducible evidence, no blocking conflicts, strict audits, `audit source-trace
  --require-complete`, current snapshots. Stage 4 is file-only: the live Ghidra receipt must stay
  equal to the stage-3 baseline `f8912398...`.

## 2. Inventory

| Item | Count |
| --- | --- |
| Sized functions | 9,703 (644 WEAK, 1,247 template/inline instances emitted by headers) |
| Data objects | 10,181 (5,909 `@N` literals, 2,329 named, 1,078 mangled, 248 `__vt__`, 469 `__RTTI__`, 148 `.p__sinit`) |
| `.mwcats` exception records | 283 |
| Loaded sections | `main` (+ 4-byte `heap`); original input sections survive only as 554 SECTION symbols |
| DWARF compile units | 959 DIEs, 114 distinct paths; pc ranges cover only 879 functions (~9%) |
| Other TU evidence | 148 `__sinit_<file>` (link order, 0 inversions), 88 `__FILE__` strings (400 functions), 33 `@unnamed@<file>@` tags, 325 `gcc2_compiled.` provider-object markers; 231 distinct TU names in total |
| Rough split | ~7,100 authored vs ~2,600 provider-like functions (estimate, not a classification) |
| Current `src/` | 241 `.cpp` (112 empty) + 75 `.h`; all 316 owners unverified; 171 basenames match evidence, 70 have none, 60 evidenced files missing; 0 annotations |

Regions: crt0+MSL 0x140000-0x150000; SCE/newlib 0x150000-0x170400; authored 0x170400-0x336ef0;
speech middleware 0x336ef0-0x3788a0; mixed authored + Medius/libc/audio/libptt
0x3788a0-0x469e80; `__sinit` 0x469e80-0x471000.

Tool defects found: `audit docblocks` resolves IDs against the `symbols` collection that schema 6
removed; `audit pipeline-reachability` treats source-correlation as active without a producer.

## 3. Work-item model (about 100 items)

The unit is a contiguous address segment (<= ~200 functions, cut at strong anchors: GCC markers,
CU edges, `__FILE__` changes) plus its data slices, because TU boundaries are what is being solved.

| Kind | Count | Roles | Output |
| --- | --- | --- | --- |
| artifact registry | 1 | producer + verifier | census-derived artifacts and gaps |
| provider plan (per library: SCE, newlib, MSL, MW runtime, crt0, Medius, speech, libptt, 989snd, lgAud, RSA) | ~12 | provider classifier -> scrutinizer | owner rows per archive member; no source bodies |
| segment plan (authored) | ~40 | owner mapper -> independent scrutinizer | TU -> artifacts, path, header emits, unresolved rows |
| segment apply | ~40 | source worker | file moves/creates + generated annotations |
| data reconcile | ~5 | mapper + scrutinizer | cross-TU data order consistent with text order |
| stage gate | 1 | verifier | - |

No Ghidra writes, so items can run in parallel (locks per directory). Deferred stage-3 gaps do not
block ownership (it is decided from ELF symbols and relocations): the speech region is middleware
bounded by GCC markers; vtables follow their class's key-function TU; statics follow their function;
the unreferenced jump table 0x467e80 and the `__use_facet` instances become explicit rows.

## 4. Tool work first (the producer)

| Step | Estimate |
| --- | --- |
| Fix the two audit defects; record a missing-producer blocker | 0.5 day |
| Artifact registry (schema 7 `semantic_spans`/`storage_contributions`, stable IDs, migration) | 3 days |
| `source graph`: deterministic ELF-only TU-evidence producer -> segments | 4 days |
| Owner-plan schema + `source plan validate` (every artifact owned once or unresolved) | 3 days |
| `progress decompose-stage --stage source-correlation`, packets, audits | 2 days |
| Guarded apply + generated annotations (`source annotate --check/--write`) | 3 days |
| Gate route + file-stage baseline | 1.5 days |
| Docs, roles, mirrors | 1 day |

Total about 15-20 agent-days. Reused as-is: `source artifacts`, the audits (after the fix), guards,
the work claim/handoff/accept/reject flow, `progress sql`, `reference relocations`.

Lean alternative (coordinator note): skip the schema 7 migration and keep owner maps in plan files
plus tracker evidence, and generate annotations only for named artifacts. That cuts the tooling to
roughly 8-10 agent-days, at the cost of a less queryable registry and more work in the gate check.

## 5. Decisions for the user (recommended first)

1. Annotation density: `defines` in source for named functions and globals; compiler-generated
   artifacts (`@N`, RTTI, sinit words, padding) owned through the owner row's artifact list.
   (Alternative: ~20k annotation lines in source.)
2. Workspace placement: keep `src/<Apps|gamez>/<module>/` with evidence basenames; store the
   original `Z:\dev` path on the owner row. (Alternative: mirror the original tree, ~200 moves.)
3. Existing provisional files: keep evidenced names as owner candidates; leave the 70 unevidenced
   and 112 empty files unowned; delete only through an accepted plan, with history.
4. Provider granularity: one item per library, one owner row per archive member; no source bodies.
5. Artifact basis: the census-derived set (ELF symbols plus gaps), not only Ghidra-accepted ones.
6. Mapper write access: allow writing `build/source-plans/` only.
7. Producer scope: full producer (15-20 days) vs lean producer (8-10 days).

## 6. Risks and timeline

Risks: ~6,000 functions have no direct TU anchor and are placed by contiguity; template/weak
instance placement and the key-function vtable rule cannot be checked with the compiler (license
blocker); `__sinit` code is separated from its TUs; the 0x467e80 table has no reference; provider
vendors/versions for speech, lgAud and Medius are unknown; ownership claims are hard to falsify
before stage 5 order checks.

Timeline (estimates): tooling 3-4 weeks (lean: ~2), registry + providers ~1 week, ~40 segment plans
with scrutiny 2-3 weeks in parallel, data reconcile + gate ~1 week. Total roughly 7-9 weeks
(lean: 6-7).
