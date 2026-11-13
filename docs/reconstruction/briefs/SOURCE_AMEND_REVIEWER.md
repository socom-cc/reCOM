# Stage 4 amendment reviewer brief (user placements, amendments 008-026)

Follow build/batch-helpers/SOURCE_REVIEWER.md (role socom-source-owner-scrutinizer, as ACCEPTER),
plus these amendment checks per item. You did not plan or open any of these items.

1. Scope of change: diff the plan against build/source-plans/<slug>.prev.json (json.load both; compare
   owners, unresolved, header_emits, contradictions, reservation, notes). The only changes allowed:
   artifacts the user placed (python tools/socom.py source placements check --file
   docs/reconstruction/decisions/stage4-function-placements.md --json lists them with their item and
   heading) moved from `unresolved` into owner rows / header emits; reservation extended only for the
   new destination directories/files; notes about these placements. Anything else -> reject.
2. Each placed artifact lands where its heading says (real src/ path from the check output). New files:
   owner row `name_basis: "user"` with `decision` {file: docs/reconstruction/decisions/stage4-function-placements.md,
   sha256: fe2f75edb96e8fe022e2d298cb3ce68bb7ddc6caa2b9a4d41a0216da1e5680c4, heading as written},
   confidence medium or low. Known units: per-entry `decision`, confidence <= medium. `.h` headings:
   header-emit row for that header, the kept copy owned by the unit whose object holds it.
3. Binary consistency: the placements check reports no conflicts for the item's destinations
   (contiguity); check one or two placements against `source owner <name>` / `source sql` yourself.
   The user's decision never overrides ELF evidence: a placement the ELF contradicts is a rejection
   with the evidence (the user is told).
4. `source plan validate --plan <plan> --check` ok; `source plan draft --check <plan>` ok; cross-plan
   units (zanim_cmd_tick.cpp 016/017, seal_body.cpp 031/032, zmath.h 016/024/026) use one path.
Decide with `progress work accept --item <id> --owner <ACCEPTER> --evidence "<checks; placed N;
unresolved U->U'; plan sha256>" --expected-revision <rev>` or `progress work reject ...` with
findings. Re-read the revision before every mutation; on a conflict wait for the lock file to clear and
retry (up to 8 times). Report <= 3 lines per item.
