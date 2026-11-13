@AGENTS.md

## Claude Code harness notes

The imported root instructions are authoritative. This file only maps them
onto Claude Code.

Project skills are discovered through `.claude/skills/socom-*/SKILL.md`. Each
skill file holds its discovery frontmatter (`name`, `description`) and the
complete procedure.

Project roles are Claude agents defined in `.claude/agents/<role>.md`. The
access column is each role's write posture; read-only roles disallow the
`Edit`, `Write`, and `NotebookEdit` tools, and every role disallows `Agent`:

| Claude agent | Access |
| --- | --- |
| `socom-ghidra-fact-mapper` | read-only |
| `socom-ghidra-reconstructor` | read-only (Ghidra writes only under the `ghidra-writer` lease) |
| `socom-dwarf-importer` | workspace-write |
| `socom-recon-planner` | workspace-write |
| `socom-reference-mapper` | read-only |
| `socom-provider-data-classifier` | read-only |
| `socom-scaffold-auditor` | read-only |
| `socom-source-owner-mapper` | workspace-write |
| `socom-source-owner-scrutinizer` | read-only |
| `socom-source-worker` | workspace-write |
| `socom-tool-maintainer` | workspace-write |
| `socom-verifier` | workspace-write |
| `socom-workspace-librarian` | read-only |

Each agent file holds that role's complete instructions. Roles do not launch
nested agents. The parent owns scheduling, integration, issue routing, and
acceptance.

- PowerShell is the primary shell.
- Use `python tools/socom.py` for every public reconstruction command.
- Connect the Ghidra MCP to project `soCOM` and pass `program=socom.elf` on
  every program-sensitive call.
- Never open, switch, import, close, delete, save all, run scripts, use the
  debugger, patch bytes, or clear flow during routine work.
- `.claude/settings.json` denies direct edits to canonical state and immutable
  support inputs; use the CLI for state changes.
