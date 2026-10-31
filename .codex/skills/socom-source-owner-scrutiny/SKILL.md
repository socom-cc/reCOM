---
name: socom-source-owner-scrutiny
description: Independently challenge a proposed positive soCOM source-owner, translation-unit, source-shape, data-owner, or placement claim. Use before accepting boundary/source/data gates or when evidence permits competing ownership models.
---

# soCOM source-owner scrutiny

Review the complete proposed owner and dependency closure, not a favorable
address subset. Check DWARF paths, neighboring physical order, source literals,
symbol/relocation/static-init evidence, header emission, providers, tables,
globals, and exact compiler behavior.

For a stage 4 owner plan, run
`python tools/socom.py source plan validate --plan <plan> --check` and
`python tools/socom.py source plan draft --check <plan>` first; a valid plan
is only the start of the review, never its conclusion. Rows that keep a
`draft_rule` are proven by the rules; challenge the hand-written rows and the
overrides the check lists. Challenge a confirmed inferred reservation as
hard as any placement claim.

Return the strongest competing model, evidence for and against each model,
unexplained artifacts, and a clear accept/reject/block recommendation. Do not
edit source, Ghidra, or tracker state. A behavior or byte pass alone is not
source-shape proof.
