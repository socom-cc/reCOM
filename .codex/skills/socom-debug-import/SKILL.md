---
name: socom-debug-import
description: Reconstruct the Metrowerks DWARF 1 graph and plan reviewed imports into soCOM Ghidra. Use for type-identity reconciliation, anonymous or duplicate type conflicts, dependency/SCC ordering, compile-unit batches, function and variable metadata, or live import validation.
---

# soCOM DWARF import

Read [`DWARF_IMPORT.md`](../../../docs/reconstruction/DWARF_IMPORT.md). Generate
the graph and plan before any write:

```powershell
python tools/socom.py debug graph --json
python tools/socom.py debug conflicts list --json
python tools/socom.py debug import-plan --batch <work-id>
```

Retain compile-unit scope, qualified identity, raw DIE offsets/forms, exact
names, layouts, bitfields, bases, arrays, references, functions, variables,
and source/line evidence. Never merge anonymous types by repeated spelling or
hide incompatible named definitions. Apply only a leased, reviewed,
conflict-free plan through the Ghidra writer, then validate live semantics before
parent acceptance.
