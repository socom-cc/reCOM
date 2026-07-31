---
name: socom-progress-tracker
description: Read and mutate the authoritative soCOM reconstruction tracker with revisions, locks, leases, reservations, handoffs, and live acceptance. Use for selecting work, inspecting linked entities, coordinating writers, recording evidence, or performing a governed tracker mutation.
---

# soCOM progress tracker

Run:

```powershell
python tools/socom.py progress audit --strict
python tools/socom.py progress next --json
```

Read `show`, `find`, relationships, and dependencies before claiming. Every
mutation requires the current revision and the public CLI. Use bounded leases,
heartbeat long work, and release or hand off explicitly. Workers never edit
JSON or self-accept. Parent live-advance commands must validate once and commit
from that same semantic result; hashes and receipts are evidence only.

After claiming, render `progress work packet --item <id> --owner <owner>`.
DWARF plan packets are file-only; their matching apply packets alone own
Ghidra. Undecomposed stage seeds are not claimable work. Use `progress migrate`
for versioned schema upgrades and never rewrite state manually.

Follow [`TRACKER.md`](../../../docs/reconstruction/TRACKER.md) for entity and
stage semantics.
