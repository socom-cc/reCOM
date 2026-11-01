---
name: socom-source-model-recovery
description: Recover soCOM translation units, declarations, definitions, class or subsystem boundaries, source ownership, and compiler-emitted artifacts. Use when correlating accepted binary facts with provisional source or deciding original source/header placement.
---

# soCOM source model recovery

Read root [`AGENTS.md`](../../../AGENTS.md),
[`SOURCE_TRACEABILITY.md`](../../../docs/reconstruction/SOURCE_TRACEABILITY.md)
and [`SOURCE_CORRELATION.md`](../../../docs/reconstruction/SOURCE_CORRELATION.md).
Treat current files as provisional. Use accepted Ghidra facts, DWARF
paths/lines, symbol order, relocations, static initialization, tables, and
exact compiler behavior. `python tools/socom.py source graph` gathers the
ELF-only unit signals, classification candidates and segments into
`build/source-graph/`; its rows are candidates with provenance, not owners.

Keep logical ownership distinct from physical ELF storage. Give each physical
artifact one owner; headers may declare or emit reviewed inline/template
artifacts, while one source owner defines ordinary storage. Record unresolved
competing models as blockers. Add `@socom-anchor` and `@socom-artifact` only
through reviewed source-correlation work.

A stage 4 plan item's owner plan starts from
`python tools/socom.py source plan draft --item <item> --output <plan>` (the
versioned rules decide what they can; the rest is marked `"draft": "open"`),
with `source plan evidence` and `source sql` for the open rows. It must pass
`python tools/socom.py source plan draft --check <plan>` and
`python tools/socom.py source plan validate --plan <plan> --check`:
every slice artifact owned once or unresolved with a reason, provisional
files cited exactly as they exist, the annotation targets the owner rows
imply listed (`--fill-annotations` writes them), and owners placed in the
apply's reserved directories. Confirm or correct an inferred reservation in
the plan's `reservation` row.

A stage 5 order plan item (`order-plan-segment`, `order-plan-link`) starts
from `python tools/socom.py order plan draft --item <item>`; see
[`FUNCTION_ORDER.md`](../../../docs/reconstruction/FUNCTION_ORDER.md#order-plans).
Settle only its open rows with `order plan decide`, each with its evidence,
and hand off once `order plan validate --plan <plan> --check` passes.

An accepted plan is applied under its apply item's lease with
`python tools/socom.py progress apply-source-plan --item <item> --owner <owner> --expected-revision <n> --dry-run`
and then without `--dry-run`. The route moves, creates and retires files and
writes the generated annotation docblocks (`source annotate`) only inside
the reservation. It records the plan and file SHA-256s on the item, and the
verifier checks them with `python tools/socom.py source apply-check --item <item>`.
