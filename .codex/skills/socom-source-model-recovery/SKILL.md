---
name: socom-source-model-recovery
description: Recover soCOM translation units, declarations, definitions, class or subsystem boundaries, source ownership, and compiler-emitted artifacts. Use when correlating accepted binary facts with provisional source or deciding original source/header placement.
---

# soCOM source model recovery

Read root [`AGENTS.md`](../../../AGENTS.md) and
[`SOURCE_TRACEABILITY.md`](../../../docs/reconstruction/SOURCE_TRACEABILITY.md).
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
