![soCOM logo](img/recom-logo.png)

# soCOM

soCOM is an evidence-driven reconstruction of PlayStation 2 executable
SCUS-972.05 and its GameZ engine code. The goal is maintainable C/C++ that
reproduces the original Metrowerks/R5900 program—not merely source that builds
on a modern host.

The workspace is self-contained except for the live semantic project:

- immutable reference ELF: `support/socom.elf`;
- canonical live semantics: external Ghidra project `soCOM`, program
  `/socom.elf`;
- pinned compiler: `compiler/mwcps2-2.4-001213`;
- workflow and state: `AGENTS.md`, `.agent`, and `tools/socom.py`;
- provisional recovered source/data: `src` and `data`.

No Ghidra project/archive is tracked. Portable semantic receipt digests and
target facts live in the tracker; disposable receipt files belong under
`build/`.

## Reference

| Property | Value |
| --- | --- |
| Product code | SCUS-972.05 |
| Build date | May 13, 2002, 09:10:36 PST |
| Target | PlayStation 2, little-endian ELF32 MIPS/R5900 |
| Entry point | `0x140010` |
| SHA-256 | `00c9cee7f75b921fda1e848d04f64881b5a0b7841300591cac91371bb23d4f8a` |
| Compiler comment | `MW MIPS C Compiler (2.4.1.01)` |
| Ghidra baseline | `12.1.4`, `r5900:LE:32:default`, compiler `default` |

The workspace census identifies 12 ELF sections, 21,894 symbol-table entries,
115,142 relocations, 289 `.mwcats` records, 116,691 DWARF 1 DIEs, 959 compile
units, 16,602 named type records, and 880 line units. Of 52 original
`Z:\dev\...` paths, 16 map exactly to the provisional source layout and 36
require deliberate correlation.

## Bootstrap and health checks

Python 3.11 or newer is required. Ghidra must have project `soCOM` open with
program `/socom.elf`; CMake is a convenience wrapper for host-side tests.

```powershell
python tools/socom.py toolchain verify --identity-only
python tools/socom.py reference verify
python tools/socom.py doctor --infrastructure-only --ghidra
python tools/socom.py ghidra preflight --strict
python tools/socom.py progress audit --strict
python tools/socom.py progress next --json
python -m pytest -q tests/tools
```

The pinned compiler reports `Version 2.4 (Engineering Build 0017)` and carries
the `2.4.1.01` internal signature. Its upstream archive contains no FLEXlm
license, so native compilation remains blocked until the user supplies a valid
one. The workspace reports that blocker and provides no bypass.

## Reconstruction workflow

The ten stages are:

1. reference census;
2. debug-metadata import;
3. Ghidra semantic reconstruction;
4. source correlation;
5. authored function order;
6. authored call contracts;
7. authored byte matching;
8. full function order;
9. linked byte matching;
10. final validation.

The immediate work begins by reconciling the global DWARF type graph and then
reconstructing Ghidra functions, types, globals, data, and xrefs before source
correlation.

DWARF work uses separate plan and apply leases: planners write deterministic
files under `build/import-plans`, while only reviewed apply items may acquire
the Ghidra writer. Later native order/call/byte stages remain explicitly
deferred until their real producers and compiler/provider prerequisites exist.

<!-- SOCOM_PROGRESS_BEGIN -->
### Generated progress snapshot

- Tracker revision: `94`
- Next work item: `socom:debug-batch:e168f5ec330b2d69ef33-apply`
- Work items: 93 total (32 ready, 0 active, 0 awaiting acceptance, 22 accepted, 39 dependency-blocked)
- Open blockers: 3
- Provisional source owners still unverified: 316

| Stage | Status |
| --- | --- |
| `reference-census` | accepted |
| `debug-metadata-import` | active |
| `ghidra-reconstruction` | pending |
| `source-correlation` | pending |
| `authored-function-order` | pending |
| `authored-call-contract` | pending |
| `authored-byte-match` | pending |
| `full-function-order` | pending |
| `linked-byte-match` | pending |
| `final-validation` | pending |
<!-- SOCOM_PROGRESS_END -->

## Documentation

- [authoritative reconstruction instructions](AGENTS.md)
- [Ghidra workflow](docs/reconstruction/GHIDRA.md)
- [reconstruction workflow](docs/reconstruction/WORKFLOW.md)
- [tracker and receipt model](docs/reconstruction/TRACKER.md)
- [DWARF import design](docs/reconstruction/DWARF_IMPORT.md)
- [Metrowerks toolchain](docs/reconstruction/TOOLCHAIN.md)
- [final ELF readiness](docs/reconstruction/FINAL_ELF.md)
- [target-native tool coverage](docs/reconstruction/TOOL_COVERAGE.md)
- [knowledge index](docs/reconstruction/KNOWLEDGE_INDEX.md)
- [complete command index](docs/reconstruction/COMMANDS.md)

Use `python tools/socom.py commands --json` for machine-readable discovery and
`python tools/socom.py docs command-index --write` to regenerate the public
command reference.
