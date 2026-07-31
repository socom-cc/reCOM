# DWARF 1 import design

The reference contains Metrowerks DWARF 1 in `.debug` and statement programs in
`.line`. `tools/_socom/dwarf1.py` implements the record, form, tag, attribute,
reference, and line-unit readers with no third-party runtime dependency.

The importer retains:

- compile units, producer/language, source paths, address ranges, and line lists;
- subprograms, parameters, locals, globals, and location blocks;
- classes, structures, unions, enums, typedefs, pointers/references, arrays,
  inheritance, fields, member offsets, and bitfields;
- raw DIE offsets/forms and unresolved references as evidence.

Run:

```powershell
python tools/socom.py debug inspect
python tools/socom.py debug graph
python tools/socom.py debug import-plan `
  --batch <socom:work-or-debug-batch-id> `
  --output build/import-plans/<batch>.json
```

The schema-version 2 plan declares `mutation_performed: false`, pins portable
Ghidra project/program/language facts, and emits a receipt scope for selected
functions and types. It emits forward declarations before full types and
reports incompatible definitions as blocking conflicts. A reviewed Ghidra
writer applies the plan; the Python planner never opens or saves the program.

Tracker schema 3 represents these as two different leases. A
`debug-import-plan-*` item is owned by the DWARF importer and can write only its
deterministic file under `build/import-plans`. After independent acceptance,
the matching `debug-import-apply-*` item becomes eligible; it is owned by the
Ghidra reconstructor and alone may acquire `ghidra-writer`. Batch plan items do
not become eligible until the accepted foundation plan has been applied.

Type identities retain their compile-unit offset/path, parent DIE, scope path,
raw name, and qualified name. Anonymous/synthetic `@...` records are keyed by
compile unit, parent, and DIE offset; identical spellings from unrelated units
are therefore not reported as false global conflicts. Named definitions still
require layout reconciliation before unification.

The raw DWARF source layout is not copied mechanically. Original paths are
correlation evidence, and duplicate compiler/library type records are not
assumed to describe authored application ownership.
