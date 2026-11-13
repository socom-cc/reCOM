"""Cross-surface audits for workspace tools, roles, skills, and documentation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .constants import STAGES
from .capabilities import CAPABILITIES, audit_capabilities, capability_document
from .source import audit_independence
from .tracker import load_tracker


SKILL_FRONTMATTER_KEYS = frozenset({"name", "description"})
AGENT_FRONTMATTER_REQUIRED = frozenset({"name", "description", "disallowedTools", "effort"})
# Claude Code subagent frontmatter fields; anything else is a typo or a foreign harness key.
AGENT_FRONTMATTER_KEYS = AGENT_FRONTMATTER_REQUIRED | {
    "tools",
    "model",
    "permissionMode",
    "maxTurns",
    "skills",
    "mcpServers",
    "hooks",
    "memory",
    "background",
    "isolation",
    "color",
}
AGENT_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
ROLE_ACCESS = frozenset({"read-only", "workspace-write"})
WRITE_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})
GHIDRA_SKILLS = ("socom-ghidra-workflow", "socom-ghidra-reconstruction")
GHIDRA_ROLES = ("socom-ghidra-fact-mapper", "socom-ghidra-reconstructor")
SURFACE_NAME_RE = re.compile(r"^socom-[a-z0-9]+(?:-[a-z0-9]+)*$")
SURFACE_REFERENCE_RE = re.compile(r"`(socom-[a-z0-9]+(?:-[a-z0-9]+)*)`")
ROOT_AUTHORITY_RE = re.compile(
    r"\bRoot (?:`AGENTS\.md`|\[`AGENTS\.md`\]\([^)\s]+\))"
    r"(?: and .{1,160}?)? (?:is|are) authoritative"
)
# Wording of the retired pointer stubs: a skill or role must hold its own text.
STUB_WORDING_RE = re.compile(
    r"\.codex[/\\]|canonical procedure at|developer_instructions|"
    r"this (?:stub|mirror) adds no",
    re.I,
)
RETIRED_SURFACE_RE = re.compile(r"\.codex[/\\`]")
MIN_SURFACE_WORDS = 40


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n") if path.is_file() else ""


def _split_frontmatter(path: Path) -> tuple[dict[str, str] | None, str, list[str]]:
    """Return (fields, body, problems); fields is None when there is no frontmatter."""

    text = _read_text(path)
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return None, text, ["missing frontmatter"]
    fields: dict[str, str] = {}
    problems: list[str] = []
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        if ": " not in line or line.startswith(" "):
            problems.append(f"malformed frontmatter line {line!r}")
            continue
        key, value = line.split(": ", 1)
        if key in fields:
            problems.append(f"duplicate frontmatter key {key!r}")
        fields[key] = value.strip()
    return fields, text[match.end() :], problems


def _frontmatter(path: Path) -> dict[str, str]:
    fields, _body, _problems = _split_frontmatter(path)
    return fields or {}


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _documented_roles(claude_md: str) -> dict[str, str]:
    """Role -> access posture from the CLAUDE.md role table."""

    roles: dict[str, str] = {}
    for line in claude_md.splitlines():
        match = re.match(r"^\| `(socom-[a-z0-9-]+)` \| ([^|]+?) \|\s*$", line)
        if match:
            roles[match.group(1)] = match.group(2).split()[0]
    return roles


def _documented_skills(agents_md: str) -> set[str]:
    """Skill names from the table rows of the AGENTS.md "Skills and roles" section."""

    section = re.search(r"^## Skills and roles\n(.*?)(?=^## |\Z)", agents_md, re.S | re.M)
    if not section:
        return set()
    return {
        name
        for line in section.group(1).splitlines()
        if line.startswith("|")
        for name in SURFACE_REFERENCE_RE.findall(line)
    }


def _surface_body_errors(body: str) -> list[str]:
    errors: list[str] = []
    normalized = _normalized(body)
    if not ROOT_AUTHORITY_RE.search(normalized):
        errors.append("body omits root authority")
    if STUB_WORDING_RE.search(normalized):
        errors.append("body keeps pointer-stub wording")
    if len(normalized.split()) < MIN_SURFACE_WORDS:
        errors.append("body is too short to be self-contained")
    return errors


def agent_surface(root: Path, commands: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    if (root / ".codex").exists():
        errors.append(".codex is a retired harness surface; .claude is the only home")
    agents_md = _read_text(root / "AGENTS.md")
    claude_md_text = _read_text(root / "CLAUDE.md")

    skills = {
        path.parent.name: path
        for path in sorted((root / ".claude" / "skills").glob("*/SKILL.md"))
    }
    if not skills:
        errors.append(".claude/skills defines no skills")
    bodies: dict[str, str] = {}
    for name, path in skills.items():
        label = f"skill {name}"
        fields, body, problems = _split_frontmatter(path)
        errors.extend(f"{label}: {problem}" for problem in problems)
        if fields is None:
            continue
        bodies[path.relative_to(root).as_posix()] = body
        if set(fields) != SKILL_FRONTMATTER_KEYS:
            errors.append(
                f"{label}: frontmatter keys must be exactly "
                f"{sorted(SKILL_FRONTMATTER_KEYS)}, found {sorted(fields)}"
            )
        if fields.get("name") != name or not SURFACE_NAME_RE.match(name):
            errors.append(f"{label}: frontmatter name must equal its directory name")
        description = fields.get("description", "")
        if not description or len(description) > 1024:
            errors.append(f"{label}: description must be 1-1024 characters")
        if not re.search(r"^# \S", body, re.M):
            errors.append(f"{label}: body has no title heading")
        errors.extend(f"{label}: {error}" for error in _surface_body_errors(body))
        if name in GHIDRA_SKILLS and (
            "`ghidra` MCP" not in _normalized(body) or "program=socom.elf" not in body
        ):
            errors.append(f"{label}: omits the `ghidra` MCP and program=socom.elf contract")
    for name in sorted(_documented_skills(agents_md) - skills.keys()):
        errors.append(f"AGENTS.md documents missing skill {name}")

    agents = {
        path.stem: path for path in sorted((root / ".claude" / "agents").glob("*.md"))
    }
    if not agents:
        errors.append(".claude/agents defines no roles")
    documented_roles = _documented_roles(claude_md_text)
    for name in sorted(documented_roles.keys() - agents.keys()):
        errors.append(f"CLAUDE.md documents missing role {name}")
    for name, path in agents.items():
        label = f"role {name}"
        fields, body, problems = _split_frontmatter(path)
        errors.extend(f"{label}: {problem}" for problem in problems)
        if fields is None:
            continue
        bodies[path.relative_to(root).as_posix()] = body
        missing = sorted(AGENT_FRONTMATTER_REQUIRED - fields.keys())
        if missing:
            errors.append(f"{label}: missing frontmatter keys {missing}")
        unknown = sorted(fields.keys() - AGENT_FRONTMATTER_KEYS)
        if unknown:
            errors.append(f"{label}: unknown frontmatter keys {unknown}")
        if fields.get("name") != name or not SURFACE_NAME_RE.match(name):
            errors.append(f"{label}: frontmatter name must equal its file name")
        if not fields.get("description"):
            errors.append(f"{label}: description is empty")
        if fields.get("effort") not in AGENT_EFFORTS:
            errors.append(f"{label}: effort must be one of {sorted(AGENT_EFFORTS)}")
        disallowed = {
            value.strip()
            for value in fields.get("disallowedTools", "").split(",")
            if value.strip()
        }
        if "Agent" not in disallowed:
            errors.append(f"{label}: must disallow nested agents")
        access = documented_roles.get(name)
        if access is None:
            errors.append(f"{label}: not documented in the CLAUDE.md role table")
        elif access not in ROLE_ACCESS:
            errors.append(
                f"{label}: CLAUDE.md access {access!r} is not one of {sorted(ROLE_ACCESS)}"
            )
        elif access == "read-only" and not WRITE_TOOLS <= disallowed:
            errors.append(f"{label}: read-only role does not disallow {sorted(WRITE_TOOLS)}")
        elif access == "workspace-write" and WRITE_TOOLS & disallowed:
            errors.append(f"{label}: workspace-write role blocks workspace writes")
        errors.extend(f"{label}: {error}" for error in _surface_body_errors(body))
        if "spawn another agent" not in _normalized(body).casefold():
            errors.append(f"{label}: body does not forbid spawning another agent")
        if name in GHIDRA_ROLES and "program=socom.elf" not in body:
            errors.append(f"{label}: omits the program=socom.elf contract")

    # Every backticked socom-* name in the instructions and the surface itself
    # must resolve to a skill or a role, and no document may point at the
    # retired .codex surface.
    known = skills.keys() | agents.keys()
    references = {
        "AGENTS.md": agents_md,
        "CLAUDE.md": claude_md_text,
        ".claude/README.md": _read_text(root / ".claude" / "README.md"),
        **bodies,
    }
    for label, text in references.items():
        for name in sorted(set(SURFACE_REFERENCE_RE.findall(text)) - known):
            errors.append(f"{label}: references unknown skill or role {name}")
    documents = {
        **references,
        "README.md": _read_text(root / "README.md"),
        **{
            path.relative_to(root).as_posix(): _read_text(path)
            for path in sorted((root / "docs").rglob("*.md"))
        },
    }
    for label, text in documents.items():
        if RETIRED_SURFACE_RE.search(text):
            errors.append(f"{label}: references the retired .codex surface")
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
        "skill_count": len(skills),
        "agent_count": len(agents),
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
        "progress work reopen": True,
        "progress work release": True,
        "progress audit": False,
        "progress next": False,
        "ghidra preflight": False,
        "ghidra receipt": True,
        "ghidra preflight-batch": False,
        "ghidra fingerprint": True,
        "debug apply-program": False,
        "ghidra apply-types": True,
        "ghidra map-zero-fill": True,
        "ghidra repair-signatures": True,
        "ghidra repair-labels": True,
        "ghidra repair-boundaries": True,
        "progress add-repair": True,
        "debug batch-program": False,
        "ghidra apply-batch": True,
        "ghidra restore-accepted": True,
        "progress handoff-live-ghidra": True,
        "progress advance-live-ghidra": True,
        "progress rebaseline-live-ghidra": True,
        "progress apply-source-plan": True,
        "progress open-capability-gate": True,
        "progress reopen-source-plan": True,
        "source annotate": True,
        "source apply-check": False,
        "source gate-check": False,
        "progress handoff-source-gate": True,
        "progress accept-source-gate": True,
        "audit source-baseline": False,
        # Name parsing is read-only; --output writes only under build/.
        "reference demangle": False,
        # Stage 5 phase A is read-only: outputs and the order cache are build/ products.
        "order target": False,
        "order link-spec": False,
        "order draft": False,
        "order sql": False,
        # Order plans are build/ products; decide edits one under the item's lease, like source plan decide.
        "order plan draft": False,
        "order plan decide": True,
        "order plan validate": False,
        # Stage 5 phase B: the governed skeleton route writes src/ and the tracker; apply-check only reads (its render is a build/ product).
        "progress add-order-skeleton-prepare": True,
        "progress apply-order-skeleton": True,
        "order skeleton decide": True,
        "order skeleton apply-check": False,
        "progress handoff-order-skeleton": True,
        "progress accept-order-skeleton": True,
        # After a stage 4 amendment: reopen (tracker; the merge-ancestor blobs are build/ products) and rebase (tracker, frozen base).
        "progress reopen-order-skeleton": True,
        "progress rebase-function-order": True,
        "progress amend-source-plan": True,
        "progress accept-source-amendment": True,
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
        "ghidra preflight-batch": ("required", False),
        "ghidra fingerprint": ("required", False),
        "ghidra apply-types": ("required", True),
        "ghidra map-zero-fill": ("required", True),
        "ghidra repair-signatures": ("required", True),
        "ghidra repair-labels": ("required", True),
        "ghidra repair-boundaries": ("required", True),
        "ghidra apply-batch": ("required", True),
        "ghidra restore-accepted": ("required", True),
        "progress handoff-live-ghidra": ("required", True),
        "progress advance-live-ghidra": ("required", False),
        "progress rebaseline-live-ghidra": ("required", False),
        # Stage 4 reads the live receipt and never writes Ghidra.
        "source gate-check": ("optional", False),
        "progress handoff-source-gate": ("required", False),
        "progress accept-source-gate": ("required", False),
        "progress amend-source-plan": ("none", False),
        "progress accept-source-amendment": ("required", False),
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
    # Validators such as `audit source-trace` are not producers: a stage is
    # active only once a command that creates its work is registered here.
    active_producers = {
        "reference-census": {"reference census", "reference verify"},
        "debug-metadata-import": {"debug import-plan", "progress work packet"},
        "ghidra-reconstruction": {"progress decompose-stage", "ghidra apply-recon"},
    }
    # A stage produced and closed by several registered routes (decomposition,
    # planning, apply and the gate route): every one of them must exist.
    complete_producers = {
        "source-correlation": {
            "progress decompose-stage",
            "source plan validate",
            "source annotate",
            "progress apply-source-plan",
            "progress handoff-source-gate",
            "progress accept-source-gate",
        },
    }
    # A stage whose planning producer is registered but whose closing route is
    # still a deferred capability: it may be decomposed, never accepted yet.
    partial_producers = {
        "authored-function-order": {
            "progress decompose-stage",
            "order plan validate",
            "progress add-order-skeleton-prepare",
            "progress apply-order-skeleton",
            "progress accept-order-skeleton",
        },
    }
    tracker = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    blockers = {
        stage
        for row in tracker.get("blockers", [])
        if row.get("status") == "open"
        for stage in row.get("blocks", [])
    }
    # A deferred capability naming a stage defers it until its prerequisite
    # (a registered producer) exists, as TOOL_COVERAGE.md reports.
    deferred_capabilities = {
        row["stage"]: row
        for row in CAPABILITIES
        if row.get("status") == "deferred" and row.get("stage")
    }
    deferred: list[dict[str, Any]] = []
    for stage in STAGES:
        if stage in active_producers:
            producers = active_producers[stage]
            if not any(producer in names for producer in producers):
                missing.append({"stage": stage, "expected_one_of": sorted(producers)})
            continue
        if stage in complete_producers:
            if not complete_producers[stage] <= names:
                missing.append({"stage": stage, "expected_all_of": sorted(complete_producers[stage])})
            continue
        seeds = [
            row
            for row in tracker.get("work_items", [])
            if row.get("stage") == stage and row.get("kind") == "stage-seed"
        ]
        gates = [
            row
            for row in tracker.get("work_items", [])
            if row.get("stage") == stage and row.get("kind") == "stage-gate"
        ]
        capability = deferred_capabilities.get(stage)
        decomposed = bool(gates) and stage in partial_producers
        if stage in partial_producers and not partial_producers[stage] <= names:
            missing.append({"stage": stage, "expected_all_of": sorted(partial_producers[stage])})
        if not (seeds or decomposed) or (stage not in blockers and capability is None):
            missing.append(
                {"stage": stage, "error": "deferred stage lacks a seed and explicit blocker"}
            )
        elif stage in blockers:
            deferred.append({"stage": stage, "seed_count": len(seeds), "blocked": True, "decomposed": decomposed})
        else:
            row = {
                "stage": stage,
                "seed_count": len(seeds),
                "blocked": False,
                "capability": capability["id"],
                "prerequisite": capability["blocker"],
            }
            deferred.append(row)
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
