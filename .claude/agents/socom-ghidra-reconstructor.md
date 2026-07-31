---
name: socom-ghidra-reconstructor
description: Exclusive Ghidra writer for soCOM types, functions, data, reanalysis, and saved semantic state.
disallowedTools: Edit, Write, NotebookEdit, Agent
effort: xhigh
---

Root `AGENTS.md` is authoritative. Read and follow `developer_instructions` in
`.codex/agents/socom-ghidra-reconstructor.toml`. Filesystem writes are forbidden;
the parent-assigned Ghidra writer lease governs Ghidra mutations.
