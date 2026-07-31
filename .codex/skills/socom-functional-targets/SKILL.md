---
name: socom-functional-targets
description: Define and run focused soCOM behavioral verification targets. Use when a source owner needs reproducible behavior evidence, a deterministic smoke harness, target registration, or functional-batch validation without claiming source shape, order, ABI, or byte equivalence.
---

# soCOM functional targets

Register only deterministic targets with explicit inputs, expected outputs,
build/run commands, timeout, writable build root, and owner relationships.
Keep generated output under `build/`.

Use `verify functional` for one target and `verify functional-batch` for a
reviewed set. Report pass/fail and the first behavioral divergence. Functional
evidence never proves original ownership, contribution order, calling
convention, provider identity, or bytes; those remain independent gates.
