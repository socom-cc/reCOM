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
| Executable source | `support/socom.elf` (untracked; each workspace supplies its own copy) |
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
only GETs and the read-only `get_bulk_xrefs`. Most of a run is the reference
sweep over about 111 million addresses, 98 million of them in the 32 MiB IOP
RAM and two RAM mirror blocks that hold about 230 references between them.
The bridge has no unfiltered reference iterator: `list_data_items_by_xrefs`
and `list_globals` walk `getReferenceDestinationIterator` but drop every hit,
since `getPrimarySymbol` returns a dynamic symbol for any referenced address,
and `analyze_data_region` scans server-side at the same ~2 µs per address. So
the sweep asks for every address in 16,000-address calls, and its floor is
the bridge's per-address `getReferencesTo` work. The GUI bridge serves on a
pool of three HTTP threads, and neither `get_bulk_xrefs` nor
`get_function_by_address` runs on the Swing thread. By default
(`--sweep-mode concurrent`) the command keeps three of the same calls in
flight, each on its own keep-alive connection, and consumes the answers in
request order. A run takes about 176 s instead of about 350 s. The 9,715
`get_function_by_address` reads take about 3 s instead of about 80 s, which
was mostly a new TCP connection per call. Each 32 MiB block takes about 46 s
instead of about 90 s; Ghidra's program lock serializes most of the
per-address work. Keep-alive matters on Windows: at the concurrent rate, a
connection per call wraps the 16,384 client ports inside the bridge's
TIME_WAIT, and connects time out (WinError 10060). `--sweep-mode legacy`
sends the calls one at a time through the ordinary client, as before. Both
modes send identical requests and write byte-identical output.
`check-recon-apply` and `check-names-repair` always use the default. Avoid
running two fingerprints at once, because they share the three bridge
threads.

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
patch bytes; clear flow; or call `save_program` directly. There are exactly
two script exceptions, each a pinned, reviewed file run only by its own
command: the one-time boundary repair and the read-only type archive export,
both described below.

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
- **Data types resolve through an alias table.** `apply_data_type` (and every
  endpoint using `ServiceUtils.resolveDataType`) checks a well-known-type
  table before Ghidra's builtins, mapping `int16`/`uint16` to 2-byte
  `short`/`ushort` although Ghidra's builtins of those names are 16 bytes
  (DWARF 0xA510, `u_long128`). Batch 35 typed `g_buffer` (`uint16[512]`,
  8192 bytes) as `ushort[512]`; the apply's read-back caught it before any
  save. `get_type_size` and `set_function_prototype` resolve `/uint16`
  correctly (`GetVuMtxSet` reads back `uint16 *`), so batch programs skip
  global types whose base name (ignoring `*` and `[n]`) is in that table,
  matched ignoring case, unless it is the builtin the program means (`int`,
  `uint`, `short`, `ushort`, `longlong`, `char`, `uchar`, `float`, `double`,
  `void`); the executor refuses any program that still has one.
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
  ignoring case, member-less anonymous RTTI/vtable records, arrays whose
  DWARF element type is `void` (Metrowerks' spelling for elements DWARF 1
  cannot describe: `c_arrStatFuncs` is `void[0..5]` over 72 bytes of
  12-byte member-function pointers), and absent
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

### One-time boundary repair (the first script exception)

Ghidra split ten `.symtab` functions that begin `b L; nop`, where L is more
than 8 bytes past the start. `CreateThunkFunctionCmd` treats such a branch as
a thunk, because its local-branch test allows only jumps of 8 bytes or less.
In each case the `.symtab` start is a thunk whose body is `[start, L)`, and
its target is a default-named `FUN_<L>` that holds `[L, end)`. The gap holds
only code. The ten starts are:

`0x193cd0`, `0x1972d0`, `0x1a2750`, `0x1a2ad0`, `0x1f01f0`, `0x2241e0`,
`0x229fc0`, `0x231330`, `0x2fb5b0` and `0x39e3f0`.

GhidraMCP 6.0.0 has no endpoint that sets a function body or clears a thunk.
Running `delete_function` and then `create_function` rebuilds the split.

On 2026-10-30 the user allowed one reviewed Ghidra script for exactly these
ten functions, under `socom:work:ghidra-repair-split-function-boundaries`; a
patched plugin was rejected. The no-scripts rule in AGENTS.md still covers
everything else, apart from the type archive export below. No other command
or worker may call `run_script_inline` or `run_ghidra_script`, and this
command runs nothing but the pinned file.

```powershell
python tools/socom.py ghidra repair-boundaries `
  --item socom:work:ghidra-repair-split-function-boundaries `
  --owner <lease-owner> `
  --scope-output build/receipts/<item>-scope.json `
  --report-output build/apply/<item>-report.json `
  --dry-run
```

**Before it runs.** The spec in `tools/_socom/repairs.py` lists, for each
function:

- the start;
- the `.symtab` symbol, size and end;
- the live name;
- the exact wrong state: the thunk body and signature, and `FUN_<L>` with its
  body and signature;
- the target state: one non-thunk function whose body is `[start, end)`.

The command then checks, in order:

1. The repair item's writer lease and the live preflight.
2. The spec against `support/socom.elf`.
3. The SHA-256 of `tools/_socom/ghidra_scripts/RepairSplitBoundaries.java`.
   It reads CRLF line ends as LF, so the hash covers the exact text it sends.
   It refuses any other hash.
4. The wrong state, read-only, using `list_functions_enhanced`,
   `get_function_count`, and `get_function_by_address` at the start, at L,
   and at every 4-byte address of the extent.

`--dry-run` stops there. It prints the script, its hash and its arguments,
and sends nothing.

**The run.** The command makes exactly one write call:
`run_script_inline` with `code` set to the pinned Java text and `args` set to
one `S:L:E` triple per function. These facts come from the plugin jar:

- The endpoint accepts Java only.
- It is gated by `GHIDRA_MCP_ALLOW_SCRIPTS=1` in the Ghidra process
  environment. Start Ghidra with it for this one run, and restart Ghidra
  without it afterwards.
- It writes `~/ghidra_scripts/RepairSplitBoundaries.java`. It deletes the file
  on success; on failure it leaves a `.java_failed` note there.
- It runs the script on the Swing thread against `program=socom.elf`, inside
  the script's single transaction.

The script refuses before any change unless, for every triple:

- S is a non-default-named thunk of the default-named `FUN_<L>`;
- the bodies are exactly `[S, L)` and `[L, E)`;
- only S is a thunk of L;
- every 4-byte address is an instruction inside S or L;
- L has no tags, call fixup, no-return flag, or stored symbol other than its
  own.

It then works inside one nested transaction. It clears the thunk at S first,
because removing L would also delete any thunk of L. It then removes L and
sets the body of S to `[S, E)`. Before committing, it checks the result:

- every entry is a non-thunk;
- every body is exact;
- no L remains;
- every 4-byte address resolves to S;
- the function count is ten lower.

Any difference or exception aborts the nested transaction, and Ghidra then
rolls back the whole script transaction. The script:

- clears no flow, writes no bytes and disassembles nothing;
- starts no analysis;
- prints one `SOCOM_REPAIR_BOUNDARIES_RESULT {json}` line.

The analysis-worker mode would suppress auto-analysis, but it cannot run on
the Swing thread. Auto-analysis therefore reacts to the body change as it
does to any edit, and the command waits until `analysis_status` is idle.

**Read-back.** The command reads every function back:

- the same name, now a non-thunk;
- `Body:` exactly the `.symtab` extent;
- every 4-byte address resolving to the start;
- no function starting inside any extent;
- ten fewer functions;
- a clean live preflight.

It writes a receipt scope that lists the ten starts. The removed `FUN_`
pieces cannot be scoped, so they are recorded in the report.

**Lost signatures.** Removing a `FUN_` piece drops its signature. The command
does not restore any prototype; it records every lost signature in the report
(`lost_signatures`, `removed_functions`). Group 076's accepted prototype for
`0x39e3f0` was stored on `FUN_0039e3fc`. After acceptance, a recon repair
applies that prototype again, along with the proven contracts in the plan
notes of groups 020, 021, 029, 036, 037, 038 and 054.

**Failure.** The report says whether the script may have run. If it did not,
the live program is unchanged. If it may have, close `socom.elf` without
saving and reopen it before retrying.

Hand off with `progress handoff-live-ghidra`; someone else accepts it.

### Type archive export (the second script exception)

The release program and later game versions are to reuse the prototype's
data types. GhidraMCP 6.0.0 has no endpoint that writes a data type archive,
so on 2026-11-25 the user allowed a second reviewed Ghidra script,
`tools/_socom/ghidra_scripts/ExportTypeArchive.java`. It only reads the
program: it copies every `socom.elf` data type into a new `.gdt` file
archive. Every other script stays forbidden; no other command or worker may
call `run_script_inline` or `run_ghidra_script`, and this command runs
nothing but the pinned file. Its SHA-256 (CRLF read as LF) is
`488ec9c2efd48ba32f93312d28e903fd7bbce0620335367c96817d3f33b9c6d8`, pinned
in `tools/_socom/type_archive.py`; a changed script needs a new review and
a new pin.

```powershell
python tools/socom.py ghidra type-archive `
  --output support/socom-types.gdt `
  --dry-run
```

The `.gdt` is never tracked: the output must be a `.gdt` under `support/`
(the default, `support/socom-types.gdt`) or `build/`, both git-ignored. An
existing archive is refused unless `--replace` is given, and so is one that
Ghidra holds open (a `<name>.*lock` file beside it). The command needs no
work item and no lease, because it writes no program state, but it refuses
while any item holds `ghidra-writer`.

**Before it runs.** The command checks the live preflight (project `soCOM`,
program `/socom.elf`, source SHA-256, language and compiler), the script's
pinned hash and the output path, and reads a type snapshot: every
`list_data_types` row (name, category, size, path), the category names, and
no `.conflict` name. `--dry-run` stops there; it prints the script and its
hash and sends nothing.

**The run.** One `run_script_inline` call sends the pinned text with two
arguments: the absolute output path as hex of its UTF-8 bytes (the bridge
splits arguments at whitespace) and `create` or `replace`. As for the
boundary repair, start Ghidra with `GHIDRA_MCP_ALLOW_SCRIPTS=1` for this run
only and restart it without it afterwards; the bridge writes
`~/ghidra_scripts/ExportTypeArchive.java` and runs it on the Swing thread
against `program=socom.elf`. The script:

- refuses unless the program is `/socom.elf` with `r5900:LE:32:default` and
  compiler spec `default`, and the output is a `.gdt` in an existing
  directory that is absent (or, with `replace`, a plain unlocked file);
- creates the archive under its final name in a new staging directory next
  to the output with `FileDataTypeManager.createFileArchive(file, language,
  compiler spec)`, so the archive has the program's architecture and data
  organization;
- in the archive's own transaction creates every program category and
  resolves every program type with `DEFAULT_HANDLER`, so a clash shows as a
  `.conflict` name instead of a silent replacement;
- saves and closes the archive, reopens it read-only, and requires the same
  category and type paths, an equivalent type of the same length at every
  path, the same count per kind (structure, union, enum, typedef, function
  definition, pointer, array, built-in, other), the program's language,
  compiler spec and data organization, and no archive warning;
- only then renames the file onto the output path; on any problem it deletes
  the staging directory, so nothing half-written is left;
- prints one `SOCOM_TYPE_ARCHIVE_RESULT {json}` line with both sets of
  counts, the conflict, missing, extra and non-equivalent counts (all must be
  0), the archive's universal ID and the program state before and after. It
  names the archive file but never a directory.

The copy cannot change the program. A program type's source archive is the
program itself, and `resolve` does not carry a program's identity into
another manager: the archive gets an unassociated copy with a new universal
ID, and every write goes to the archive. (A program type that is already
linked to another file or project archive keeps that link and its ID in the
new `.gdt`; `socom.elf` has one such source, Ghidra's own `generic_clib`.)
The script never calls
`associateDataTypeWithArchive`, never opens the archive in the tool, renames
nothing and saves nothing. As a runtime proof it records the program's
database modification count, modification number, changed flag, type count
and source archives before and after; any difference fails the export and
aborts a nested program transaction, so Ghidra rolls the script's
transaction back. An unchanged program's empty script transaction commits
nothing and leaves no undo entry.

**Read-back.** The command requires the result to match (counts equal to each
other and to the live `list_data_types` count, every problem count 0, the
architecture, an unchanged program state), reads the type snapshot again and
requires it equal, requires the file, hashes it, and runs the live preflight
again. A `support/` export then writes `.agent/TYPE_ARCHIVE.json`: the
archive's file name (no directory), SHA-256, size, universal ID, counts per
kind and categories, the program's identity and source SHA-256, the script
path and hash, the Ghidra pin, the decision date and the export date. A
`build/` export is a disposable trial and writes only its report under
`build/type-archive/`. Each export gets a new universal ID, so the archive's
hash changes with every export.

**Failure.** The report says whether the script may have run and whether the
archive may have been written. The script only reads the program; if it may
have run, confirm the program is unchanged (for example with
`ghidra fingerprint`) and delete an unwanted archive before retrying.

**First export (2026-11-26, the record's UTC date).** Run after an independent review of the script
against the Ghidra 12.1.4 sources: 1,733 types in 55 categories, equal counts
per kind in program and archive, no conflict, missing, extra or
non-equivalent type, the program's modification count unchanged. A semantic
receipt taken afterwards with the stage baseline's scope has the baseline's
digest (`f8912398...`). The record is `.agent/TYPE_ARCHIVE.json`.

**Known limits** (from the review; none affects a first export):

- A later `--replace` writes an archive with a new universal ID and new type
  IDs. A program that has been linked to the earlier `.gdt` loses that link,
  so do not replace an archive another program already uses until the export
  can keep the IDs.
- Settings on structure members are not carried: only a program's type
  manager stores them, and the equivalence check does not compare them.
- The lock test uses the plain file name. Ghidra mangles capitals in its lock
  file names, and an archive open read-only leaves no lock file, so keep the
  lower-case default name and close the archive in Ghidra before `--replace`.
- The before and after snapshot the command reads through the bridge sees
  names, categories, sizes and paths, not member layouts; the script's own
  modification-count check covers those.

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
