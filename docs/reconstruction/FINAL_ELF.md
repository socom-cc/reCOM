# Final ELF readiness

Final validation has two deliberately separate results:

- candidate comparison answers whether a supplied ELF agrees with the immutable
  reference at the requested linked or whole-file level;
- acceptance readiness answers whether the candidate was produced by accepted
  source, provider, order, ABI, relocation, and byte pipelines with complete
  typed coverage.

An equal candidate is not evidence of how it was produced. The default
comparison commands are therefore diagnostic:

```powershell
python tools/socom.py verify linked-byte --candidate <path>
python tools/socom.py verify final-elf --candidate <path>
```

They report `comparison_ok` and `acceptance_ready` independently. The final
command accepts `--acceptance`, but that mode fails closed while any stage is
undecomposed, any provider or compiler prerequisite is unresolved, or the
typed catalog is incomplete.

## Typed coverage catalog

Run:

```powershell
python tools/socom.py audit final-elf-catalog
```

The catalog partitions file offsets and loaded memory. ELF headers, program
and section tables, and nonloaded symbol/string/debug/line/relocation metadata
may be classified mechanically. Loaded code, data, providers, padding, and
zero-fill require accepted semantic spans or storage contributions. Raw
`reference-evidence` storage rows do not count as reconstruction completion.

The report lists loaded-file gaps, loaded-memory gaps, whole-file gaps,
overlaps, invalid classifications, and ambiguous provider identities. It is
expected to be incomplete during Ghidra reconstruction. A clean, explicit
incomplete report is useful evidence; silently treating gaps as padding is not.

## Current boundary

Compiler identity can be verified now, but native compilation remains blocked
by the recorded FLEXlm prerequisite. No native object/order/call/byte producer
or acceptance route is registered. Do not invent one-off manifests, modern
replacement providers, linker flags, or post-link patches. Activate those
capabilities only with exact inputs, reproducible producers, focused tests, and
stage-specific acceptance rules.
