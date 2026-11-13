---
name: socom-workspace-audit
description: Audit soCOM instructions, Claude skill and role surfaces, command registry, schemas, documentation, generated metadata, immutable inputs, and process health. Use for onboarding validation, workflow drift, missing tools, stale project dependencies, or non-address maintenance review.
---

# soCOM workspace audit

Root [`AGENTS.md`](../../../AGENTS.md) is authoritative.

This is non-address maintenance. Do not select reconstruction work or mutate
Ghidra. Run:

```powershell
python tools/socom.py doctor --infrastructure-only --ghidra
python tools/socom.py audit agent-surface --strict
python tools/socom.py audit retired-surface --strict
python tools/socom.py audit independence --strict
python tools/socom.py audit capability-coverage --strict
python tools/socom.py audit workflow-contracts --strict
python tools/socom.py audit pipeline-reachability --strict
python tools/socom.py audit docs --strict
python tools/socom.py audit docblocks --strict
python tools/socom.py audit source-trace --strict
python tools/socom.py audit live-validation-surface --strict
python tools/socom.py audit current-metadata --strict
python tools/socom.py audit workspace --strict
```

Reject competing authorities, foreign project paths/IDs/tools, literal local
account or computer names, absolute checkout/user-profile/tool paths, thin
undiscoverable harness pointers, manual live-status prose, hash-only
acceptance, unregistered commands, direct state edits, tracked local build
products, or generated artifacts outside governed roots. Use repo-relative or
environment-expanded paths in operational surfaces. Ordinary gameplay
terminology and immutable binary/debug path evidence are not workspace
dependencies.
