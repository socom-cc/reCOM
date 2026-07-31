# Tracker directory

The root [AGENTS.md](../AGENTS.md) is authoritative. Files in this directory are
generated control state or immutable manifests. Never edit
`RECONSTRUCTION_PROGRESS.json` or `REFERENCE_CENSUS.json` manually; use
`python tools/socom.py`. Workspace tooling/process issues are maintained only
through the registered `issue` commands; do not edit
`WORKSPACE_ISSUES.json` manually.
