# Claude Code surface

Root `AGENTS.md` (imported by `CLAUDE.md`) is authoritative. This folder is
the single home of the project's skills and roles:

- `skills/<skill>/SKILL.md`: discovery frontmatter (`name`, `description`)
  and the complete procedure;
- `agents/<role>.md`: frontmatter (`name`, `description`, `disallowedTools`,
  `effort`) and the role's complete instructions;
- `settings.json`: the project permission policy.

Skills and roles may narrow root policy but must not weaken it. Validate the
complete surface with:

```powershell
python tools/socom.py audit agent-surface --strict
```
