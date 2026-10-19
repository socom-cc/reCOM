from __future__ import annotations

import json
import argparse
import re
import tomllib
from pathlib import Path

from tools._socom.cli import COMMAND_SPECS, build_parser
from tools._socom.guards import source_placement
from tools._socom.issues import audit_issues, load_issues
from tools._socom.source import audit_independence, source_owners
from tools._socom.snapshot import snapshot_status
from tools._socom.tracker import audit_tracker, load_tracker


def test_workspace_is_independent(root: Path) -> None:
    assert audit_independence(root) == []


def test_independence_flags_foreign_tool_entry_points_but_not_own_tests(
    tmp_path: Path,
) -> None:
    foreign = "python " + "Tooling/" + "tools/" + "recoil" + ".py --workspace ../Rebuild"
    own_test = "tests/" + "tools/" + "test_cli" + ".py"
    (tmp_path / "README.md").write_text(f"{foreign}\n{own_test}\n", encoding="utf-8")
    findings = audit_independence(tmp_path)
    assert [row["rule"] for row in findings] == ["foreign reconstruction CLI"]
    assert findings[0]["line"] == 1


def test_independence_rejects_machine_specific_paths(tmp_path: Path) -> None:
    windows_home = "C:" + "\\" + "Users" + "\\" + "ExampleUser" + "\\tool"
    windows_tool = "D:" + "\\" + "Tools" + "\\ghidra"
    unix_home = "/" + "home" + "/" + "example" + "/tool"
    unc_path = "\\" * 2 + "build-host" + "\\share\\tool"
    device_path = "\\" * 2 + "?" + "\\" + windows_home
    (tmp_path / "README.md").write_text(
        "\n".join((windows_home, windows_tool, unix_home, unc_path, device_path)),
        encoding="utf-8",
    )

    rules = {finding["rule"] for finding in audit_independence(tmp_path)}
    assert {
        "machine-specific Windows path",
        "machine-specific Windows device path",
        "machine-specific UNC path",
        "machine-specific Unix home path",
    } <= rules


def test_independence_accepts_portable_and_reference_paths(tmp_path: Path) -> None:
    reference_path = "Z:" + "\\" + "dev" + "\\gamez\\sample.cpp"
    (tmp_path / "AGENTS.md").write_text(
        "\n".join(
            (
                r"%USERPROFILE%\tools",
                r"%LOCALAPPDATA%\soCOM",
                r"$env:APPDATA\soCOM",
                r"$env{TEMP}/soCOM",
                reference_path,
                "docs/reconstruction/WORKFLOW.md",
            )
        ),
        encoding="utf-8",
    )

    assert audit_independence(tmp_path) == []


def test_independence_rejects_dynamic_local_identities(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("USERNAME", "ExampleAccount")
    monkeypatch.setenv("COMPUTERNAME", "EXAMPLE-HOST")
    (tmp_path / "README.md").write_text(
        "ExampleAccount configured EXAMPLE-HOST.\n", encoding="utf-8"
    )

    rules = {finding["rule"] for finding in audit_independence(tmp_path)}
    assert {"local account name", "local computer name"} <= rules


def test_source_placement_rejects_user_profile_but_preserves_target_paths(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "sample.cpp"
    source.parent.mkdir(parents=True)
    local_path = "C:" + "/" + "Users" + "/" + "ExampleUser" + "/local.dat"
    source.write_text(f'static const char *path = "{local_path}";\n', encoding="utf-8")
    assert source_placement(tmp_path)["ok"] is False

    target_root = "D:" + "/"
    reference_path = "Z:" + "\\" + "dev" + "\\gamez\\sample.cpp"
    source.write_text(
        f'static const char *game_path = "{target_root}"; // {reference_path}\n',
        encoding="utf-8",
    )
    assert source_placement(tmp_path)["ok"] is True


def test_local_host_build_products_are_ignored(root: Path) -> None:
    ignored = set((root / ".gitignore").read_text(encoding="utf-8").splitlines())
    assert "/build/host-tools/" in ignored
    assert "/build/Testing/" in ignored


def test_workspace_has_only_the_ghidra_analysis_surface(root: Path) -> None:
    retired_terms = (
        "binary" + " ninja",
        "binary" + "-ninja",
        "bin" + "ja",
        "b" + "n" + "d" + "b",
        "needs_" + "bin" + "ja",
        "socom_" + "b" + "n",
    )
    retired = re.compile(
        "|".join(re.escape(term) for term in retired_terms)
        + r"|\b"
        + "B"
        + "N"
        + r"\b",
        re.IGNORECASE,
    )
    findings = []
    excluded = {".git", "build", ".pytest_cache", "__pycache__"}
    project_suffixes = {".gpr", ".rep", ".gar", ".gzf"}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in excluded for part in relative.parts):
            continue
        if retired.search(re.sub(r"\s+", " ", relative.as_posix())):
            findings.append(relative.as_posix())
        if path.is_file() and path.suffix.casefold() in project_suffixes:
            findings.append(relative.as_posix())
        if not path.is_file() or path.suffix.casefold() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".elf",
            ".exe",
            ".dll",
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if retired.search(re.sub(r"\s+", " ", text)):
            findings.append(relative.as_posix())
    assert findings == []


def test_agent_surfaces_are_complete_and_thin(root: Path) -> None:
    canonical = {
        path.parent.name
        for path in (root / ".codex" / "skills").glob("*/SKILL.md")
    }
    compatibility = {
        path.parent.name
        for path in (root / ".claude" / "skills").glob("*/SKILL.md")
    }
    assert canonical == compatibility
    assert len(canonical) == 16
    for path in (root / ".claude" / "skills").glob("*/SKILL.md"):
        canonical_path = root / ".codex" / "skills" / path.parent.name / "SKILL.md"
        canonical_frontmatter = re.match(
            r"^---\n(.*?)\n---\n",
            canonical_path.read_text(encoding="utf-8"),
            re.S,
        )
        mirror_frontmatter = re.match(
            r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S
        )
        assert canonical_frontmatter
        assert mirror_frontmatter
        assert canonical_frontmatter.group(1) == mirror_frontmatter.group(1)
        keys = {
            line.split(":", 1)[0]
            for line in canonical_frontmatter.group(1).splitlines()
            if ":" in line
        }
        assert keys == {"name", "description"}
        mirror_body = path.read_text(encoding="utf-8")[
            mirror_frontmatter.end() :
        ]
        assert ".codex/skills/" in mirror_body
        assert len(mirror_body.splitlines()) <= 5
        metadata = canonical_path.parent / "agents" / "openai.yaml"
        assert metadata.is_file()
        metadata_text = metadata.read_text(encoding="utf-8")
        assert f"${path.parent.name}" in metadata_text
        short = re.search(r'  short_description: "([^"]+)"', metadata_text)
        assert short
        assert 25 <= len(short.group(1)) <= 64
        if path.parent.name in {
            "socom-ghidra-workflow",
            "socom-ghidra-reconstruction",
        }:
            assert 'type: "mcp"' in metadata_text
            assert 'value: "ghidra"' in metadata_text


def test_agent_roles_are_discoverable_and_paired(root: Path) -> None:
    codex = {path.stem: path for path in (root / ".codex" / "agents").glob("*.toml")}
    claude = {path.stem: path for path in (root / ".claude" / "agents").glob("*.md")}
    assert codex.keys() == claude.keys()
    assert len(codex) == 13
    for path in codex.values():
        value = tomllib.loads(path.read_text(encoding="utf-8"))
        assert value["model"] in {"gpt-5.6-sol", "gpt-5.6-terra"}
        assert value["model_reasoning_effort"] == "xhigh"
        assert value["sandbox_mode"] in {"read-only", "workspace-write"}
        assert value["developer_instructions"]
        normalized_instructions = " ".join(
            value["developer_instructions"].split()
        )
        assert "spawn another agent" in normalized_instructions.casefold()
    for name in ("socom-ghidra-fact-mapper", "socom-ghidra-reconstructor"):
        value = tomllib.loads(codex[name].read_text(encoding="utf-8"))
        assert "program=socom.elf" in value["developer_instructions"]
    assert (root / "CLAUDE.md").read_text(encoding="utf-8").splitlines()[0] == "@AGENTS.md"


def _leaf_commands(parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()) -> set[str]:
    children: list[tuple[str, argparse.ArgumentParser]] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            children.extend(action.choices.items())
    if not children:
        return {" ".join(prefix)}
    result: set[str] = set()
    for name, child in children:
        result.update(_leaf_commands(child, (*prefix, name)))
    return result


def test_command_registry_exactly_matches_parser() -> None:
    registered = {row.path for row in COMMAND_SPECS}
    assert len(registered) == len(COMMAND_SPECS) == 102
    assert _leaf_commands(build_parser()) == registered


def test_tracker_file_is_valid_and_source_is_unverified(root: Path) -> None:
    tracker = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    assert audit_tracker(tracker) == []
    assert all(owner["status"] == "unverified" for owner in tracker["owners"])
    assert len(tracker["symbols"]) == 21_894
    assert len(tracker["relocations"]) == 115_142
    assert tracker["schema_version"] == 5
    # Governed repairs join through migrations and `progress add-repair`;
    # every one must be a recorded spec.
    from tools._socom.repairs import REPAIRS

    repairs = [row["id"] for row in tracker["work_items"] if row["kind"] == "ghidra-repair"]
    assert set(repairs) <= set(REPAIRS)
    # Stage 3 adds one plan and one apply item per reconstruction group.
    groups = (next(row for row in tracker["stages"] if row["name"] == "ghidra-reconstruction").get("decomposition") or {}).get(
        "group_count", 0
    )
    assert groups == 329
    recon = [row for row in tracker["work_items"] if row["kind"] in ("recon-plan-group", "recon-apply-group")]
    assert len(recon) == 2 * groups
    assert len(tracker["work_items"]) - len(repairs) - len(recon) == 91
    assert len(
        [row for row in tracker["work_items"] if "-plan-" in row["kind"] and row not in recon]
    ) == 41
    assert len(
        [row for row in tracker["work_items"] if "-apply-" in row["kind"] and row not in recon]
    ) == 41


def test_reference_and_tracker_json_are_canonical(root: Path) -> None:
    for relative in (
        ".agent/REFERENCE_CENSUS.json",
        ".agent/RECONSTRUCTION_PROGRESS.json",
        ".agent/WORKSPACE_ISSUES.json",
    ):
        path = root / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        rendered = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        assert path.read_text(encoding="utf-8") == rendered


def test_control_state_schemas_are_versioned(root: Path) -> None:
    for relative in (
        ".agent/schema/reference-census.schema.json",
        ".agent/schema/reconstruction-progress.schema.json",
        ".agent/schema/workspace-issues.schema.json",
    ):
        schema = json.loads((root / relative).read_text(encoding="utf-8"))
        assert schema["$schema"].endswith("2020-12/schema")
        assert schema["$id"].startswith("socom:schema:")


def test_workspace_issue_ledger_replaces_shadow_state(root: Path) -> None:
    value = load_issues(root)
    assert audit_issues(value) == []
    assert not (root / ".agent" / "RECONSTRUCTION_ISSUES.json").exists()
    assert not (root / "compiler" / "PROBE_STATUS.json").exists()


def test_source_inventory(root: Path) -> None:
    owners = source_owners(root)
    assert len(owners) == 316
    assert len({owner["id"] for owner in owners}) == len(owners)


def test_readme_progress_snapshot_is_fresh(root: Path) -> None:
    tracker = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    assert snapshot_status(root, tracker)["fresh"] is True
