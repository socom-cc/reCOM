---
name: socom-reference-evidence
description: Inspect and verify immutable soCOM ELF32/MIPS, symbol, alias, relocation, `.mwcats`, DWARF 1, line, source-path, and compiler-comment evidence. Use when establishing reference facts, resolving contradictions, or validating stored census/provenance data.
---

# soCOM reference evidence

Use:

```powershell
python tools/socom.py reference verify --strict
python tools/socom.py reference show
python tools/socom.py debug inspect
```

Prefer the workspace-owned parsers; external tools are corroboration. Preserve
file/memory extents, exact offsets, raw encodings, aliases, paired MIPS
relocations, source strings, and unknown vendor values. Do not edit the
reference ELF or turn debug names into accepted semantics without assembly and
xref agreement.
