---
name: socom-metrowerks-final-build
description: Diagnose soCOM Metrowerks/R5900 build readiness and compare candidate ELFs. Use for compiler identity, license or provider blockers, typed ELF coverage, deterministic candidate comparison, and eventual final acceptance prerequisites.
---

# soCOM Metrowerks final build

Read [`TOOLCHAIN.md`](../../../docs/reconstruction/TOOLCHAIN.md) and
[`FINAL_ELF.md`](../../../docs/reconstruction/FINAL_ELF.md). Verify tool
identity before any compile probe. The current workspace has no accepted
native object/order/byte producer, so do not invent a manifest, flags,
providers, or acceptance path. Candidate ELF comparison is diagnostic until
the tool-coverage registry marks those producers active.

The current compiler requires a lawful FLEXlm license. Report
`blocked_by_license` without bypassing it. Final validation also requires
complete typed coverage of ELF headers, segments, sections, zero-fill,
symbols/strings, relocations, `.mwcats`, debug/line data, padding, and provider
contributions before a fresh build and whole-file comparison. Use
`audit final-elf-catalog` to expose current gaps and `verify final-elf
--candidate <path>` for diagnostic comparison. Add `--acceptance` only after
all readiness errors are closed.
