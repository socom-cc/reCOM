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
```

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
