---
name: socom-reference-evidence
description: Inspect and verify immutable soCOM ELF32/MIPS, symbol, alias, relocation, `.mwcats`, DWARF 1, line, source-path, and compiler-comment evidence. Use when establishing reference facts, resolving contradictions, or validating stored census/provenance data.
---

# soCOM reference evidence

Root [`AGENTS.md`](../../../AGENTS.md) is authoritative.

Use:

```powershell
python tools/socom.py reference verify --strict
python tools/socom.py reference show
python tools/socom.py reference demangle <symbol>
python tools/socom.py debug inspect
```

`reference demangle` parses Metrowerks mangled names exactly and mangles them
back. It does not encode return types, `static` or `virtual`, or whether a
scope is a class or a namespace
([FUNCTION_ORDER.md](../../../docs/reconstruction/FUNCTION_ORDER.md#metrowerks-name-mangling)).

Prefer the workspace-owned parsers; external tools are corroboration. Preserve
file/memory extents, exact offsets, raw encodings, aliases, paired MIPS
relocations, source strings, and unknown vendor values. Do not edit the
reference ELF or turn debug names into accepted semantics without assembly and
xref agreement.
