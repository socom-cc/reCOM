# Stage 5 order-plan planner brief

You settle the open rows of stage-5 order plans (role socom-source-owner-mapper) named in your
prompt. AGENTS.md is in context. Read docs/reconstruction/FUNCTION_ORDER.md sections "Source-order
drafts and the calibration" and "Order plans" first. Write only build/order-plans/ and the tracker
through the CLI; no src/, Ghidra writes, memory or issue ledger.

The measured rule (calibration on 36 DWARF units): functions are emitted in REVERSE source order
(99.6% of pairs); in-class members are emitted on demand right after their first caller; data is
laid out in declaration (address) order; the local-static counter (`name$N`) follows source order;
`@N` literal labels follow emission order and never decide source order. Phase C (the compiler)
settles every hypothesis later; your job is the best evidenced hypothesis, never a guess dressed as
proof.

Cycle per item (`socom:work:order-segment-NNN`, plan build/order-plans/socom-work-order-segment-NNN.json,
already drafted - do not re-draft unless validate says stale):
1. `progress work claim --item <id> --owner <OWNER> --lease-minutes 60 --expected-revision <rev>`.
2. `order plan validate --plan P` lists the open rows (kind, reason). For each, gather evidence
   (`order draft --unit <tu>`, `order sql`, `reference relocations`, DWARF lines/DIEs, asm) and
   settle it with `order plan decide --plan P --lease-owner <OWNER> --artifact <id> ... --basis "..."`:
   - `constraint-conflict`: the counter/initializer orders two rows against the rule. Find why:
     is one row an in-class or on-demand member (emitted after its first caller -> `--in-class
     --no-position`)? does the local static belong to code inlined from another function (the
     counter numbers it at the inline site)? For data, address order is declaration order; a
     static-initializer order against it is scheduling noise unless the bytes say otherwise. Keep
     the evidence that wins, class `hypothesis` (or `constrained` when the counter decides), and
     say in the basis what the losing evidence was.
   - `out-of-rule` (DWARF line against the rule): confirm the in-class member and its first caller.
   - `interleaved`: a stray copy outside the unit's main run is a stage 7 target; settle with basis.
   - `deferred-in-span`: an unresolved stage-4 row (gate deferral) inside the run; settle with
     basis only, naming the deferral category.
3. `order plan validate --plan P --check` ok (0 open, 0 mismatches), then
   `progress work handoff --item <id> --owner <OWNER> --summary "<rows settled and how>"
   --evidence "<P> sha256:<sha256 of P>" --evidence "<key evidence>" --expected-revision <rev>`.
Re-read the revision before every mutation; on a conflict retry with the current revision, up to
5 times (handoff re-runs validate before it checks the revision, so parallel workers race). Keep
scripts in your own scratch subdirectory named after OWNER. Report <= 2 lines per item.
