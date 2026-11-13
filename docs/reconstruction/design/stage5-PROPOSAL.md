# Stage 5 (`authored-function-order`) decomposition proposal

Date: 2026-11-01. Status: proposal - six decisions for the user at the end. 2026-11-01: compiling moved from Phase B to a new Phase C (user). Nothing here is built or
decomposed yet; the stage seed stays a closed placeholder until a producer and an acceptance route
are registered (blocker `socom:blocker:deferred-stage-producers`).

## 1. What stage 5 must deliver

AGENTS.md: "reproduce authored physical contribution order". Concretely: for every authored object
file, source that the exact compiler turns into an object whose artifacts appear in the same order
as in `socom.elf` - functions, and data per section - and the order of the authored objects in the
link. Stage acceptance needs reproducible evidence and a verifier passing from a disposable clean
build; exact-compiler behavior is primary evidence.

Not in stage 5: calling conventions and ABI (stage 6), byte equality (stage 7), provider order
(stage 8). Byte matching is monotonic and starts from accepted order work.

## 2. What we have (measured today)

| Item | Count / state |
| --- | --- |
| Authored functions in the ELF | 6,565 (of 9,703) |
| Authored source files owned by stage 4 | 219 `.c/.cpp` + 39 headers; 8,920 ownership annotations |
| Rows deferred at the stage-4 gate | 561 (5 category issues), plus open issues 179 and 180 |
| Existing provisional code | about 605 function definitions in 276 `.c/.cpp` files (171 have none) - roughly 9% of the functions |
| Functions with DWARF line numbers | 655 authored (DWARF covers few units) |
| Pinned compiler | `mwcps2-2.4-001213`; its signature `2.4.1.01` equals the ELF comment `MW MIPS C Compiler (2.4.1.01)` - it is the exact compiler |
| Compiler state | assembler runs; `mwccps2` stops at the FLEXlm check ("Invalid (inconsistent) license key") - blocker `socom:blocker:metrowerks-flexlm-license`, the user's to resolve; the linker is untested |

Order evidence available without compiling (all measured during stage 4):

- **Source order from DWARF lines** (corrected by round m20, using each function's own definition
  line): functions are emitted in **reverse source order** - 4,251 of 4,268 pairs (99.6%), 35 of 36
  units exactly. All 17 exceptions are in-class members emitted on demand right after their first
  caller; kept inline copies behave the same way (609 of 668 sit right after their first user in
  the unit). Data is laid out in declaration order; the local-static counter (`name$N`) follows
  source order. The earlier "75%, a tendency" figure used each function's lowest line, which
  includes inlined code, and is superseded. The compiler still has to confirm the rule (Phase B).
- **Literal label numbers** (`@N`, a per-unit compiler counter) follow emission (address) order, not
  source order (m20: 99 of 102 DWARF pairs reversed), so they corroborate but do not decide order.
- **Data order**: `.sdata/.sbss/.bss` keep link order (0 drops); LOCAL symbol names keep one order
  across objects (6,970 of 6,970 shared pairs); static-initializer order for 148 units.
- **Copies**: WEAK copies sit at the end of their object (161 of 162); a kept inline copy comes from
  the first unit in link order that defines it (0 counterexamples in 2,609).

## 3. The central constraint

Without the compiler, stage 5 can compute the order the ELF requires (the *target*) and a best
guess of the source arrangement that produces it (the *hypothesis*), but it cannot prove
reproduction. The measured rule (reverse source order, on-demand members) is strong, so Phase A
drafts mostly follow from it; the compiler must still confirm it. Acceptance
therefore needs the compiler. The proposal splits the stage in two phases so the license does not
idle the whole stage.

A second constraint: an inline or template copy, and a string literal, is emitted only where a
function body uses it. With 9% of bodies written, their positions cannot be reproduced until real
bodies exist (stage 7). See decision D3.

## 4. Proposed design

Work unit: one authored object file, batched by the 46 stage-4 segments (their slices and owners
are accepted, so items reuse them; a few units span segments and are planned once).

### Phase A - no compiler needed (file-only)

- **A1 Order target (tool).** Per unit, from the accepted stage-4 ownership and the ELF: the order
  of its functions (with kept inline/WEAK copies at their positions) and of its data in each
  section, plus the global order of authored objects. Deterministic, with a digest like the stage-4
  source graph; a SQL cache for planners.
- **A2 Order plans (planner + independent reviewer per segment).** Per unit, the intended source
  arrangement: the definition order of its functions and data, each step with its evidence (DWARF
  lines, `@N` order, data order) or marked as a hypothesis for the compiler to settle. A drafter
  decides what the evidence fixes, as in stage 4; planners decide the rest.
- **A3 Link-order specification.** The ordered object list (authored objects, with the provider
  positions from stage 4) as a linker-order file, checked against the ELF statically.
- **A4 Correction route.** A governed reopen-and-re-apply for stage-4 plans, to fix issues 179
  (header vs `.cpp` for some inline destructors) and 180 (`team_table` owned by an SCE object), and to
  resolve deferred rows once compiled evidence decides them.

### Phase B - skeletons, no compiler needed (writes `src/`)

Split out of the compile work on 2026-11-01 at the user's request, so the license blocks only Phase C.

- **B1 Skeleton generator (tool).** From an accepted order plan, write each unit's source in the
  planned order: every definition with its exact signature (see D4), existing provisional bodies
  moved into place unchanged, a marked stub body elsewhere, and the class declarations the
  signatures need. Deterministic and regenerable: if Phase C shows the rule differs somewhere, the
  plan is corrected and the skeleton regenerated, never hand-patched.
- **B2 Static checks (no compiler; not stage evidence).** Each signature mangles back to the ELF's
  exact name (a Metrowerks name mangler in the tools, round-tripped against all mangled symbols);
  the definition order parsed from the written file predicts the order target under the
  measured rule; generated blocks and stage-4 annotations are unchanged. Optional lint: a host
  compiler's syntax-only pass catches typos; it proves nothing about Metrowerks behavior.
- **B3 Apply (per segment, writes `src/`).** Claim, generate, run B2, hand off; an independent
  verifier re-runs B2 and accepts the apply.

### Phase C - needs the compiler

- **C1 Probe harness.** Compile one unit twice with the exact compiler (flags established by probes
  and recorded), read the object's section and symbol order, compare it with the order target.
- **C2 Calibrate the emission rule** on the units whose source order DWARF records, then on the rest
  (and on the 561 deferred rows where object boundaries become provable); correct plans and
  regenerate skeletons where the rule differs.
- **C3 Per-unit verify.** An independent verifier builds each unit from a clean checkout and checks
  the object order against the target; compile errors in skeletons or moved bodies are fixed here.
- **Gate.** All units verified (or deferred with a user-approved reason); an order baseline (object
  order digests) is recorded, and the stage-4 file baseline must still hold. The stage cannot be
  accepted before Phase C: AGENTS.md requires a verifier passing from a clean build, and the
  license stays a visible blocker.

### Estimated effort (from stage-4 experience)

| Part | Tool rounds | Agent work | Wall clock |
| --- | --- | --- | --- |
| Phase A (A1-A4) | 3-4 small rounds | 46 plans + reviews, mostly drafted | about 1-2 days |
| Phase B (B1-B3) | 2 rounds (skeleton generator, name mangler and static checks) | 46 applies + verifications | about 1-2 days, no license needed |
| Phase C (C1-C3) | 1-2 rounds (probe harness, compile verifier) | 46 compile verifications + fixes | about 1-2 days after the license works |

Stage-4 lessons applied: build the drafter and deterministic checks before scaling planners; keep
tool rounds to 3-5 related fixes; run at most about 8 agents at once (12 exhausted the 5-hour usage
limit); fix recurring review findings once with a tool and a consolidated sweep, not plan by plan;
use fresh small agents for mechanical fixes instead of resuming large-context ones.

## 5. Decisions for the user

- **D1 - Compiler license (required for Phase C and the stage gate).** The pinned compiler is the exact one; it needs a
  valid FLEXlm license for feature `Win32_Plugins_MIPS_PS2`. This is yours to obtain; the workspace
  will not bypass licensing. Until then Phases A and B can run.
- **D2 - Start Phase A now?** Recommended: yes - targets, plans, the link-order file and the
  correction route are all useful once the compiler runs, and none of them writes source code.
- **D3 - Scope of stage-5 order.** Recommended: definition order only (functions and data defined
  in each file), verified by the compiler in stage 5; inline/template-copy and literal positions are
  recorded as targets and verified in stage 7, when real bodies emit them. Alternative: reproduce
  everything now with stub bodies that contain the triggering calls - more work and fragile, because
  the calls need correct argument types (stage-6 knowledge).
- **D4 - What Phase B writes to `src/`** (compiled in Phase C). Recommended: compilable skeletons - every function defined
  in its file in the planned order with its exact signature (so the compiler produces the same
  mangled names), a clearly marked stub body where no code exists yet, existing provisional bodies
  kept and moved into place, and the class declarations the signatures need. Alternative: an order
  manifest only, with no compile check until stage 7 writes bodies (cheaper now, but stage 5 would
  then prove nothing).
  Signature rule for the skeleton generator: member functions are written as real C++ members with
  an implicit `this` - never as free functions with an explicit `this` parameter, which would change
  the mangled name (`Tick__10CZSealBodyFf` vs `Tick__FP10CZSealBodyf`). Ghidra's explicit `this`
  (stage 3 prototypes) is dropped; the class comes from the mangled name; `C` before `F` makes the
  member `const`; `__ct__`/`__dt__` become constructors/destructors without Metrowerks' hidden
  arguments (the destructor's delete flag, stage 3's `__dtor_flags`), which the compiler adds itself;
  static vs instance members come from the stage-3 prototypes and their call sites. The compiled
  object's mangled names must equal the ELF's, so any slip fails the order check.
- **D5 - The 561 deferred rows.** Recommended: resolve them through the correction route as compiled
  object boundaries decide them during stage 5; any still undecidable stay deferred to stage 7.
- **D6 - Item unit.** Recommended: reuse the 46 stage-4 segments (219 authored objects) rather than one
  item per object, so planning and review batch naturally and the reservations already exist.
