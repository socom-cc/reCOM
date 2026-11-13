---
name: socom-progress-tracker
description: Read and mutate the authoritative soCOM reconstruction tracker with revisions, locks, leases, reservations, handoffs, and live acceptance. Use for selecting work, inspecting linked entities, coordinating writers, recording evidence, or performing a governed tracker mutation.
---

# soCOM progress tracker

Root [`AGENTS.md`](../../../AGENTS.md) is authoritative.

Run:

```powershell
python tools/socom.py progress audit --strict
python tools/socom.py progress next --json
```

Read `show`, `find`, relationships, and dependencies before claiming. Every
mutation requires the current revision and the public CLI. Use bounded leases,
heartbeat long work, and release or hand off explicitly. Workers never edit
JSON or self-accept. Reviewers return defective handoffs with
`progress work reject`, recording the reason and evidence. An accepted plan whose
apply has not started returns for revision with `progress work reopen` (stage 3)
or `progress reopen-source-plan` (stage 4, reason and evidence required). After the
stage 4 gate is accepted, correct an accepted plan or data reconcile with
`progress amend-source-plan`, re-apply its marked applies with
`progress apply-source-plan`, and let an independent accepter record the next
baseline with `progress accept-source-amendment`. Parent live-advance commands must validate once and commit
from that same semantic result; hashes and receipts are evidence only.

After claiming, render `progress work packet --item <id> --owner <owner>`.
DWARF plan packets are file-only; their matching apply packets alone own
Ghidra. Undecomposed stage seeds are not claimable work. Use `progress migrate`
for versioned schema upgrades and never rewrite state manually.

Follow [`TRACKER.md`](../../../docs/reconstruction/TRACKER.md) for entity and
stage semantics.
