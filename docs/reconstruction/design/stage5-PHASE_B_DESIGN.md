# Stage 5 Phase B: skeleton generator design (measured)

Date: 2026-11-01. Round m26, design only: no code, no tracker change, no `src/` edit.
Inputs: `build/stage5/PROPOSAL.md` (Phase B/C split, D3, D4 and its signature rule),
`docs/reconstruction/FUNCTION_ORDER.md` "Order plans", the 46 drafted segment plans in
`build/order-plans/` (plus the link plan), and m25's Metrowerks mangler (`tools/_socom/mw_mangle.py`,
assumed to map scope, name, params and const to a mangled name).
Measurements were read-only. Outputs are in `build/stage5/phase-b/*.json`. To rerun them, use
`python build/stage5/phase-b/scripts/measure_{sig,decl,src,data,misc,cover}.py .`, in that order.

**Scope measured:** 219 units (all `.cpp`; 39 have DWARF lines). They hold 4,638 function rows
(3 `in_class`), 1,862 data rows and 1,221 `not_placed` rows. The plans also list 1,865 copies and
5,742 literals as stage 7 targets.

## 1. Signature inputs per function definition

| Piece | Source (no live Ghidra) | Covered | Missing |
| --- | --- | --- | --- |
| scope, name, params, `const` | the mangled name (`mwdemangle` today, m25 for the reverse) | 4,636 mangled (3,933 member, 703 free; 189 `const`) | 2 C-linkage rows (`main`, `TRC_PreparePowerOff`): they need `extern "C"`, and their params are not in the name |
| static vs instance | stage 3 prototype (explicit `this`); otherwise a rule (`__ct__`/`__dt__`, a vtable slot) | 3,098 stage 3 + 373 rule | 89 only in a provisional header, 373 none |
| return type | stage 3 prototype; ctor/dtor need none | 2,629 typed + 301 not needed | 318 only in a provisional header, 1,388 none (`undefined` or Ghidra's default prototype) |
| parameter names | stage 3 names; `build/param-names` | 1,984 rows with only real names | not needed: stubs leave parameters unnamed, and moved bodies keep their own names |
| named types | `src` declarations; otherwise the DWARF 1 or stage 3 type | 4,229 rows have every type declared | 207 rows need a type exported, 200 rows name a type with no record (pointer and reference uses need only a forward declaration) |
| member declared in a class body | provisional `src` class bodies | 1,012 | 2,123 missing from an existing body; 798 rows belong to 156 classes with no body at all |

Covered by accepted evidence (identity, member kind, return type and a recorded type): 2,919 of 4,636.
Of those, 1,018 are already fully declared in `src`.

**Where the stage 3 prototypes are.** They are cached in the repository. The stage 3 closeout receipt
`build/closeout-ghidra-reconstruction/receipt-stage-2.json` (receipt `f8912398…`, the recorded
stage baseline) holds the signature of every function in scope (9,703). Only 962 authored
definitions still have Ghidra's default prototype, which stage 3 left `unresolved`.
`fp-closeout.json` adds all 51,840 data items with their types, and all 1,733 type names with sizes.
Layouts are not cached: the receipt carries them for only 28 types.

Every Ghidra writer item in the tracker is a stage 2 or stage 3 item, and all are accepted, so the
cache should equal the live program. The design does not assume that:

- **B0 export (read-only):** `ghidra receipt --scope build/stage5/skeleton-scope.json --output
  build/stage5/skeleton-receipt.json`. The existing command already returns layouts and enums for
  the types it is given. The scope lists the classes the signatures need, the static-member and
  data-row types, and the stage 3 function scope.
- The generator accepts the export only when its function-index digest equals the stage 3
  baseline's `indexes.functions.sha256` (`156178ab…`).
- Known gap: the receipt does not read back types whose names are ambiguous ignoring case, unions,
  or function definitions. Those come from DWARF instead.

**Spellings the generator must handle:**

| Case | Rows |
| --- | --- |
| nested scope `Q2…` (namespace vs class is not in the name) | 622 |
| nested-type parameters | 488 |
| anonymous namespace `@unnamed@<file>@` | 109 |
| function-pointer parameters | 26 |
| 128-bit code `1` | 11 |
| varargs | 8 |
| member pointers | 3 |
| local classes (`Local$N`) | 2 |

A scope component is written as a namespace only when `src` declares `namespace X`. Otherwise it is
a class.

## 2. Declarations

There are 631 type chains in signatures:

| State | Chains |
| --- | --- |
| declared in a `src` header | 339 |
| enum | 14 |
| namespace | 2 |
| forward declaration only | 2 |
| undeclared | 274 (153 of them are member scopes, 30 are passed by value) |

77 undeclared types have DWARF records, and so live Ghidra types; 199 have no record anywhere. Data
needs more:

- 913 data rows are static members, and need `static` declarations in class bodies.
- 564 are plain globals.
- 385 are function-local statics.

Consequences for the emitted order:

- **Virtual functions:** 592 planned definitions are vtable targets. The plans hold 167 `__vt__`
  and 407 `__RTTI__` generated rows. Class bodies must declare virtuals in vtable-slot order (from
  the ELF vtable relocations), with bases from RTTI or DWARF. Otherwise the vtable or RTTI moves or
  disappears. Metrowerks' rule for where a vtable is emitted is unverified, so Phase C (C2)
  calibrates it.
- **Inline in headers:** 87 planned out-of-line definitions are currently in-class bodies in
  provisional headers. Left there, they would become copies, not definitions. They move out of
  line, with their bodies unchanged.
- **The 3 `in_class` rows** (`CAiLinePtItr`) stay in their class body. They are emitted only after
  a real caller, so they behave like copies (see BD8).
- **Header contention:** 55 headers declare classes that have planned members. 25 of them have
  members from more than one segment (up to 7). 344 member rows have their header outside their segment's apply directories.
  26 of the 40 apply directories are shared by more than one apply item. This drives BD3.

## 3. Existing provisional code (606 definitions in 105 of 276 `.cpp` files)

The brace scanner found all 606 definitions; none failed to parse. Mapping uses the plan rows of the
file's own unit, by scope, name and then arity. m25's mangler later replaces arity with an exact
name match.

| Result | Defs | Phase B action |
| --- | --- | --- |
| maps to the file's own unit | 342 + 12 by arity | move into place unchanged (mechanical) |
| owned by another unit (88 in unit files, 68 in the 57 orphan `.cpp` files) | 156 | cross-file move to the owner, which keeps the stage 4 edges true |
| overloads that name and arity cannot separate | 10 | settled by mangling the declarator |
| copies only (inline or WEAK) | 24 | BD4: header body or `inline` (stage 7 places them) |
| artifact owned by no authored unit (stage 4 deferred or provider) | 38 | BD4 |
| no ELF function (helpers, inlined code) | 24 | stays in the preamble if it emits nothing, otherwise BD4 |

At least 7 mapped bodies have a declarator whose arity disagrees with the ELF name: for example
`CMatrix::CMatrix()` against 16 floats, and `CSTable::CSTable()` against `(Ui, Ui)`. That number
rises once types are checked (BD6).

Other file content:

- 343 `#include` lines and 523 comment lines: stay in the authored preamble.
- 200 file-scope data definitions: become data entries.
- 6 conditional and 2 `#define` lines in the whole tree: no blocker.
- The 57 orphan `.cpp` files carry no annotations and appear in no plan.

**File layout and regeneration:**

1. The stage 4 annotation blocks, byte-identical.
2. The authored preamble (includes, macros, file-scope declarations and helpers), untouched.
3. One entry per definition, fenced `/* @socom-skeleton <stub|body> <mangled> */`, in plan order.
   Fences carry no addresses.

A `stub` entry is regenerable only while its text equals the canonical stub, checked by digest. An
edited stub becomes a `body`, and `body` text is only ever moved, never rewritten. Moves read from a
frozen body snapshot (`build/stage5/provisional-bodies.json`, with path, span and SHA-256), so donor
and recipient applies are independent. A stage-level check confirms that each snapshot body lands
exactly once.

## 4. Data definitions

| Region | Rows | Initialized bytes | Relocated | Ghidra-typed | Sizes |
| --- | --- | --- | --- | --- | --- |
| `.data` (8) | 57 | 47 non-zero, 10 zero | 7 | 11 | 12-2,332 |
| `.rodata` (12) | 87 | 37 non-zero, 50 zero | 12 | 20 | 2-572 |
| small data (18, from `__data_end`) | 369 | 359 non-zero, 10 zero | 19 | 115 | 1-8 |
| `.sbss` (21) | 881 | nobits | 0 | 158 | 1-8 |
| `.bss` (23) | 467 | nobits | 0 | 136 | 10-160,000 |
| region 1 | 1 | zero (256 KiB, LOCAL) | 0 | 0 | 262,144 |

There are no authored COMMON rows (region 24 has 0 units). The small regions hold only objects of 8
bytes or less, and `.data` and `.bss` only objects of 10 bytes or more. That is consistent with a
`-G8` threshold, which C1 must pin as a flag.

A skeleton data row is written as follows:

- Its type: DWARF, then stage 3, then the provisional declaration if its size agrees. Otherwise a
  type sized from the access widths reported by `recon global-facts`, flagged unproven.
- `static` for LOCAL rows (1,132).
- An initializer from the ELF bytes for file-backed rows. Relocated words become `&symbol`. The 20
  zero-filled `.data` and small-data rows get an explicit zero initializer, and C2 must confirm
  that it keeps them out of `.bss`.
- `const` for `.rodata`.
- No initializer for `.sbss` and `.bss`.

Declaration order follows the plan positions. Stage 7 keeps padding and fill, literal pools,
alignment gaps and byte equality.

## 5. Units and row classes Phase B writes or skips

- **C and assembly units:** none in scope (all 219 units are `.cpp`). The 2 C-linkage functions get
  `extern "C"` (`main` is unmangled by rule). The 2 data-only units (`ztwod_main.cpp`,
  `ztwod_bitmap.cpp`) get data entries only.
- **Local statics** (385; 369 have one owning function in the unit, 11 several, 5 outside):
  declared inside the owning function's stub, in counter order.
- **Static guards** (`init$N`, 315), **`__sinit_`/`.p__sinit_`** (146 + 146) and
  **`__arraydtor$N`** (13): never written. The compiler emits them when a local or file-scope object
  has a dynamic initializer, so the skeleton writes those objects with their class types. Their
  order is checked in Phase C.
- **Literals (5,742), copies (1,865), fill:** not written; they stay stage 7 targets (D3). Phase C's
  check compares definitions only.

## 6. Static checks, item flow, sizing and risks

**Checks (B2).** None of these is stage evidence.

- **S1 mangle:** every written declarator, stub or moved, mangles with m25 to its row's ELF name.
  The scope-kind and typedef table is derived from `src`.
- **S2 order:** read the fences of each written file, apply the plan rule, and compare with the
  order target. Out-of-line rows in reverse order must give the target's address order, and data
  rows must follow region address order. This reuses `order plan validate`'s predictor. Each owned
  row appears exactly once, in its own unit, and `in_class` rows sit in class bodies.
- **S3 annotations:** the stage 4 blocks are byte-identical; `audit source-baseline` keeps the same
  edge digest; `audit docblocks` and `audit source-trace` pass.
- **S4 bodies:** each moved body's digest equals its snapshot digest, except for recorded BD6
  declarator rewrites.
- **S5 guards:** no new findings. Fences must avoid `UNIMPLEMENTED`, `TODO … reconstruct`,
  provider and stub identifiers, and addresses. `guard raw-image` already reports 7,216 findings,
  all on stage 4 annotation IDs. That is a tool issue to file: exempt the generated blocks.
- **S6 optional lint:** MSVC `cl /Zs` is installed on this host, with a small compatibility prelude.
  It catches typos and proves nothing about Metrowerks.
- **Determinism:** two runs give identical bytes, and the manifest SHA-256 goes into the handoff
  evidence.

**Flow:**

1. Tool round 3 registers capability `function-order-skeletons`, and `progress
   open-capability-gate` opens `socom:work:order-skeleton-route`.
2. If BD3 is accepted, a **prepare** item runs first: it writes the header declarations, records
   the body snapshot and handles the orphan files.
3. Each `order-segment-NNN-apply` then runs: claim, `order skeleton write` under the lease,
   `order skeleton check`, then a dedicated handoff citing the manifest SHA-256. An independent
   `socom-verifier` re-runs the check and accepts. Generic handoff already refuses these items.
4. A corrected plan reruns the write: stubs are regenerated, and bodies are kept and moved.

**Sizing:** 3 tool rounds, against the proposal's 2.

| Round | Contents |
| --- | --- |
| R1 inputs | B0 export check; signature, declaration and body manifests; S1 on m25 |
| R2 generator | `.cpp` writer (fences, moves, stubs, data, local statics); S2-S5 |
| R3 declarations and route | header writer; prepare, apply and accept commands; capability; tests; docs |

Agent work is 1 prepare item plus 46 mostly mechanical applies and their verifications. About 110
rows need judgment: 10 overloads, at least 7 signature mismatches, 30 by-value undeclared types, 24
copy-only bodies and 38 unowned bodies. Unproven pieces are flagged, not decided. The largest
segment is 35 (4 units, 163 functions, 221 data rows).

**Risks:**

- **Thin provisional headers:** only 1,012 of 3,933 member definitions are declared today, so the
  generated declarations dominate the header diffs.
- **Vtables and RTTI:** emission depends on declared slot order, bases and Metrowerks' unverified
  rule.
- **Spellings:** 622 nested scopes rely on namespace-vs-class inference. The 128-bit type's spelling
  for the exact compiler is unknown.
- **Moved bodies:** they will not all compile against the new declarations. That is Phase C (C3)
  work by design.
- **Data types:** 76% of data rows are not Ghidra-typed (1,422 of 1,862). The zero-initialized
  `.data` and small-data placement, and the `-G` flag, need C2 to confirm them.
- **Stale inputs:** a stage 4 amendment (A4) or a reopened plan stales the snapshot and manifests.
  The digest chain (order target, plan, manifest) forces regeneration.

## 7. Decisions for the user

- **BD1 - Unproven return types (1,388 none, 318 provisional only) and member kinds (373 none, 89
  provisional only).** Neither enters the mangled name or the order. *Recommended:* use the best
  evidence available (stage 3, then a rule, then the provisional header). Otherwise write `void` or
  instance, flagged `unproven` in the manifest, for stage 6 to settle. *Alternative:* about 2,200
  planner decisions now.
- **BD2 - How much class body to write.** *Recommended:* additive only:
  - the missing member declarations (2,123 in existing bodies, plus 156 new bodies);
  - 913 static data members;
  - virtuals in slot order;
  - bases from RTTI or DWARF;
  - provisional data members kept.

  Full layouts wait for stages 6 and 7. *Alternative:* regenerate bodies from the DWARF and stage 3
  layouts now (about 430 classes, needs a type writer).
- **BD3 - Item structure.** *Recommended:* add one serialized prepare item before the 46 applies.
  It owns the headers and the 57 orphan files, and writes the declarations and the body snapshot.
  Segment-apply resources then narrow from directories to unit files. This needs `progress
  decompose-stage --refresh` and is a tracker change. *Alternative:* keep directory resources. 18
  headers would then sit outside their segment's resources and 26 directories serialize.
- **BD4 - Provisional code with no owned artifact.** This covers 38 unowned or deferred bodies, 24
  non-inline copies, emitting helpers, and the 57 orphan `.cpp` files. *Recommended:* move each
  into an unbuilt holding file per module, recorded in the manifest; delete orphan files the moves
  leave empty. *Alternatives:* leave them (Phase C sees extra symbols), or delete them (git history
  keeps them).
- **BD5 - Data initializers.** *Recommended:* initializers from the ELF bytes (typed where known,
  `&symbol` for relocated words), explicit zeros for the 20 zero-filled `.data` and small-data
  rows, and an access-width type flagged unproven otherwise. *Rejected:* dummy non-zero values,
  which are fabricated. *Alternative:* defer data rows to stage 7 and drop data order from stage 5.
- **BD6 - Moved bodies whose declarator contradicts the ELF name** (at least 7). *Recommended:*
  rewrite only the declarator to the ELF signature, keep the body, and flag it for C3.
  *Alternative:* stub the definition and park the old body (BD4).
- **BD7 - Fence style.** *Recommended:* per-definition fences with stub digests, as in section 3.
  Hand edits are never clobbered. *Alternative:* one wholly generated region, which is simpler but
  overwrites edits.
- **BD8 - Definitions emitted only on demand.** *Recommended:* write the objects that trigger
  guards, `__sinit_` and `__arraydtor` with their types, and verify them in Phase C. The 3
  `in_class` rows, which need a real caller body, are verified in stage 7 like copies.

## 8. Decided (2026-11-01)

- **User:** BD1 best evidence, otherwise `void`/instance flagged `unproven` for stage 6; BD4 holding
  files per module (unbuilt, recorded in the manifest), orphan `.cpp` files deleted only when the
  moves leave them empty; BD5 initializers from the ELF bytes (`&symbol` for relocated words,
  explicit zeros), access-width types flagged unproven.
- **Parent (technical, as recommended):** BD2 additive class bodies; BD3 one serialized prepare item
  before the 46 applies, apply resources narrowed to unit files - the tracker change must keep the
  accepted order plans (no re-decomposition that drops them); BD6 rewrite only the declarator and flag
  it for C3; BD7 per-definition fences with stub digests; BD8 trigger objects written, on-demand rows
  checked in Phase C / stage 7.
- Filed: workspace issue "guard raw-image reports 7,216 findings, all on stage-4 generated annotation
  IDs" (S5 needs it fixed or exempted).
