---
name: socom-address-handoff
description: Select, reserve, and render authoritative soCOM reconstruction work. Use when starting without an explicit target, expanding a tracker item into a bounded worker packet, checking leases or resource conflicts, or deciding whether Ghidra, source, provider, or verification work is currently launchable.
---

# soCOM address handoff

Read root [`AGENTS.md`](../../../AGENTS.md). With no explicit assignment, run:

```powershell
python tools/socom.py progress next --json
python tools/socom.py progress work leases --json
```

Claim only returned ready work at the current revision. Expand an address to its
complete dependency/source-owner closure; never treat an address as source
ownership by itself. Render only real active reservations with:

```powershell
python tools/socom.py progress work packet --item <id> --owner <owner>
```

The packet is limited to its paths, target, build root, and stop condition.
The parent retains scheduling, issue routing, and acceptance.

Connect to project `soCOM` and pass `program=socom.elf` for Ghidra-backed
context. Never open, switch, import, close, delete, save, or patch another
program. Follow
[`WORKFLOW.md`](../../../docs/reconstruction/WORKFLOW.md) for stage gates.
