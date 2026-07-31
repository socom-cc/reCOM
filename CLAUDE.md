@AGENTS.md

## Claude Code harness notes

The imported root instructions are authoritative. This file only maps them
onto Claude Code.

Project skills are discovered through `.claude/skills/socom-*/SKILL.md`.
Mirrors retain canonical discovery frontmatter and point to
`.codex/skills/<skill>/SKILL.md`.

Claude agent types use hyphens; canonical role names use underscores:

| Canonical role | Claude agent |
| --- | --- |
| `socom_ghidra_fact_mapper` | `socom-ghidra-fact-mapper` |
| `socom_ghidra_reconstructor` | `socom-ghidra-reconstructor` |
| `socom_dwarf_importer` | `socom-dwarf-importer` |
| `socom_reference_mapper` | `socom-reference-mapper` |
| `socom_provider_data_classifier` | `socom-provider-data-classifier` |
| `socom_scaffold_auditor` | `socom-scaffold-auditor` |
| `socom_source_owner_mapper` | `socom-source-owner-mapper` |
| `socom_source_owner_scrutinizer` | `socom-source-owner-scrutinizer` |
| `socom_source_worker` | `socom-source-worker` |
| `socom_tool_maintainer` | `socom-tool-maintainer` |
| `socom_verifier` | `socom-verifier` |
| `socom_workspace_librarian` | `socom-workspace-librarian` |

Each stub defers to its paired `.codex/agents/*.toml` instructions. Roles do
not launch nested agents. The parent owns scheduling, integration, issue
routing, and acceptance.

- PowerShell is the primary shell.
- Use `python tools/socom.py` for every public reconstruction command.
- Connect the Ghidra MCP to project `soCOM` and pass `program=socom.elf` on
  every program-sensitive call.
- Never open, switch, import, close, delete, save all, run scripts, use the
  debugger, patch bytes, or clear flow during routine work.
- `.claude/settings.json` denies direct edits to canonical state and immutable
  support inputs; use the CLI for state changes.
