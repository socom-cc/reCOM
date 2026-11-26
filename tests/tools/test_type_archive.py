"""The governed export of the prototype's data types to a .gdt (bridge mocked)."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pytest

from tools._socom import cli, type_archive
from tools._socom.type_archive import (
    KINDS,
    RECORD_PATH,
    SCRIPT_PATH,
    SCRIPT_SHA256,
    TypeArchiveFailure,
    archive_script,
    check_output,
    export_type_archive,
    parse_result,
    resolve_output,
)
from tools._socom.util import SocomError

TYPES = [
    ("CNode", "project", "12", "/project/CNode"),
    ("CNode *", "project", "4", "/project/CNode *"),
    ("char[8]", "", "8", "/char[8]"),
    ("tag_NODE_TYPE", "project", "4", "/project/tag_NODE_TYPE"),
    ("int", "", "4", "/int"),
]
COUNTS = {"total": 5, "structure": 1, "union": 0, "enum": 1, "typedef": 0, "function_definition": 0,
          "pointer": 1, "array": 1, "builtin": 1, "other": 0}


class _Bridge:
    """The live program as far as the export reads it, and the script's effect on disk."""

    def __init__(self, script: str = "ok") -> None:
        self.types = list(TYPES)
        self.categories = ["project", "std"]
        self.script = script
        self.posts: list[tuple[str, dict]] = []
        self.target: Path | None = None

    def request(self, endpoint: str, **parameters):
        if endpoint == "list_data_types":
            assert parameters["category"] == ""
            rows = [f"{name} | {category} | {size} bytes | {path}" for name, category, size, path in self.types]
        else:
            assert endpoint == "list_data_type_categories", endpoint
            rows = list(self.categories)
        page = rows[parameters["offset"] : parameters["offset"] + parameters["limit"]]
        return "\n".join(page) if page else "No data types found"

    def post_json(self, endpoint: str, **body):
        self.posts.append((endpoint, body))
        assert endpoint == "run_script_inline"
        if self.script == "disabled":
            return {"error": "Script execution disabled. Set GHIDRA_MCP_ALLOW_SCRIPTS=1 ..."}
        hex_path, mode = body["args"].split()
        self.target = Path(bytes.fromhex(hex_path).decode("utf-8"))
        state = {"database_mod_count": 7, "modification_number": 3, "changed": False, "type_count": 5, "source_archives": []}
        result = {
            "ok": True,
            "written": True,
            "program": "/socom.elf",
            "mode": mode,
            "archive": self.target.name,
            "program_counts": dict(COUNTS),
            "program_categories": 2,
            "program_conflict_names": 0,
            "archive_warning": "NONE",
            "archive_architecture": {"language": "r5900:LE:32:default", "compiler_spec": "default"},
            "data_organization_equal": True,
            "pointer_size": 4,
            "universal_id": "3765755167656759572",
            "archive_categories": 2,
            "archive_counts": dict(COUNTS),
            "conflict_names": 0,
            "missing": 0,
            "extra": 0,
            "not_equivalent": 0,
            "program_state_before": state,
            "program_state_after": dict(state),
            "program_unchanged": True,
            "problems": [],
        }
        if self.script == "refuse":
            result.update(ok=False, written=False, problems=["socom-types.gdt exists; pass replace to overwrite it"])
        elif self.script == "counts":
            result["archive_counts"] = dict(COUNTS, total=6, pointer=2)
        elif self.script == "conflict":
            result["conflict_names"] = 1
        elif self.script == "program changed":
            result["program_state_after"] = dict(state, database_mod_count=8)
            result["program_unchanged"] = False
        elif self.script == "snapshot changed":
            self.types.append(("CNode.conflict", "project", "12", "/project/CNode.conflict"))
        if result["written"] and self.script != "no file":
            self.target.write_bytes(b"GDT archive bytes")
        line = type_archive.RESULT_MARK + json.dumps(result, separators=(",", ":"))
        if self.script == "silent":
            line = "nothing to see"
        return (
            "=== GHIDRA SCRIPT EXECUTION ===\nScript: ExportTypeArchive.java\nProgram: socom.elf\n"
            f"\n--- SCRIPT OUTPUT ---\nExportTypeArchive.java> {line}\n\n"
            "=== SCRIPT COMPLETED SUCCESSFULLY ===\n\n--- CONSOLE OUTPUT ---\n"
            f"INFO  ExportTypeArchive.java> {line} (GhidraScript)\n"
        )


def _workspace(tmp_path: Path, root: Path) -> Path:
    target = tmp_path / SCRIPT_PATH
    target.parent.mkdir(parents=True)
    shutil.copyfile(root / SCRIPT_PATH, target)
    (tmp_path / "support").mkdir()
    return tmp_path


def test_the_pinned_script_only_reads_the_program(root: Path) -> None:
    script = archive_script(root)
    assert script["sha256"] == SCRIPT_SHA256 and script["endpoint"] == "run_script_inline"
    code = "\n".join(line for line in script["source"].splitlines() if not line.lstrip().startswith("//"))
    # No association, renames, removals, replacements, analysis or program saves.
    for forbidden in (
        "associateDataTypeWithArchive", "setSourceArchive", "disassociate", "setName(", "remove(",
        "removeDataType", "replaceDataType", "replaceWith", "moveDataType", "updateSourceArchiveName",
        "analyze", "runScript", "clearFlow", "setBytes", "Bookmark", "save_program", "saveAs",
        "programTypes.add", "programTypes.resolve", "programTypes.create", "currentProgram.save",
        "getProjectData", "openProgram",
    ):
        assert forbidden not in code, forbidden
    for required in (
        "FileDataTypeManager.createFileArchive(staged, new LanguageID(LANGUAGE)",
        "archive.addDataTypes(types, DataTypeConflictHandler.DEFAULT_HANDLER, monitor)",
        "FileDataTypeManager.openFileArchive(staged, false)",
        "getDBHandle().getModCount()",
        "currentProgram.endTransaction(abort, false)",
    ):
        assert required in code, required
    # Only the archive is written or saved; startTransaction on the program only aborts.
    assert code.count("currentProgram.startTransaction") == 1
    assert [line.strip() for line in code.splitlines() if ".save()" in line] == ["archive.save();"]


def test_an_unpinned_script_is_refused(tmp_path: Path, root: Path) -> None:
    workspace = _workspace(tmp_path, root)
    script = workspace / SCRIPT_PATH
    script.write_bytes(script.read_bytes() + b"// edited\n")
    bridge = _Bridge()
    with pytest.raises(SocomError, match="not the reviewed"):
        export_type_archive(workspace, bridge, workspace / "support" / "socom-types.gdt")
    assert bridge.posts == []
    # CRLF checkouts hash as the LF text that is sent.
    script.write_bytes((root / SCRIPT_PATH).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert archive_script(workspace)["sha256"] == SCRIPT_SHA256


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("src/socom-types.gdt", "only be written under support/ or build/"),
        ("../socom-types.gdt", "only be written under support/ or build/"),
        ("support", "only be written under support/ or build/"),
        ("support/socom.elf", "not a .gdt file name"),
        ("build/types.gdt.txt", "not a .gdt file name"),
        ("support/.gdt", "not a .gdt file name"),
    ],
)
def test_outputs_outside_support_and_build_are_refused(tmp_path: Path, value: str, message: str) -> None:
    with pytest.raises(SocomError, match=message):
        resolve_output(tmp_path, value)


def test_existing_or_open_archives_are_refused(tmp_path: Path) -> None:
    output = resolve_output(tmp_path, "build/type-archive/socom-types.gdt")
    assert output == (tmp_path / "build" / "type-archive" / "socom-types.gdt").resolve()
    check_output(output, replace=False)  # absent, directory not yet made
    output.parent.mkdir(parents=True)
    output.write_bytes(b"old")
    with pytest.raises(SocomError, match="pass --replace"):
        check_output(output, replace=False)
    check_output(output, replace=True)
    (output.parent / "socom-types.gdt.ulock").write_bytes(b"")
    with pytest.raises(SocomError, match="lock files"):
        check_output(output, replace=True)
    folder = output.parent / "folder.gdt"
    folder.mkdir()
    with pytest.raises(SocomError, match="not a file"):
        check_output(folder, replace=True)


def test_a_dry_run_reads_the_snapshot_and_sends_nothing(tmp_path: Path, root: Path) -> None:
    workspace = _workspace(tmp_path, root)
    bridge = _Bridge()
    output = resolve_output(workspace, "support/socom-types.gdt")
    result = export_type_archive(workspace, cli._ReadOnlyBridge(bridge), output, dry_run=True)
    assert bridge.posts == [] and result["bridge_call_count"] == 0 and not output.exists()
    assert result["snapshot"]["type_count"] == 5 and result["snapshot"]["conflict_names"] == []
    assert result["source"].startswith("// soCOM governed export") and result["mode"] == "create"


def test_the_export_runs_the_pinned_script_once_and_hashes_the_file(tmp_path: Path, root: Path) -> None:
    workspace = _workspace(tmp_path, root)
    bridge = _Bridge()
    output = resolve_output(workspace, "support/socom-types.gdt")
    result = export_type_archive(workspace, bridge, output)
    [(endpoint, body)] = bridge.posts
    assert endpoint == "run_script_inline" and body["code"] == archive_script(workspace)["source"]
    assert bridge.target == output and body["args"].split()[1] == "create"
    assert result["archive"]["name"] == "socom-types.gdt" and result["archive"]["size"] == len(b"GDT archive bytes")
    assert len(result["archive"]["sha256"]) == 64 and result["archive"]["replaced_sha256"] is None
    assert result["script_result"]["archive_counts"] == COUNTS and set(COUNTS) == {"total", *KINDS}


@pytest.mark.parametrize(
    ("script", "ran", "message"),
    [
        ("disabled", False, "did not run the script"),
        ("refuse", True, "refused or failed"),
        ("silent", True, "no single result line"),
        ("counts", True, "archive counts .* differ"),
        ("conflict", True, "conflict_names is 1"),
        ("program changed", True, "saw the program change"),
        ("snapshot changed", True, "types changed"),
        ("no file", True, "does not exist after the script"),
    ],
)
def test_a_failed_or_inconsistent_export_is_reported(tmp_path: Path, root: Path, script: str, ran: bool, message: str) -> None:
    workspace = _workspace(tmp_path, root)
    bridge = _Bridge(script=script)
    with pytest.raises(TypeArchiveFailure, match=message) as failure:
        export_type_archive(workspace, bridge, resolve_output(workspace, "support/socom-types.gdt"))
    assert failure.value.ran is ran and len(bridge.posts) == 1


def test_a_program_with_conflict_types_is_refused_before_the_script(tmp_path: Path, root: Path) -> None:
    workspace = _workspace(tmp_path, root)
    bridge = _Bridge()
    bridge.types.append(("CNode.conflict", "project", "12", "/project/CNode.conflict"))
    with pytest.raises(TypeArchiveFailure, match="has .conflict types") as failure:
        export_type_archive(workspace, bridge, resolve_output(workspace, "support/socom-types.gdt"))
    assert failure.value.ran is False and bridge.posts == []


def test_result_lines_must_agree() -> None:
    line = type_archive.RESULT_MARK + '{"ok":true}'
    assert parse_result(f"x\n{line}\n{line} (GhidraScript)\n") == {"ok": True}
    with pytest.raises(TypeArchiveFailure, match="no single result line"):
        parse_result(f"{line}\n{type_archive.RESULT_MARK}" + '{"ok":false}\n')
    with pytest.raises(TypeArchiveFailure, match="unreadable"):
        parse_result(type_archive.RESULT_MARK + "{not json}\n")
    with pytest.raises(TypeArchiveFailure, match="did not run") as failure:
        parse_result({"error": "x"})
    assert failure.value.ran is False


def _cli(tmp_path: Path, root: Path, monkeypatch, bridge: _Bridge, items: list[dict] | None = None):
    workspace = _workspace(tmp_path, root)
    monkeypatch.setattr(cli, "load_tracker", lambda _path: {"work_items": items or []})
    preflight = {"ok": True, "errors": [], "source_sha256": "00c9" + "0" * 60}
    monkeypatch.setattr(cli, "live_preflight", lambda *_args, **_kwargs: preflight)
    monkeypatch.setattr(cli, "GhidraBridge", lambda *_args, **_kwargs: bridge)

    def arguments(output: str = "support/socom-types.gdt", *, dry_run: bool = False, replace: bool = False):
        return argparse.Namespace(
            root=str(workspace),
            output=output,
            replace=replace,
            report_output="build/type-archive/report.json",
            dry_run=dry_run,
            bridge_url=None,
        )

    return workspace, arguments


def test_cli_dry_run_then_export_writes_the_record(tmp_path: Path, root: Path, monkeypatch, capsys) -> None:
    bridge = _Bridge()
    workspace, arguments = _cli(tmp_path, root, monkeypatch, bridge)
    assert cli._ghidra_type_archive(arguments(dry_run=True)) == 0
    captured = capsys.readouterr()
    assert SCRIPT_SHA256 in captured.err and "public class ExportTypeArchive" in captured.err
    assert json.loads(captured.out)["dry_run"] is True and bridge.posts == []
    assert not (workspace / RECORD_PATH).exists() and not (workspace / "support" / "socom-types.gdt").exists()

    assert cli._ghidra_type_archive(arguments()) == 0
    record_text = (workspace / RECORD_PATH).read_text(encoding="utf-8")
    record = json.loads(record_text)
    assert record["archive"] == "socom-types.gdt" and record["type_counts"] == COUNTS
    assert record["script"] == {"path": SCRIPT_PATH, "sha256": SCRIPT_SHA256}
    assert record["ghidra_version"] == "12.1.4" and record["program"]["language"] == "r5900:LE:32:default"
    assert record["size"] == len(b"GDT archive bytes") and record["user_decision"] == "2026-11-25"
    # Name only: no directory of this checkout anywhere in the tracked record.
    for form in (str(workspace), workspace.as_posix(), str(workspace.resolve())):
        assert form not in record_text
    assert "/" not in record["archive"] and "\\" not in record["archive"]

    # A second create is refused before the script; --replace overwrites.
    capsys.readouterr()
    assert cli._ghidra_type_archive(arguments()) == 1
    refused = json.loads(capsys.readouterr().out)
    assert "pass --replace" in refused["error"] and refused["script_may_have_run"] is False
    assert len(bridge.posts) == 1
    assert cli._ghidra_type_archive(arguments(replace=True)) == 0
    report = json.loads((workspace / "build/type-archive/report.json").read_text(encoding="utf-8"))
    assert report["ok"] is True and report["archive"]["replaced_sha256"] == record["sha256"]
    assert bridge.posts[-1][1]["args"].endswith(" replace")


def test_cli_build_trial_writes_no_record_and_failures_say_what_ran(tmp_path: Path, root: Path, monkeypatch, capsys) -> None:
    bridge = _Bridge()
    workspace, arguments = _cli(tmp_path, root, monkeypatch, bridge)
    assert cli._ghidra_type_archive(arguments("build/type-archive/trial.gdt")) == 0
    assert (workspace / "build/type-archive/trial.gdt").is_file() and not (workspace / RECORD_PATH).exists()
    capsys.readouterr()
    bridge.script = "counts"
    assert cli._ghidra_type_archive(arguments("build/type-archive/second.gdt")) == 1
    report = json.loads((workspace / "build/type-archive/report.json").read_text(encoding="utf-8"))
    assert report["ok"] is False and report["script_may_have_run"] is True and "script_response" in report
    assert "script_response" not in json.loads(capsys.readouterr().out)


def test_cli_refuses_while_a_writer_lease_is_held(tmp_path: Path, root: Path, monkeypatch) -> None:
    bridge = _Bridge()
    writer = {"id": "socom:work:x-apply", "status": "in_progress", "resources": ["ghidra:soCOM/socom.elf", "ghidra-writer"]}
    _workspace_root, arguments = _cli(tmp_path, root, monkeypatch, bridge, items=[writer])
    with pytest.raises(SocomError, match="writer lease is held by"):
        cli._ghidra_type_archive(arguments())
    assert bridge.posts == []


def test_the_command_is_registered_read_only_for_ghidra() -> None:
    row = next(row for row in cli._command_rows() if row["command"] == "ghidra type-archive")
    assert row["mutates"] is True and row["mutates_ghidra"] is False and row["ghidra_requirement"] == "required"
