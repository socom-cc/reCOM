---
name: socom-validation
description: Select and run trustworthy validation for soCOM source, Ghidra, documentation, tools, tracker, compiler, order, ABI, bytes, or final ELF changes. Use for review, diagnosis, acceptance checks, or workspace health.
---

# soCOM validation

Choose the narrowest direct check, then run the applicable infrastructure
suite:

```powershell
python tools/socom.py doctor --infrastructure-only --ghidra
python tools/socom.py progress audit --strict
python tools/socom.py audit agent-surface --strict
python tools/socom.py audit retired-surface --strict
python tools/socom.py audit capability-coverage --strict
python tools/socom.py audit workflow-contracts --strict
python -m pytest -q tests/tools
```

Validation observes current live facts and fresh build output. It never repairs
the subject while verifying or claims more than the direct comparison proves.
Report pass/fail, exact command, first actionable divergence, identities/ranges,
and the narrow next action.

`audit final-elf-catalog` is a late-stage readiness check and is expected to
report incomplete during current reconstruction; do not fold that expected
semantic gap into structural workspace health.
