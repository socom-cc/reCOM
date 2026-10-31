---
name: socom-provider-boundary
description: Classify soCOM compiler-runtime, C/C++ library, PlayStation 2 SDK, and middleware provider boundaries. Use when a function, data object, relocation target, ABI contract, archive member, or final-image contribution may be provider-owned.
---

# soCOM provider boundary

Use symbol/debug paths, mangled identity, assembly, relocations, fingerprints,
imports/exports, exact archives, and caller contracts. Distinguish authored
overrides from provider defaults and functions from their physical data or
storage contributions.

A stage 4 provider plan has one owner row per archive member (its library
plus its GNU object address or object name) and no source body; see
[`SOURCE_CORRELATION.md`](../../../docs/reconstruction/SOURCE_CORRELATION.md).

Provider classification never waives ABI, order, relocation, byte, or final
coverage checks. Register missing exact libraries or unresolved versions as
blockers; never replace them with nearby or modern implementations.
