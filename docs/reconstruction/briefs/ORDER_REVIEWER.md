# Stage 5 order-plan reviewer brief

You independently review stage-5 order plans (role socom-source-owner-scrutinizer) named in your
prompt, as ACCEPTER. AGENTS.md is in context. Read docs/reconstruction/FUNCTION_ORDER.md sections
"Source-order drafts and the calibration" and "Order plans". Do not modify any file except scratch
output under build/order-plans/<ACCEPTER>/ and the tracker through the CLI. Put scripts in your own
scratch subdirectory named after ACCEPTER (other agents share the scratchpad).

Per item (status awaiting_acceptance):
1. `progress show <id>`: the handoff evidence cites `<plan> sha256:<sha>`; the file's SHA-256
   equals it. `order plan validate --plan P --check` ok (0 open, 0 mismatches, nothing stale).
2. Reproduction: `order plan draft --item <id> --output build/order-plans/<ACCEPTER>/<file>` and
   compare JSON-aware with P. A plan handed off without open rows must equal its draft; a plan
   with settled rows may differ only in those rows (each with a basis).
3. Evidence spot checks (2-4 rows per plan, more where a unit looks unusual): a `proven` row's
   DWARF definition line and its neighbours; a `hypothesis` row's position against the reverse
   address order; a `constrained` row's counter; an `in_class` row's first caller sits right before
   it; data rows in address order; `not_placed` reasons; for every settled row, challenge the
   decision against the losing evidence named in its basis.
4. Link plan (`socom:work:order-link`): equals the current `order link-spec` output and its
   static check is clean.
Decide: `progress work accept --item <id> --accepter <ACCEPTER> --evidence "<checks, rows
spot-checked>" --expected-revision <rev>` (re-read the revision right before; on a revision
conflict retry with the current revision, up to 5 times - accept re-runs validate for ~6 s before it
checks the revision, so parallel workers race), or `progress work reject --item <id> --reviewer <ACCEPTER> --reason "<artifact,
evidence, fix>"`. If one defect recurs across plans, say so once (it is a tool fix, not per-plan
chasing). Report <= 1 line per item plus recurring findings.
