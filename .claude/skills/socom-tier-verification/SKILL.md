---
name: socom-tier-verification
description: Verify active soCOM evidence tiers, Ghidra receipts, behavior, relocation facts, and candidate ELF comparisons. Use for first-divergence diagnosis, readiness review, or governed live Ghidra acceptance without claiming deferred native stages.
---

# soCOM tier verification

Root [`AGENTS.md`](../../../AGENTS.md) is authoritative.

Validate only a registered active target and report the first typed
divergence. Expected relocation type/target/provider/alias/addend facts come
from immutable reference evidence plus accepted classifications, never from
the candidate. Use `reference relocations` for MIPS pairing context.

Native object/order/call/byte producers and acceptors are currently deferred.
Do not substitute stage-status checks for semantic verification. Linked and
final candidate comparisons report `comparison_ok` separately from
`acceptance_ready`; only final validation exposes `--acceptance`, and it also
requires a complete typed ELF catalog. Live Ghidra work uses the specific
`progress advance-live-ghidra` route and an unchanged semantic receipt.
