# Claude compatibility surface

Root `AGENTS.md`, `.codex/skills`, and `.codex/agents` are canonical.
Claude-facing skill and agent files contain discovery frontmatter and point to
those canonical procedures. They must not acquire independent policy.

Validate the complete mirror with:

```powershell
python tools/socom.py audit agent-surface --strict
```
