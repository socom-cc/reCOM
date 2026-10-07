"""Cross-surface audits for workspace tools, roles, skills, and documentation."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from .constants import STAGES
from .capabilities import audit_capabilities, capability_document
from .source import audit_independence
from .tracker import load_tracker


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            result[key] = value
    return result


def agent_surface(root: Path, commands: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    codex_skills = {
        path.parent.name: path
        for path in (root / ".codex" / "skills").glob("*/SKILL.md")
    }
    claude_skills = {
        path.parent.name: path
        for path in (root / ".claude" / "skills").glob("*/SKILL.md")
    }
    if codex_skills.keys() != claude_skills.keys():
        errors.append(
            "Codex/Claude skill names differ: "
            + repr(sorted(codex_skills.keys() ^ claude_skills.keys()))
        )
    for name, canonical in codex_skills.items():
        mirror = claude_skills.get(name)
        if mirror and _frontmatter(canonical) != _frontmatter(mirror):
            errors.append(f"{name}: Claude skill frontmatter differs from canonical")
        if mirror:
            body = mirror.read_text(encoding="utf-8")
            if "Root `AGENTS.md` is authoritative" not in body:
                errors.append(f"{name}: Claude mirror omits root authority")
            expected_path = f".codex/skills/{name}/SKILL.md"
            if expected_path not in body:
                errors.append(f"{name}: Claude mirror omits {expected_path}")
        metadata = canonical.parent / "agents" / "openai.yaml"
        if not metadata.is_file():
            errors.append(f"{name}: missing agents/openai.yaml")
        elif f"${name}" not in metadata.read_text(encoding="utf-8"):
            errors.append(f"{name}: default prompt does not invoke the skill")
        elif name in {"socom-ghidra-workflow", "socom-ghidra-reconstruction"}:
            metadata_text = metadata.read_text(encoding="utf-8")
            if 'type: "mcp"' not in metadata_text or 'value: "ghidra"' not in metadata_text:
                errors.append(f"{name}: metadata omits the Ghidra MCP dependency")

    codex_agents = {
        path.stem: path for path in (root / ".codex" / "agents").glob("*.toml")
    }
    claude_agents = {
        path.stem: path for path in (root / ".claude" / "agents").glob("*.md")
    }
    if codex_agents.keys() != claude_agents.keys():
        errors.append(
            "Codex/Claude agent names differ: "
            + repr(sorted(codex_agents.keys() ^ claude_agents.keys()))
        )
    for name, path in codex_agents.items():
        try:
            row = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{name}: invalid Codex agent TOML: {exc}")
            continue
        required = {
            "name",
            "description",
            "model",
            "model_reasoning_effort",
            "sandbox_mode",
            "developer_instructions",
        }
        missing = sorted(key for key in required if not row.get(key))
        if missing:
            errors.append(f"{name}: missing Codex agent fields {missing}")
            continue
        mirror = claude_agents.get(name)
        if mirror is None:
            continue
        mirror_frontmatter = _frontmatter(mirror)
        expected_name = str(row["name"]).replace("_", "-")
        if mirror_frontmatter.get("name") != expected_name:
            errors.append(f"{name}: Claude role name differs from canonical")
        if mirror_frontmatter.get("description") != row["description"]:
            errors.append(f"{name}: Claude role description differs from canonical")
        if mirror_frontmatter.get("effort") != row["model_reasoning_effort"]:
            errors.append(f"{name}: Claude role effort differs from canonical")
        disallowed = {
            value.strip()
            for value in mirror_frontmatter.get("disallowedTools", "").split(",")
            if value.strip()
        }
        if "Agent" not in disallowed:
            errors.append(f"{name}: Claude role must disallow nested agents")
        readonly_tools = {"Edit", "Write", "NotebookEdit"}
        if row["sandbox_mode"] == "read-only" and not readonly_tools <= disallowed:
            errors.append(f"{name}: Claude role does not mirror read-only sandbox")
        if row["sandbox_mode"] == "workspace-write" and readonly_tools & disallowed:
            errors.append(f"{name}: Claude role incorrectly blocks workspace writes")
        body = mirror.read_text(encoding="utf-8")
        if "Root `AGENTS.md` is authoritative" not in body:
            errors.append(f"{name}: Claude role omits root authority")
        if f".codex/agents/{name}.toml" not in body:
            errors.append(f"{name}: Claude role omits canonical role path")
    claude_md = (root / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    if not claude_md or claude_md[0].strip() != "@AGENTS.md":
        errors.append("CLAUDE.md must begin with @AGENTS.md")
    try:
        settings = json.loads(
            (root / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        permissions = settings.get("permissions")
        if not isinstance(permissions, dict):
            errors.append(".claude/settings.json has no permissions policy")
        else:
            expected_denies = {
                "Edit(/.agent/RECONSTRUCTION_PROGRESS.json)",
                "Edit(/.agent/REFERENCE_CENSUS.json)",
                "Edit(/.agent/WORKSPACE_ISSUES.json)",
                "Edit(/support/**)",
            }
            if set(permissions.get("deny", [])) != expected_denies:
                errors.append(".claude/settings.json deny policy differs from canonical")
            required_allows = {
                "Bash(python -m pytest:*)",
                "Bash(cmake:*)",
                "Bash(ctest:*)",
            }
            if not required_allows <= set(permissions.get("allow", [])):
                errors.append(".claude/settings.json lacks safe validation allowances")
    except Exception as exc:
        errors.append(f".claude/settings.json is invalid: {exc}")

    paths = [row["command"] for row in commands]
    if len(paths) != len(set(paths)):
        errors.append("command registry contains duplicate command paths")
    required_commands = {
        "commands",
        "doctor",
        "ghidra preflight",
        "audit agent-surface",
        "audit workflow-contracts",
        "audit workspace",
        "progress audit",
        "progress next",
        "progress migrate",
        "progress work packet",
        "reference verify",
        "reference relocations",
        "docs readme-progress",
    }
    missing_commands = sorted(required_commands - set(paths))
    if missing_commands:
        errors.append(f"command registry is missing {missing_commands}")
    return {
        "ok": not errors,
        "canonical_skill_count": len(codex_skills),
        "paired_agent_count": len(codex_agents),
        "command_count": len(commands),
        "errors": errors,
    }


def workflow_contracts(root: Path, commands: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    by_command = {row["command"]: row for row in commands}
    expected = {
        "progress work claim": True,
        "progress work heartbeat": True,
        "progress work handoff": True,
        "progress work accept": True,
        "progress work reject": True,
        "progress work release": True,
        "progress audit": False,
        "progress next": False,
        "ghidra preflight": False,
        "ghidra receipt": True,
        "debug apply-program": False,
        "ghidra apply-types": True,
        "ghidra map-zero-fill": True,
        "debug batch-program": False,
        "ghidra apply-batch": True,
        "ghidra restore-accepted": True,
        "progress handoff-live-ghidra": True,
        "progress advance-live-ghidra": True,
        "progress rebaseline-live-ghidra": True,
    }
    for command, mutates in expected.items():
        row = by_command.get(command)
        if not row:
            errors.append(f"missing workflow command {command}")
        elif row["mutates"] is not mutates:
            errors.append(f"{command}: mutates metadata must be {mutates}")
    ghidra_contracts = {
        "doctor": ("optional", False),
        "ghidra preflight": ("required", False),
        "ghidra receipt": ("required", False),
        "ghidra apply-types": ("required", True),
        "ghidra map-zero-fill": ("required", True),
        "ghidra apply-batch": ("required", True),
        "ghidra restore-accepted": ("required", True),
        "progress handoff-live-ghidra": ("required", True),
        "progress advance-live-ghidra": ("required", False),
        "progress rebaseline-live-ghidra": ("required", False),
    }
    for command, (requirement, mutates_live) in ghidra_contracts.items():
        row = by_command.get(command)
        if row and (
            row.get("ghidra_requirement") != requirement
            or row.get("mutates_ghidra") is not mutates_live
        ):
            errors.append(f"{command}: Ghidra metadata differs from its contract")
    tracker = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    if tracker.get("policy", {}).get("ghidra_writer_limit") != 1:
        errors.append("tracker must enforce one Ghidra writer")
    if tracker.get("stage_order") != list(STAGES):
        errors.append("tracker stage order differs from canonical pipeline")
    return {"ok": not errors, "errors": errors, "checked_commands": len(expected)}


def workspace(root: Path) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    approved = {
        "build",
        ".pytest_cache",
        "__pycache__",
    }
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        parts = set(relative.parts)
        if any(part in approved or part.endswith(".egg-info") for part in parts):
            continue
        if path.suffix.casefold() in {".pyc", ".pyo", ".tmp"}:
            findings.append(
                {"path": relative.as_posix(), "reason": "generated/scratch artifact"}
            )
    return {
        "ok": not findings,
        "finding_count": len(findings),
        "findings": findings,
    }


def docs(root: Path, commands: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    markdown = [
        root / "AGENTS.md",
        root / "CLAUDE.md",
        root / "README.md",
        *sorted((root / "docs").rglob("*.md")),
        *sorted((root / ".codex" / "skills").glob("*/SKILL.md")),
        *sorted((root / ".claude" / "skills").glob("*/SKILL.md")),
        *sorted((root / ".claude" / "agents").glob("*.md")),
        root / ".claude" / "README.md",
        root / "tools" / "functional_verify_targets" / "README.md",
    ]
    command_names = {row["command"] for row in commands}
    for path in markdown:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)", text):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                errors.append(
                    f"{path.relative_to(root).as_posix()}: link escapes workspace: {target}"
                )
                continue
            if not resolved.exists():
                errors.append(
                    f"{path.relative_to(root).as_posix()}: missing link target {target}"
                )
        for invocation in re.findall(r"python\s+tools/socom\.py\s+([^\r\n`]+)", text):
            tokens = [
                token
                for token in invocation.strip().split()
                if not token.startswith("<") and not token.startswith("--")
            ]
            if not tokens:
                continue
            candidates = [
                " ".join(tokens[:length])
                for length in range(min(4, len(tokens)), 0, -1)
            ]
            if not any(candidate in command_names for candidate in candidates):
                errors.append(
                    f"{path.relative_to(root).as_posix()}: unregistered command "
                    f"{invocation.strip()!r}"
                )
    return {
        "ok": not errors,
        "document_count": len([path for path in markdown if path.is_file()]),
        "errors": errors,
    }


def pipeline_reachability(root: Path, commands: list[dict[str, Any]]) -> dict[str, Any]:
    names = {row["command"] for row in commands}
    missing = []
    active_producers = {
        "reference-census": {"reference census", "reference verify"},
        "debug-metadata-import": {"debug import-plan", "progress work packet"},
        "ghidra-reconstruction": {"progress handoff-live-ghidra", "ghidra receipt"},
        "source-correlation": {"audit source-trace", "source artifacts"},
    }
    tracker = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    blockers = {
        stage
        for row in tracker.get("blockers", [])
        if row.get("status") == "open"
        for stage in row.get("blocks", [])
    }
    deferred: list[dict[str, Any]] = []
    for stage in STAGES:
        if stage in active_producers:
            producers = active_producers[stage]
            if not any(producer in names for producer in producers):
                missing.append({"stage": stage, "expected_one_of": sorted(producers)})
            continue
        seeds = [
            row
            for row in tracker.get("work_items", [])
            if row.get("stage") == stage and row.get("kind") == "stage-seed"
        ]
        if not seeds or stage not in blockers:
            missing.append(
                {"stage": stage, "error": "deferred stage lacks a seed and explicit blocker"}
            )
        else:
            deferred.append({"stage": stage, "seed_count": len(seeds), "blocked": True})
    return {"ok": not missing, "missing": missing, "deferred": deferred}


def independence(root: Path) -> dict[str, Any]:
    findings = audit_independence(root)
    return {"ok": not findings, "findings": findings}


def retired_surface(root: Path) -> dict[str, Any]:
    """Reject obsolete analysis-backend files and terms, even when wrapped."""

    terms = (
        "binary" + " ninja",
        "binary" + "-ninja",
        "bin" + "ja",
        "b" + "n" + "d" + "b",
        "needs_" + "bin" + "ja",
        "socom_" + "b" + "n",
    )
    pattern = re.compile("|".join(re.escape(term) for term in terms), re.I)
    findings: list[dict[str, Any]] = []
    excluded = {".git", "build", ".pytest_cache", "__pycache__"}
    binary_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".elf", ".exe", ".dll"}
    project_suffixes = {".gpr", ".rep", ".gar", ".gzf"}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in excluded for part in relative.parts):
            continue
        relative_text = re.sub(r"\s+", " ", relative.as_posix())
        if pattern.search(relative_text) or path.suffix.casefold() in project_suffixes:
            findings.append({"path": relative.as_posix(), "where": "path"})
        if not path.is_file() or path.suffix.casefold() in binary_suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        normalized = re.sub(r"\s+", " ", text)
        if pattern.search(normalized):
            findings.append({"path": relative.as_posix(), "where": "content"})
    return {"ok": not findings, "findings": findings}


def capability_coverage(root: Path, commands: list[dict[str, Any]]) -> dict[str, Any]:
    report = audit_capabilities(commands)
    target = root / "docs" / "reconstruction" / "TOOL_COVERAGE.md"
    expected = capability_document()
    fresh = target.is_file() and target.read_text(encoding="utf-8") == expected
    errors = list(report["errors"])
    if not fresh:
        errors.append("generated tool coverage document is stale")
    return {**report, "ok": not errors, "document_fresh": fresh, "errors": errors}
