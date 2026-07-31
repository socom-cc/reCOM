---
name: socom-tool-maintainer
description: Maintain soCOM CLI commands, schemas, migrations, parsers, skills, roles, tests, and workflow contracts. Use for infrastructure defects or requested capabilities that do not reconstruct a game function directly.
---

# soCOM tool maintainer

Keep `tools/socom.py` as the only public gate. Preserve deterministic,
repo-relative, standard-library-first behavior, explicit mutation metadata,
dry-run safety, interprocess locking, atomic writes, and backward-readable
state through audited migrations.

Do not touch reference inputs or accept reconstruction facts while fixing
tools. Update tests, agent-surface metadata, command documentation, and
generated snapshots with the implementation. Run infrastructure doctor,
agent-surface, workflow-contract, reachability, current-metadata, workspace,
and focused unit tests before handoff.
