# Source traceability

Source filenames and current code are provisional. Traceability begins with an
accepted physical artifact in the ELF and connects it to one source owner only
after debug, relocation, symbol, assembly/xref, and compiler evidence agree.

The minimum trace row should retain:

- artifact identity and exact section/range;
- symbol aliases and relocation coverage;
- original compile-unit path and line evidence;
- current owner candidate and confidence;
- authored, compiler-generated, SDK/runtime, or middleware classification;
- dependencies and contradictions;
- tracker evidence/work-item IDs.

Source annotations use the forms defined in `AGENTS.md`. `defines` identifies
the single physical owner; `emits` records a contribution. Headers may declare
an artifact but cannot become duplicate owners.

Review source placement with:

```powershell
python tools/socom.py source owners
python tools/socom.py source artifacts
python tools/socom.py audit docblocks
python tools/socom.py audit source-trace
python tools/socom.py guard source-placement
```

Annotation artifact IDs must be exact IDs already present in tracker evidence,
and section names must match the reference census. `audit source-trace` checks
one defining edge per annotated physical artifact; `--require-complete` also
requires every accepted physical artifact to have a defining source edge.

Original `Z:\dev\...` strings are quoted evidence, not active paths and not
instructions to reproduce the original drive tree. Source-correlation changes
must use a future revision-guarded batch interface that preserves prior claims
as history; no such mutation interface is currently registered.
