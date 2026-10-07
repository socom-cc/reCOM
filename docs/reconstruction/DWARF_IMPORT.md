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

The schema-version 4 plan declares `mutation_performed: false`, pins portable
Ghidra project/program/language facts, and emits a receipt scope for selected
functions and types. Types-only batches carry no function addresses in that
scope. It emits forward declarations before full types and reports distinct
structures that share one qualified identity, or members that contradict
their owner's template arguments, as blocking conflicts. Every member,
parameter, local, variable, and type reference is a descriptor of DWARF
modifiers (`pointer_to`, `reference_to`, `const`, `volatile`) plus either a
DIE offset or a fundamental type code; array rows decode their dimensions and
element type. A reviewed
Ghidra writer applies the plan; the Python planner never opens or saves the
program.

Tracker schema 3 represents these as two different leases. A
`debug-import-plan-*` item is owned by the DWARF importer and can write only its
deterministic file under `build/import-plans`. After independent acceptance,
the matching `debug-import-apply-*` item becomes eligible; it is owned by the
Ghidra reconstructor and alone may acquire `ghidra-writer`. Batch plan items do
not become eligible until the accepted foundation plan has been applied.

Type identities retain their compile-unit offset/path, parent DIE, scope path,
raw name, and qualified name. Anonymous/synthetic `@...` records are keyed by
compile unit, parent, and DIE offset; identical spellings from unrelated units
are therefore not reported as false global conflicts.

## Evidence-backed type identity

Metrowerks DWARF 1 drops namespaces, enclosing classes, and template
arguments, and repeats header types in every compile unit.
`tools/_socom/type_identity.py` therefore:

1. groups every type DIE into a structural class by partition refinement over
   kind, size, members, offsets, bitfields, enum elements, array dimensions,
   and the classes of by-value member types. Pointees are compared by name, so
   a pointer to a forward declaration equals a pointer to the complete type.
   Size-0, member-less class records are forward declarations, not layouts;
2. names DIEs from binary evidence, strongest first:
   - `method`: subroutine DIEs carry their mangled name (attribute `0x2000`);
     the `this` parameter and aligned parameters link type DIEs to
     demangled qualified names (`tools/_socom/mwdemangle.py`). Functions that
     DWARF shows without `this` are never treated as receivers;
   - `call-site`: mangled methods in `main` that pass `this + k`, optionally
     through loaded pointer members, as `a0` to a mangled callee name the DIE
     stored at that offset in every compile-unit copy of the caller's class.
     The R5900 tracer honors delay slots, annulled branch-likely slots,
     three-operand `mult`, linking branches, and block-ending jumps;
   - `symbol`: an unshared bare spelling with exactly one qualified candidate
     among demangled `.symtab` names, template arguments included;
   - `spelling`: the only structure with a bare name that no symbol qualifies;
3. decides how far a name reaches. A spelling is *shared* when symbols qualify
   it more than one way or use it as a template base. Layout-identical
   structures can then be different C++ types (every MSL `deque<T>` stores
   `void**`), so names attach only to the DIEs that evidence reaches, and
   symbol inference never names them. Unshared spellings name their whole
   structural class;
4. gives every unnamed DIE a deterministic `provisional` name
   `<raw>@<class-hash>` under `/project/unresolved/`. Ambiguous call-site
   receivers and disagreeing evidence leave DIEs unnamed and are recorded as
   contradictions. Resolution fails closed if it does not converge;
5. blocks when a by-value member or base contradicts its owner's template
   arguments.

The plan's `identities` table holds one entry per structural class and name,
with its resolution and evidence.
Every type row carries `structural_class`, `identity_resolution`, and
`ghidra_path`; resolved names map to `/project/<scope>/<name>` categories.
Provisional identities are non-blocking and are renamed only by later
evidence.

The raw DWARF source layout is not copied mechanically. Original paths are
correlation evidence, and duplicate compiler/library type records are not
assumed to describe authored application ownership.
