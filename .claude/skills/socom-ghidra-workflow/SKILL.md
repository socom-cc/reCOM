---
name: socom-ghidra-workflow
description: Inspect the live soCOM Ghidra program safely and read-only. Use for functions, types, layouts, data, xrefs, assembly, p-code caveats, dependency frontiers, analysis state, or semantic receipts without changing the project.
---

# soCOM Ghidra read-only workflow

Root [`AGENTS.md`](../../../AGENTS.md) is authoritative; read it with
[`GHIDRA.md`](../../../docs/reconstruction/GHIDRA.md). Start with:

```powershell
python tools/socom.py ghidra preflight --strict
```

Connect the `ghidra` MCP server only to project `soCOM`. Pass
`program=socom.elf` on every program-sensitive call; never rely on the active
CodeBrowser program. Address
overlay locations as `<overlay>::<hex>` with the exact case returned by
`get_address_spaces`.

Prefer assembly, immutable ELF/DWARF, relocations, and exact compiler behavior
over p-code or decompilation. Treat current names, prototypes, types, and
plugin completeness or naming judgments as provisional. Plugin Hungarian or
Pascal naming policy is not project authority; pass `strict_mode=off` when a
read-only analysis call exposes that option.

Do not open, switch, import, close, delete, save, save all, run scripts, use
the debugger, patch bytes, clear flow, rename, retype, comment, or reanalyze.
Return boundaries, address-labelled assembly, callers/callees, xrefs, types,
data extents, tables, source strings, contradictions, and analysis caveats.
