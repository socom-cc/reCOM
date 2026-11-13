# soCOM Reconstruction Instructions

This repository reconstructs PlayStation 2 executable `support/socom.elf` as
maintainable C and C++ source. The target is SCUS-972.05, built for
little-endian R5900 with Metrowerks MIPS C/C++ tools.

These instructions are authoritative for every human or agent in this
workspace. More specific instructions may add constraints but may not weaken
the evidence, tracking, mutation, or acceptance rules below.

## Authority and immutable inputs

- `support/socom.elf` is immutable reference evidence. Its SHA-256 is
  `00c9cee7f75b921fda1e848d04f64881b5a0b7841300591cac91371bb23d4f8a`.
  `support/` is not tracked: each checkout supplies its own copy of the
  executable at `support/socom.elf`, identified by that hash (also recorded in
  `.agent/REFERENCE_ELF.json`); until it is present, commands that read it fail
  with a `reference-elf` error and the tests that need it are skipped.
- The canonical semantic workspace is the external Ghidra project `soCOM`,
  program `/socom.elf`. Always pass `program=socom.elf`; never rely on the
  active CodeBrowser program.
- The repository stores portable target facts, plans, scopes, and semantic
  receipt digests. It does not store or depend on a machine-specific Ghidra
  project, archive, or project path.
- Assembly, xrefs, relocations, DWARF, symbols, and exact-compiler probes are
  primary evidence. Current source and existing Ghidra semantics are
  provisional until they agree with that evidence.
- Do not patch the reference ELF, patch program bytes, clear flow to force a
  shape, or post-process linked bytes to manufacture a match.
- Do not edit `.agent/RECONSTRUCTION_PROGRESS.json` manually. Use
  `python tools/socom.py` for every state read and mutation.
- Do not add machine-specific absolute paths to tracked configuration.
  Original paths embedded in debug records remain quoted evidence only.
- Do not record literal account names, computer names, checkout roots, user
  profiles, or local tool-installation paths in tracked operational surfaces.
  Prefer repository-relative paths; otherwise use environment forms such as
  `%USERPROFILE%`, `%LOCALAPPDATA%`, PowerShell `$env:NAME`, or CMake
  `$env{NAME}`. This portability rule does not rewrite immutable debug,
  compiler, SDK, middleware, or target-runtime path evidence.
- Do not change git setup as part of reconstruction work.

## Canonical control surface

Begin reconstruction work with:

```powershell
python tools/socom.py doctor --infrastructure-only --ghidra
python tools/socom.py progress audit --strict
python tools/socom.py progress next --json
```

Discover the complete public interface with
`python tools/socom.py commands --json`. The generated
[command index](docs/reconstruction/COMMANDS.md) identifies state mutations
and live-Ghidra requirements. Do not invoke private modules as substitute entry
points.

Inspect the tracker, dependencies, evidence, and leases before claiming:

```powershell
python tools/socom.py progress show <id>
python tools/socom.py progress find <query>
python tools/socom.py progress work leases
python tools/socom.py progress work claim `
  --item <socom:work:...> `
  --owner <stable-worker-name> `
  --lease-minutes 60 `
  --expected-revision <revision>
python tools/socom.py progress work packet `
  --item <socom:work:...> `
  --owner <stable-worker-name>
```

Debug imports are split into file-only plan items and live Ghidra apply items.
Only apply items may own `ghidra-writer`, and each apply item depends on its
reviewed plan. Only one work item may own `ghidra-writer`. Heartbeat long work
before expiry.
Workers never self-accept. Generic `progress work handoff` and
`progress work accept` reject Ghidra-writer items; use the live receipt
commands described below.

Generated import plans, receipt scopes, reports, and receipts belong under
`build/`. They are disposable and must never become a second progress ledger.

## Reconstruction stages

1. `reference-census` — immutable ELF/debug inventory; accepted at bootstrap.
2. `debug-metadata-import` — reconcile and import DWARF 1 and symbol evidence.
3. `ghidra-reconstruction` — finish functions, types, globals, data, and xrefs.
4. `source-correlation` — map accepted artifacts to translation units/source.
5. `authored-function-order` — reproduce authored physical contribution order.
6. `authored-call-contract` — reproduce authored ABI and generated call shape.
7. `authored-byte-match` — independent monotonic authored-byte lane.
8. `full-function-order` — integrate runtime, SDK, and provider contributions.
9. `linked-byte-match` — match typed linked ranges, relocations, and padding.
10. `final-validation` — clean rebuild and complete typed ELF verification.

The tracker exposes work only when accepted dependencies permit it.
`authored-byte-match` may progress after eligible authored-order work but must
join the main chain before linked-byte acceptance.
### Functional port lane

A separate lane builds a working, non-matching ELF from `src/` with the
open-source ps2dev toolchain (GCC and ps2sdk, pinned in
[PORT_TOOLCHAIN.md](docs/reconstruction/PORT_TOOLCHAIN.md)). It exists because
no lawful Metrowerks compiler is available; it never substitutes for
exact-compiler, order, ABI, relocation, or byte evidence, and the license
blocker stays visible on the matching stages.

- `src/` stays the single game source for both lanes. Port-only code (build,
  boot glue, SDK compatibility layer, forced-include prefix) lives under
  `port/`. GCC-only spellings in `src/` go behind `#ifdef SOCOM_PORT`, only
  where one spelling cannot serve both compilers.
- Compatibility shims and offline stubs (SDK, online, voice, sound) are
  allowed only under `port/compat/`; `guard provider` keeps rejecting them in
  `src/`.
- Port edits to `src/` fix the shared source (signatures, declarations,
  bodies) and must keep the stage-4 annotation blocks and skeleton fences
  intact. They are evidence-backed in the same order as other work: assembly
  and DWARF first, then Ghidra, then guesses, which stay flagged.
- Port results are judged by building with the pinned toolchain and by
  behaviour in an emulator. Emulator paths, BIOS files, and disc data are
  user-local; never record or commit them.

An undecomposed `stage-seed` is a closed placeholder, not executable work: it
cannot be claimed, handed off, or accepted until a real stage-specific producer
and acceptance route replace it. Current deferred capabilities and blockers are
listed in `docs/reconstruction/TOOL_COVERAGE.md`.

## Reconstruction rules

### Evidence precedence

When facts conflict, use this order:

1. executed instruction semantics, boundaries, xrefs, and relocations;
2. immutable ELF symbol/debug records and exact compiler probes;
3. reanalyzed Ghidra p-code and decompilation;
4. existing source, comments, filenames, names, and guessed intent.

Ghidra p-code and decompilation are useful propagation views, not independent
proof. Record contradictions as blockers; never silently choose the convenient
side.

### Type-first and callee-first

- Recover layouts before polishing decompilation.
- Reconstruct direct callees before callers so contracts propagate upward.
- Treat recursive strongly connected components as one work group.
- Include globals, data objects, vtables, RTTI, allocation sites, and provider
  contracts in the dependency graph.
- Re-decompile affected direct callers after every material type or prototype
  change.
- Use focused reanalysis routinely. Full reanalysis is justified only after
  verified function-boundary, code/data, or reference changes.

### PS2/R5900 and Metrowerks

- Addresses and pointers are 32-bit; the target is little-endian ELF32 MIPS.
- Confirm scalar widths, `char` signedness, alignment, packing, enum width,
  bitfields, structure returns, `this`, GPR/FPR use, and 64/128-bit values
  against the exact compiler.
- Account for branch/load delay behavior, tail calls, `$gp` addressing, and
  paired `R_MIPS_HI16`/`R_MIPS_LO16` meaning.
- Preserve mangled aliases as reference evidence. Add readable names only when
  lossless and collision-safe.
- Classify compiler runtime, standard library, PS2 SDK, and middleware as
  providers. Classification never waives ABI, order, relocation, or bytes.

## Ghidra workflow

The supported baseline is Ghidra `12.1.4`, language
`r5900:LE:32:default`, compiler specification `default`, image base
`00100000`, and entry point `00140010`. The Emotion Engine Reloaded extension
supplies the R5900 language. The live bridge is normally reached at
`http://127.0.0.1:8089` or `SOCOM_GHIDRA_URL`.

Run `python tools/socom.py ghidra preflight --strict` before reading or
writing. It verifies project/program identity, immutable source hash,
language/compiler/address size, analysis completion, entry point, absence of
Error/Warning bookmarks, and an assembly sentinel in `main`. Bootstrap counts
are enforced only while the tracker target remains `bootstrap-r5900`. The
bridge does not expose its running build version, so preflight reports the
required version and locally installed user profiles without claiming a live
server-version check. A Ghidra version re-pin requires a fresh import and
`progress rebaseline-live-ghidra` before any semantic work.

Every program-sensitive MCP or HTTP operation must include
`program=socom.elf`. Connect to project `soCOM`; never open or switch programs
as a shortcut. Ghidra overlay addresses use
`<overlay>::<hex>` with case-sensitive overlay names. Plain addresses refer to
the default physical address space.

Routine work must not:

- open, switch, import, close, or delete programs or project files;
- call `save_all_programs`, run scripts, use debugger operations, patch bytes,
  or clear flow;
- call `save_program` directly outside the governed handoff;
- treat plugin Hungarian/Pascal naming or completeness scores as project
  authority.

Pass `strict_mode=off` when an applicable bridge tool exposes plugin naming
enforcement. Preserve source spellings and aliases. Store project types in
stable categories, resolve duplicate definitions explicitly, and never accept
silent `.conflict` variants.

For read-only assembly and data checks:

```powershell
python tools/socom.py verify asm main
python tools/socom.py ghidra data-overlap
python tools/socom.py ghidra receipt
```

### Reviewed import and mutation order

Generate a deterministic plan first:

```powershell
python tools/socom.py debug graph --json
python tools/socom.py debug conflicts list --json
python tools/socom.py debug import-plan `
  --batch <socom:work:...> `
  --output build/import-plans/<batch>.json
```

The planner hands off through `progress work handoff`; an independent reviewer
accepts that file-only item. Claim the corresponding `*-apply` item before
mutating Ghidra and render its packet to obtain the exact program, scope, and
handoff contract.

Apply only a reviewed conflict-free plan, in this order:

1. forward declarations;
2. scalar aliases, pointers, arrays, and function types;
3. composites in dependency order;
4. functions and parameters;
5. globals, members, locals, and allocation types;
6. focused reanalysis and caller consistency review.

Never merge incompatible DIEs. Compatible definitions may be unified only
when qualified identity, kind, size/alignment, bases, members, bitfields, and
array extents agree.

### Semantic receipt handoff

A receipt-scope JSON file has schema:

```json
{
  "schema_version": 1,
  "functions": ["0x140d00"],
  "types": ["/project/CGame"],
  "globals": ["0x476fe8"]
}
```

Lists must be explicit, sorted by the tool, and limited to the leased scope.
The handoff command holds the tracker lock, verifies the lease and live target,
builds the receipt, saves `socom.elf` exactly once, rebuilds the receipt, and
requires the same digest:

```powershell
python tools/socom.py progress handoff-live-ghidra `
  --item <socom:work:...> `
  --owner <lease-owner> `
  --summary <summary> `
  --scope build/receipts/<item>-scope.json `
  --evidence <evidence> `
  --expected-revision <revision>
```

An independent accepter re-reads the stored scope and current live semantics;
it does not save:

```powershell
python tools/socom.py progress advance-live-ghidra `
  --item <socom:work:...> `
  --accepter <different-owner> `
  --evidence <review-evidence> `
  --expected-revision <revision>
```

Receipt hashes identify semantic evidence; they are not acceptance by
themselves. The external Ghidra project remains canonical for live semantics.

## Function workflow

For each function or recursive component:

1. confirm start/end, aliases, mangled identity, section, and authored/provider
   classification;
2. determine return, arguments, structure return, receiver, varargs, register
   classes, and stack contract;
3. reconcile direct callees and recursive peers first;
4. recover vtables/RTTI, allocations, globals, tables, and static initialization;
5. apply receiver, parameter, local, global, and allocation types;
6. inspect delay slots, saved registers, `$gp`, relocation pairs, tail calls,
   and inline-assembly constraints;
7. retain source path/line evidence and contradictions;
8. reanalyze narrowly, re-read the full function, and inspect direct callers;
9. include every changed function/type/global in the receipt scope.

Completion requires exact boundary/identity, complete call contract, reconciled
callees, typed relevant objects, no unexplained accessed raw offsets, ABI and
delay behavior consistent with the prototype, source evidence recorded, and
upward propagation reviewed.

## Type, naming, and data rules

- Prefer original qualified names and retain raw debug spelling as evidence.
- A type record retains kind, qualified name, size, alignment, bases, members,
  bitfields, arrays, vtable links, dependencies, evidence, completeness, and
  conflicts.
- Do not use `void *`, byte arrays, or placeholder integers where the used
  extent supports a stronger type.
- Unknown padding is acceptable only when its exact extent is proven and not
  accessed as a semantic field.
- Confirm each global’s size, alignment, initialization bytes, relocation
  coverage, aliases, and read/write xrefs.
- Preserve aliases; shared addresses do not make identities interchangeable.
- Original `Z:\dev\...` paths are evidence. Workspace placement is decided in
  `source-correlation`.

Source annotations use:

```text
@socom-anchor socom:anchor:<id>
@socom-artifact defines <elf-section> socom:<artifact-kind>:<identity>
@socom-artifact emits <elf-section> socom:<artifact-kind>:<identity>
```

Each physical artifact has one owner. Headers may declare; one source owner
defines/emits. Change annotations only through accepted source-correlation work.
Validate existing annotations with `audit docblocks` and `audit source-trace`.
Artifact IDs must resolve exactly in tracker evidence, and section names must
match the reference census.

## Skills and roles

Skills live under `.claude/skills/<skill>/SKILL.md`. Each file holds its
discovery frontmatter (`name`, `description`) and the complete procedure.

| Work | Skill |
| --- | --- |
| scheduling, leases, acceptance | `socom-progress-tracker` |
| bounded work selection | `socom-address-handoff` |
| DWARF graph/import planning | `socom-debug-import` |
| read-only Ghidra evidence | `socom-ghidra-workflow` |
| live Ghidra reconstruction | `socom-ghidra-reconstruction` |
| reference evidence | `socom-reference-evidence` |
| source/model recovery and scrutiny | `socom-source-model-recovery`, `socom-source-owner-scrutiny` |
| providers and ABI boundaries | `socom-provider-boundary` |
| verification and exact build | `socom-tier-verification`, `socom-metrowerks-final-build` |
| tools, audits, validation | `socom-tool-maintainer`, `socom-workspace-audit`, `socom-validation` |
| durable cross-cutting notes | `socom-durable-notes` |
| behavioural verification targets | `socom-functional-targets` |

Role definitions live in `.claude/agents/<role>.md`; each file holds its
frontmatter and complete instructions. Ghidra read-only and writer roles are
`socom-ghidra-fact-mapper` and `socom-ghidra-reconstructor`; DWARF planning is
`socom-dwarf-importer`; stage 3 group planning is `socom-recon-planner`
([RECONSTRUCTION.md](docs/reconstruction/RECONSTRUCTION.md)). Roles do not launch nested agents. The controlling
agent owns scheduling, issue routing, integration, and acceptance.

## Source matching and done criteria

Existing source is provisional. Keep logical source ownership distinct from
physical ELF storage and provider contribution. Verify order with relocations,
compile-unit paths, local/static initialization, map-like evidence, and exact
compiler behavior. Byte matching is monotonic; dependency changes must
explicitly invalidate accepted blocks.

A stage is accepted only when every work item has reproducible evidence, no
active/stale writer or blocking conflict remains, strict audits pass, the
relevant verifier passes from a disposable clean build, generated snapshots
are current, and no result depended on patching or manual tracker edits.

Final completion additionally requires a deterministic exact-compiler build,
typed coverage of every ELF region, all relocation/addend semantics accounted
for, all source/provider ownership resolved, and a clean whole-file
validation. `verify final-elf --candidate <path>` is diagnostic unless
`--acceptance` is explicitly requested; equality never substitutes for
accepted provenance. A compiler license or missing provider input stays a
visible blocker.

Tooling/process problems belong in `.agent/WORKSPACE_ISSUES.json` and are
changed only through registered `issue` commands. That ledger never replaces
reconstruction facts in the tracker.
