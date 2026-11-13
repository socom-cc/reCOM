# Stage 3 repair-pass planner brief (token-lean)

You plan the recon repair(s) named in your prompt, as OWNER. AGENTS.md is in context; do not
re-read it. Follow build/batch-helpers/PLANNER.md (its recon-repair rules and tool list) and
docs/reconstruction/RECONSTRUCTION.md "### Partial prototypes" and "## Repair item: recon
repairs" (withdrawals, keep rows). Start from `recon evidence --item`, `recon live --item` and
`recon facts --item`; candidate reports: build/repair-pass/partial-candidates.json and
build/repair-pass/withdrawal-candidates.json (leads, not evidence).

Kinds (user decisions 2026-10-29):
- partial (repairs 011-020): each listed function is an unresolved row of an applied group whose
  live signature is Ghidra's default. Give it a partial row with its proven parameters (return
  undefined), or a complete row when `recon void` (rules 20, the default) gives VERDICT void or
  the return is otherwise proven. 0x300c70 C2D::Draw (repair 019): void from its DWARF-void slot
  +0xc overrides (rules 20). A function you cannot prove becomes a keep row with keep_reason.
- void-withdraw (021-023): each is an applied `void` that `recon void` leaves open. Re-check:
  if anything proves void (DWARF, a rule, a slot family, a typed callback member), make it a
  keep row citing that proof; otherwise a `withdraws_return` partial row whose contradiction
  quotes the open VERDICT line exactly.
- header (024-027): each applied non-void return rests on a recalled SDK/C-library header
  (issue b8acf0d9). Re-prove the return from asm and callers (exit v0/f0 sources, caller use,
  DWARF, mangled names, accepted live prototypes of callees). Proven -> keep row citing that
  evidence; unproven -> `withdraws_return` row. A runtime/MSL declaration that exists in the
  workspace (cite path and line) is evidence; one only remembered is not.
Parameters must stay exactly the live ones in withdraw rows. By-value class parameters over
8 bytes are refused (keep row).

Hand off with `progress work handoff`. Scratch only under build/facts/<OWNER>-*. Claim, plan
or edit nothing else, including memory. Report <= 6 lines per repair: counts (complete,
partial, withdraw, keep), plan sha256, rows a reviewer should check first, tool gaps.
