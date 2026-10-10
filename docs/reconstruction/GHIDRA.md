# Ghidra reconstruction

The canonical semantic target is external Ghidra project `soCOM`, program
`/socom.elf`. The project directory is deliberately not tracked or named in
repository configuration. The workspace records portable program identity,
semantic receipts, and evidence only.

## Verified target

| Property | Required value |
| --- | --- |
| Ghidra | `12.1.4` |
| Program | `socom.elf` at project path `/socom.elf` |
| Executable source | this workspace’s `support/socom.elf` |
| Source SHA-256 | `00c9cee7f75b921fda1e848d04f64881b5a0b7841300591cac91371bb23d4f8a` |
| Language | `r5900:LE:32:default` |
| Compiler specification | `default` |
| Address size | 32 bits |
| Image base | `00100000` |
| Entry point | `00140010` |

The R5900 language comes from Emotion Engine Reloaded. The bridge must expose
the live Ghidra MCP schema. `SOCOM_GHIDRA_URL` may override the normal
`http://127.0.0.1:8089` endpoint.

Run:

```powershell
python tools/socom.py ghidra preflight --strict
```

The check is read-only and verifies project/program identity, source hash,
the program's recorded `Executable SHA256`, language/compiler, image/entry
facts, completed analysis, bookmark health, bootstrap counts, the required
Ghidra version against local user profiles, and the first six `main`
instructions. It always supplies `program=socom.elf`; the active UI program is
irrelevant. The recorded `Executable Location` names whichever machine imported
the project and is not compared, so a copied project passes on any checkout.

The bridge currently exposes no authoritative running-server version. The
report therefore distinguishes `required_ghidra_version` from
`local_profile_versions` and does not claim to have queried the live build.

## Addressing and evidence

Pass `program=socom.elf` on every target-sensitive bridge call. Connect only to
project `soCOM`. Do not use `open_program` or `switch_program` to compensate
for an omitted program parameter.

The default address space uses plain hexadecimal addresses. Overlay locations
must use `<overlay>::<hex>` with the case-sensitive name returned by
`get_address_spaces`. Never discard the overlay qualifier.

The bridge's bulk `list_data_items` response currently omits address-space
qualifiers. Consequently, `ghidra data-overlap` treats the monotonic prefix
before the first strict address decrease as physical memory. Equal adjacent
addresses in that prefix remain eligible physical aliases. Everything after
the first decrease is excluded as overlay data, while the overlay-space count
comes from `get_address_spaces`. Inspect a specific overlay with its qualified
address through target-sensitive Ghidra calls.

Evidence precedence is assembly/xrefs/relocations, immutable ELF/DWARF,
exact-compiler probes, then Ghidra p-code/decompilation. Current symbols,
types, prototypes, comments, decompilation, and plugin completeness results
remain provisional.

## Safe read-only operations

Use:

```powershell
python tools/socom.py verify asm main
python tools/socom.py ghidra data-overlap
python tools/socom.py ghidra receipt
python tools/socom.py ghidra fingerprint --output build/fingerprints/<name>.json
```

`ghidra fingerprint` records the whole program, not a scope: every
function's name, thunk/external flags and `get_function_by_address` details
(signature, entry, body), every defined data item, every type's path and
size (not its layout), the bookmark profile (counts by type and category, not
each bookmark), all memory blocks including overlays, and every reference
into any block, with a digest per section. Verifiers cover layouts with an
all-types receipt and bookmarks with a full `list_bookmarks` read (issue
5d602dad tracks recording both). It is evidence beside the semantic receipt, not part of
it, and catches what a scoped receipt cannot see, such as a thunk prototype
rewriting its target's signature. With `--compare <earlier.json>` it reports
the differences by section (`--diff-output` writes them in full). It uses
only GETs and the read-only `get_bulk_xrefs`; a run takes about six and a
half minutes (396 s and 399 s around batch 18), almost all of it the
reference sweep over about 111 million addresses, most of them in the 32 MiB
IOP RAM and RAM mirror blocks. The bridge serializes requests, so the sweep is
one stream of 16,000-address calls: a single block sweeps at about 460,000
addresses per second (overlay blocks about half that), larger calls and
concurrent streams were measured slower, and a full run averages less than
any one block. Run it with no other bridge traffic: a concurrent sweep has
timed out.

Read-only work may inspect functions, disassembly, decompilation, p-code,
callers/callees, xrefs, symbols, data, types, bookmarks, options, and address
spaces. It must not rename, retype, comment, reanalyze, save, open, switch,
import, close, delete, run scripts, use the debugger, patch bytes, or clear
flow.

The plugin’s Hungarian/Pascal naming and completeness rules are not project
authority. Pass `strict_mode=off` when an applicable tool exposes that
parameter.

## Mutation discipline

Mutations require an assigned tracker item, a current bounded lease, the
exclusive `ghidra-writer` resource, a reviewed conflict-free plan, and a
receipt scope.

Work type-first and callee-first:

1. create stable project categories and forward declarations;
2. apply aliases, pointers, arrays, and function types;
3. apply composites in dependency order;
4. reconstruct callees, prototypes, parameters, and returns;
5. apply globals, members, locals, allocation types, labels, and xrefs;
6. reanalyze only the affected scope and re-decompile direct callers.

Preserve source-defined names and aliases. Resolve duplicate types explicitly;
do not allow silent `.conflict` variants. Full reanalysis is reserved for
verified boundary, code/data, or reference changes.

Routine reconstruction must not open, switch, import, close, or delete
programs; call `save_all_programs`; run scripts; use debugger operations;
patch bytes; clear flow; or call `save_program` directly.

### Bridge hazards

The GhidraMCP bridge has behaviors that silently corrupt work:

- **Naming enforcement.** With the tool option *GhidraMCP → Strict Naming
  Enforcement* enabled, `create_struct` and `modify_struct_field` rewrite field
  names into Hungarian form (`m_b` becomes `pM_b`) and no request parameter
  overrides it. Disable the option and use the plugin's *Restart Server* action
  before any type work.
- **GET values are decoded twice.** The bridge URL-decodes a GET query and
  then splits it again, so a literal `=`, `&`, `%` or `+` in a value is cut
  short or rewritten: `get_function_labels` for
  `std::_RefCountedPtr<...>::operator=` looks up `...::operator`, and
  `search_functions name_pattern=operator=` searches for `operator`.
  Percent-encoding such a value twice (`%253D` on the wire) reads it exactly.
  `GhidraBridge.request` encodes once, so the two live types whose names
  contain `&` (Metrowerks `alloc_ptr<...&...>` and `compressed_pair_imp<...&...>`)
  are recorded as `unreadable-name` in receipts rather than misread. Read by
  address where possible; JSON POST bodies (every write) are unaffected.
- **Deletion clears data.** `delete_data_type` documents that it refuses
  referenced types, but it removes types applied to data and clears those data
  items. Never delete a type that existed before the current run, and confirm
  any cleanup with a full semantic receipt, not the type list.
- **Bare-name lookup.** Type endpoints resolve bare names only, ignore case,
  and truncate names at `&`; category paths are not accepted. A lookup can
  silently answer with a different type (`line_data` returns `LINE_DATA`), so
  read layouts while names are unique and compare the reported name and size.
- **Retyping drops names.** `modify_struct_field_type` clears the component
  name; `modify_struct_field` with both `new_type` and `new_name` keeps it.
- **C imports replace by name.** `import_data_types` replaces any existing
  type that the source mentions (an incomplete `struct X` reference empties
  `X`). Each import must define only the types it intends to replace.
- **Union read-back.** `get_struct_layout` refuses unions; only their size is
  readable.
- **`disassemble_bytes` is a write.** It opens a "Disassemble Bytes"
  transaction and runs `DisassembleCommand`; on already-analyzed code it
  re-triggered analysis that added eight `PARAM` references into `.bss`. Read
  instructions with `disassemble_function` or `verify asm`.
- **Analysis endpoints reanalyze everything.** `run_analysis` and `reanalyze`
  both call `reAnalyzeAll` over all initialized memory. After `.bss` was
  mapped, that typed 25 four-byte string literals (e.g. `@3845` "POS") as
  pointers and invented a 42-entry address table. Add evidence-backed
  references instead; never run analysis without a reviewed reason and a
  before/after diff of data, bookmarks, and references outside the target.

If a mistake reaches the live program, close `socom.elf` without saving and
reopen it; nothing persists until `progress handoff-live-ghidra` saves.

### Applying a reviewed type plan

`debug apply-program` translates an accepted types-only DWARF plan into a
deterministic program under `build/apply/`. It is file-only and records every
translation decision and omission. `ghidra apply-types` then requires the
item's `ghidra-writer` lease, an accepted plan item that cites the plan
SHA-256, and an apply program identical to a fresh translation:

```powershell
python tools/socom.py debug apply-program `
  --plan build/import-plans/<plan>.json `
  --output build/apply/<item>.json
python tools/socom.py ghidra apply-types `
  --program build/apply/<item>.json `
  --item <socom:work:...-apply> `
  --owner <lease-owner> `
  --scope-output build/receipts/<item>-scope.json `
  --report-output build/apply/<item>-report.json
```

Every type is created under a unique `socom_t_NNNN` name: zero-length stubs
first, then enums and function definitions, then one self-contained
`#pragma pack(1)` C import for each layout with bitfields or 128-bit members,
then the remaining layouts in by-value dependency order with explicit offsets.
Every layout and enum is read back and compared before categories are created
and types are moved and renamed; the command never deletes a type. A
Metrowerks bitfield occupies bit `location * 8 + bit_offset` of the
little-endian layout, counted from the least-significant bit
(`__ct__8CAiEventFv` writes `m_visible`, recorded at location 24 with
`bit_offset` 16, through bit 0 of byte 26). The written scope then feeds
`progress handoff-live-ghidra`.

### Applying a reviewed batch plan

Batch plans carry functions and placed globals; the types they use were
created by the type foundation. `debug batch-program` translates an accepted
batch plan (file-only, deterministic) and `ghidra apply-batch` applies it
under the batch apply item's lease with the same plan-provenance checks as
`apply-types`:

```powershell
python tools/socom.py debug batch-program `
  --plan build/import-plans/<plan>.json `
  --output build/apply/<item>.json
python tools/socom.py ghidra apply-batch `
  --program build/apply/<item>.json `
  --item <socom:debug-batch:...-apply> `
  --owner <lease-owner> `
  --scope-output build/receipts/<item>-scope.json `
  --report-output build/apply/<item>-report.json
```

`ghidra preflight-batch --program build/apply/<item>.json --output
build/preflight/<item>.json` is the read-only rehearsal: it needs no lease,
checks that the program regenerates from its plan file, runs live preflight,
and drives the same executor with every live read and pre-write check
(current names, rename clashes, type resolution, code-address refusal) while
a read-only bridge refuses any POST. It reports the exact calls an apply
would make, the skips and unchanged entries, the plan item's status, and any
write outside the receipt scope, scope entry missing from the program, or
scope type that does not exist live. An
apply should only be claimed after its preflight is clean.

- **Names.** Functions and globals take readable demangled names
  (`CGameState::~CGameState`, `operator_new[]`,
  `zdb::CTexManager::m_texmanager`) when unique; Ghidra symbols cannot hold
  whitespace, so spaces after commas are dropped and others become `_`. The
  mangled symbol stays as a secondary label. A name already used at another
  address (any `.symtab` name, any live function or defined data name, or
  one this run assigned) is not reused. File-local copies (one per compile
  unit, e.g. six `__RTTI__10CGameState` and 24 `__RTTI__3C2D` objects) take
  the readable name only when canonical: the RTTI copy that word 0 of the
  class's single `__vt__` (an `R_MIPS_32` relocation) points to. Other copies,
  and copies of names with no canonical copy (`__msl_ios_base_ninit__3std`,
  and the functions `IOPRebootHandler__FQ211CIOPManager...` and
  `find<...CModel...>`, three copies each), keep their mangled names
  (`rename_skip`).
  The bridge has no complete read-only symbol listing (`list_globals` filters
  heuristically), so a renamed label on bytes without defined data is not
  seen.
- **Prototypes.** `__stdcall` with an explicit `this`, built from DWARF
  return and parameter records; parameters DWARF omits come from the mangled
  signature, and destructors gain the hidden `short __dtor_flags`. DWARF may
  omit a parameter anywhere (`LoadTextures__10OrdersMenuFPQ23zdb6CWorldP7C2DFont`
  records only `font`), so DWARF parameters are placed as an ordered
  subsequence of the mangled signature that their pointer depth and class
  name or builtin width allow; a DWARF parameter keeps its name and type only
  where every placement agrees, other positions take the mangled type, and a
  list with no placement is a recorded skip. Executed code outranks DWARF: a
  function DWARF declares `void` whose direct caller reads `v0` or `f0` right
  after the call (before any write of it or control transfer) is a recorded
  contradiction skip, writing neither side (`sceVu0ClipBBox` returns its clip
  mask to `TestFOV`). Likewise a prototype is skipped when the function's
  entry block (up to its first branch and delay slot) reads an argument
  register, `a0`-`t3` or `f12`-`f19`, before writing it and the prototype does
  not declare that register: Metrowerks' `@8@72@__dt__...` this-adjusting
  thunks read `a0` though DWARF records them as `void` with no parameters.
  A by-value class, struct or union return or parameter is
  a recorded skip: Metrowerks passes a class result as a hidden pointer in
  `a0` ahead of `this` at every size and need not return it in `v0`
  (`CAppCamera::GetThirdPersonCamPos` returns `CPnt3D`), while Ghidra's r5900
  `__stdcall` hides only results over 8 bytes, returns that pointer in `v0`,
  and reads back an extra `__return_storage_ptr__` parameter. Enums are
  scalars and unaffected. A method
  has a receiver only when DWARF records `this` or its address is in its
  class's vtable (`__vt__10CGameState` holds the seven parameterless
  `CGameState` virtuals). Methods without that evidence keep their signature.
- **Globals.** Placed objects take their DWARF type over auto-analysis data.
  The per-unit rows of one global fold into one entry and must agree on the
  type. `apply_data_type` with `clear_existing` clears from the address to
  the larger of the new type and the existing code unit, so the program
  refuses a global inside a function or of function type, the executor
  refuses an address `audit_global` reports as code, and a global that
  already has the type and length is left alone (`unchanged`). A global
  declared in several compile units recurs in later batches; one an earlier
  batch already renamed keeps that name (`unchanged`) instead of failing the
  live-name check. An address holding only zero-size `NOTYPE` labels (no
  `OBJECT` symbol), such as `extern void *_gp` at 0x47cbf0 with `EER27`, is a
  linker symbol rather than a data object and is a recorded skip. Arrays are
  spelled `element[count]` (the bridge builds one level, only for a count
  above 0): an outermost extent DWARF leaves open (`aiDeployList`,
  `EQUIP_ITEM[0..-1]`) is completed from the `.symtab` size
  (`EQUIP_ITEM[11]`), every array carries its byte length for read-back, a
  global whose DWARF extent differs from its `.symtab` size is left untyped,
  and a multi-dimensional array applies only if a type of exactly that name
  exists. Only pointer and reference modifiers are spelled (`*`); `const` and
  `volatile` are recorded skips.
- **Thunks.** A function whose whole body is `j target` or `b target` with a
  `nop` delay slot is a Ghidra thunk, and a thunk shares its target's
  signature: setting one changes the target. The program therefore records a
  thunk's prototype as a skip (it is still renamed). Batch 001 predates this
  rule and set `COurGame::StopPlay`/`StartPlay` (0x140500/0x140510), which
  gave `StopPlay__5CGameFv`/`StartPlay__5CGameFv` (no DWARF) `COurGame * this`;
  see "Governed repairs".
- **Recorded skips.** Type names with commas or `&` (STL), names not unique
  ignoring case, member-less anonymous RTTI/vtable records, and absent
  objects are left as they are and listed in the report. The comma check
  covers every prototype spelling, including a receiver taken from a vtable
  (`basic_streambuf<wchar_t, std::char_traits<wchar_t>> *`), and the
  executor refuses, before any write, a program that still spells one: the
  bridge splits a prototype's parameters at commas.
- **Cross-batch type conflicts.** A global declared in several compile units
  recurs in later batches, and units can describe it differently
  (`_impure_ptr` is `_reent@1aa0a63ac4 *`, 752 bytes, in most units but
  `_reent@b152c1df75 *`, 748 bytes, in MSL's iostream units). When a global
  is in the stored receipt scope of an earlier accepted batch apply and its
  live type is defined, differs, and is not one Ghidra's analysis assigns
  (`pointer`, `dword`, `string`, ...), the new type is a recorded conflict
  skip; accepted state is never overwritten by whichever batch runs last.
  The zero-fill map's scope (every `.bss` object) and repairs do not count:
  they type nothing.

Every applied name, prototype (`Signature:` line), and global type and length
is read back before the report is written.

### Mapping the zero-fill load image

The ELF has no `.bss` section header; `PT_LOAD` 0 covers 0x100000-0x5e7eff in
memory but only 0x100000-0x4755ff in the file, and the import mapped only the
file-backed part. Objects such as `theGame` (0x476f60) therefore had no memory,
no data, and no code references. Under the `socom:work:ghidra-zero-fill-memory`
lease:

```powershell
python tools/socom.py ghidra map-zero-fill `
  --item socom:work:ghidra-zero-fill-memory `
  --owner <lease-owner> `
  --scope-output build/receipts/<item>-scope.json `
  --report-output build/apply/<item>-report.json
```

The command derives each zero-fill range from the `PT_LOAD` headers, refuses
any overlap with an existing block, and creates an uninitialized block named
after the segment's block (`main.bss`) with the segment's permissions. It runs
no analyzer. It adds only the references the relocations prove:

- `R_MIPS_LO16` pairs with the `lui` whose write of the LO16's base register
  reaches the site (`tools/_socom/mips_flow.py`). Metrowerks interleaves the
  HI16s of one section symbol across functions and lists some after their
  LO16, so relocation order is not pairing: `lw v1,-0x5d98(s4)` at 0x411dac
  reads `s4 = lui 0x59` (0x411cfc), target 0x58a268, although the latest
  same-symbol HI16 holds 0x5b. The intra-function graph models delay slots,
  annulled branch-likely slots, always-taken `b`, call clobbers after the
  call's delay slot, dead padding after unconditional transfers, jump-table
  targets, and `addu`/`move` index arithmetic; unsized startup code uses the
  span between code labels. An unresolved LO16 whose symbol lies in the zero
  fill fails the step. The ten unresolved sites relocate `.data`/`.rodata`
  symbols only: eight read a `%hi` register reloaded from a stack spill
  (`_vf*printf_r`), and two sit where two jump tables' targets merge
  (`CSealCtrlAi::SetAiMode`, every candidate `lui 0x45`).
- `R_MIPS_GPREL16` is relative to the `.reginfo` `$gp` (0x47cbf0).
- `R_MIPS_32` words hold the address.

That is 16,333 references (10,542 LO16, 5,727 GPREL16, 64 words), typed READ,
WRITE, or DATA by the referencing opcode. When the block already exists as
this step created it, the command reconciles instead: it reads every
reference into the zero fill (read-only `get_bulk_xrefs` over every byte of
the block, failing unless every address is answered), removes those the
relocations do not prove, that carry another type, or that duplicate a proven
pair, and adds missing ones. In both modes it then sweeps again and fails
unless the live references into the zero fill equal the relocation-proven set
exactly. It also fails if the function index, the data outside the new block,
or the bookmarks change. Its receipt scope lists every `.symtab`
object in the mapped range, so the handoff receipt binds their names and
reference counts.

### Governed repairs

When an accepted apply changed live state outside its scope and no later
batch will correct it, a `ghidra-repair` item (added by a tracker migration)
restores it under its own writer lease:

```powershell
python tools/socom.py ghidra repair-signatures `
  --item <socom:work:ghidra-repair-...> `
  --owner <lease-owner> `
  --scope-output build/receipts/<item>-scope.json `
  --report-output build/apply/<item>-report.json
```

A repair item enters the tracker through the thunk migration or through
`progress add-repair --item <id> --expected-revision <n>`, which requires every
apply it corrects to be accepted. Label repairs run with
`ghidra repair-labels` (same arguments): each readable label is removed with
`delete_label` naming it exactly (without a name the endpoint deletes every
label at the address), so the mangled label becomes primary again; the
command requires `deleted_names` to be exactly that label and reads the
primary name and data type back.

The spec in `tools/_socom/repairs.py` names each target, the exact wrong state
the live program must still show (any other state is refused before a write),
and the state to restore. The thunk repair restores `StopPlay__5CGameFv` and
`StartPlay__5CGameFv` to `undefined __stdcall NAME(void)`: batch 001's
before-snapshot shows the import-time `undefined NAME(void)` with an unknown
calling convention, but `set_function_prototype` accepts only `__stdcall` and
`__thiscall` (it refused `unknown` after applying the signature), so the
repair keeps the compiler spec's default convention. It reads back both
targets and both thunks and scopes all four functions for the handoff
receipt.

### Restoring the accepted state

A saved defect is repaired from a fresh baseline import, not by hand: rename
the damaged `/socom.elf`, import `support/socom.elf` as `/socom.elf` with the
`r5900:LE:32:default` language and default analysis, then, under any writer
lease:

```powershell
python tools/socom.py ghidra restore-accepted `
  --item <leased writer item> `
  --owner <lease-owner> `
  --report-output build/apply/<item>-restore.json
```

The command requires the unscoped receipt to equal the tracker's recorded
baseline import, replays each accepted type-foundation apply from its
accepted plan, and requires each replay to reproduce that item's accepted
receipt exactly. It does not save; the leased item's handoff does. It has no
replay route yet for the zero-fill memory map, batch applies, or repairs
(issue `014521cb`), and batch 001's accepted program no longer regenerates
once the thunk guard skips its two thunk prototypes, so a full replay past
the foundation is not yet possible.

## Ghidra version re-pin

The pinned version lives in `tools/_socom/constants.py`. To move to another
Ghidra release before semantic work begins:

1. import `support/socom.elf` into a fresh `soCOM` project with the new
   release and default analysis;
2. update the pinned version and bootstrap counts with tests and documentation;
3. preview, then record, the new baseline:

```powershell
python tools/socom.py progress rebaseline-live-ghidra `
  --recorder <name> `
  --evidence <evidence> `
  --expected-revision <revision> `
  --dry-run
```

The command runs the strict preflight, computes a non-saving receipt, and
refuses unless the target is still `bootstrap-r5900`, no `ghidra-writer` work
is leased or accepted, and the function and type index digests equal the
previous baseline. It appends a history entry with the previous version and
receipt, per-index comparisons, and count deltas, then sets the baseline and
current receipt. It never saves the program.

## Receipt scope and handoff

A scope file is a schema-versioned JSON object:

```json
{
  "schema_version": 1,
  "functions": ["0x140d00"],
  "types": ["/project/CGame"],
  "globals": ["0x476fe8"]
}
```

Functions and globals are addresses; types must resolve exactly once by name
or path. Scope files and generated receipts belong below `build/`.

`progress handoff-live-ghidra` is the only routine save path. While holding the
tracker lock it:

1. verifies the current revision, owned lease, writer resource, and program;
2. validates every scoped function, type, and global;
3. computes a portable semantic receipt;
4. calls `save_program` for `socom.elf` exactly once;
5. recomputes the receipt and requires the same SHA-256;
6. moves the item to `awaiting_acceptance`.

The receipt excludes endpoint URL, host project path, and timestamps. It pins
portable target facts, analysis and bookmark state, an assembly sentinel,
full function/type/data index digests, and the scoped semantic facts. A scoped
type also records its component layout or enum values when its bare name is
unique ignoring case and the bridge reports back that exact name and size.
Otherwise its `detail` says why: `ambiguous-name`, `mismatched-readback`,
`unreadable-name` (the bridge truncates the name), or `no-component-readback`
(unions and function definitions, whose members the bridge cannot read).

`progress advance-live-ghidra` performs independent acceptance. It recomputes
the stored scope without saving and fails unless the live receipt equals the
handoff receipt. The handoff owner cannot accept the item.

## Baseline facts

At the fresh Ghidra 12.1.4 R5900 import, preflight reports 9,715 functions,
24,194 symbols, 210 data types, and 27 memory blocks. Analysis is complete.
There are 716 Analysis bookmarks: 713 Address Table and three Non-Returning
Function bookmarks, with no Error or Warning bookmarks.

The original 12.1.2 import reported 26 memory blocks. Its function and type
index digests are identical to the 12.1.4 import; its data index has the same
51,523 rows but a different digest. That data difference is recorded in the
rebaseline history entry and is not attributed to specific rows, because no
12.1.2 data listing was retained.

These exact counts are bootstrap checks, not permanent reconstruction goals.
After accepted semantic work, identity, analysis health, entry, source hash,
and assembly sentinel stay mandatory while evolving counts are recorded in
semantic receipt history.
