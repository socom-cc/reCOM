"""The one-time governed repair of the ten split function boundaries (bridge mocked)."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
from pathlib import Path

import pytest

from tools._socom import boundary_repair, cli
from tools._socom.boundary_repair import BoundaryFailure, boundary_script, check_reference, repair_boundaries
from tools._socom.repairs import READABLE_NAMES_REPAIR_ID, REPAIRS, SPLIT_BOUNDARIES_REPAIR_ID
from tools._socom.util import SocomError

SPEC = REPAIRS[SPLIT_BOUNDARIES_REPAIR_ID]
STARTS = [function["address"] for function in SPEC["functions"]]
UIVAR = "0x39e3f0"


def _extent(function: dict) -> tuple[int, int, int]:
    return int(function["address"], 16), int(function["wrong"]["thunk_target"], 16), int(function["end"], 16)


class _LiveBridge:
    """The live program as far as the repair reads it, and the script's effect on it."""

    def __init__(self, script: str = "apply", idle_after: int = 2) -> None:
        self.functions: dict[int, dict] = {
            0x140010: {"name": "entry", "thunk": False, "body": (0x140010, 0x14004F), "signature": "void entry(void)"}
        }
        for function in SPEC["functions"]:
            start, split, end = _extent(function)
            wrong = function["wrong"]
            self.functions[start] = {"name": function["name"], "thunk": True, "body": (start, split - 1), "signature": wrong["signature"]}
            self.functions[split] = {
                "name": wrong["split_name"],
                "thunk": False,
                "body": (split, end - 1),
                "signature": wrong["split_signature"],
            }
        self.script = script
        self.idle_after = idle_after
        self.polls = 0
        self.posts: list[tuple[str, dict]] = []

    def request(self, endpoint: str, **parameters):
        if endpoint == "list_functions_enhanced":
            return {
                "functions": [
                    {"address": f"{address:08x}", "name": row["name"], "isThunk": row["thunk"], "isExternal": False}
                    for address, row in sorted(self.functions.items())
                ]
            }
        if endpoint == "get_function_count":
            return {"function_count": len(self.functions), "program": "socom.elf"}
        if endpoint == "analysis_status":
            self.polls += 1
            return {"name": "socom.elf", "analyzing": self.polls < self.idle_after}
        assert endpoint == "get_function_by_address", endpoint
        address = int(parameters["address"], 16)
        for entry, row in self.functions.items():
            if row["body"][0] <= address <= row["body"][1]:
                return "\n".join(
                    [
                        f"Function: {row['name']} at {entry:08x}",
                        f"Signature: {row['signature']}",
                        f"Entry: {entry:08x}",
                        f"Body: {row['body'][0]:08x} - {row['body'][1]:08x}",
                    ]
                )
        return f"No function found at address {parameters['address']}"

    def post_json(self, endpoint: str, **body):
        self.posts.append((endpoint, body))
        assert endpoint == "run_script_inline"
        if self.script == "disabled":
            return {"error": "Script execution disabled. Set GHIDRA_MCP_ALLOW_SCRIPTS=1 ..."}
        before = len(self.functions)
        triples = [tuple(int(value, 16) for value in argument.split(":")) for argument in body["args"].split()]
        problems: list[str] = []
        if self.script == "refuse":
            problems = ["0x193cd0: not a thunk of 0x193cdc"]
        else:
            for start, split, end in triples:
                if not (self.script == "partial" and start == triples[-1][0]):
                    del self.functions[split]
                    row = self.functions[start]
                    # An entry's own record: Ghidra kept the prototype on the target.
                    row.update(thunk=False, body=(start, end - 1), signature=f"undefined {row['name']}(void)")
        ok = not problems
        result = {
            "ok": ok,
            "changed": ok,
            "program": "/socom.elf",
            "function_count_before": before,
            "function_count_after": before - len(triples) if ok else None,
            "functions": [
                {"entry": f"0x{start:x}", "split": f"0x{split:x}", "end": f"0x{end:x}", "name": self.functions[start]["name"]}
                for start, split, end in triples
            ],
            "problems": problems,
        }
        line = boundary_repair.RESULT_MARK + json.dumps(result, separators=(",", ":"))
        if self.script == "silent":
            line = "nothing to see"
        return (
            "=== GHIDRA SCRIPT EXECUTION ===\nScript: RepairSplitBoundaries.java\nProgram: socom.elf\n"
            f"\n--- SCRIPT OUTPUT ---\nRepairSplitBoundaries.java> {line}\n\n"
            "=== SCRIPT COMPLETED SUCCESSFULLY ===\n\n--- CONSOLE OUTPUT ---\n"
            f"INFO  RepairSplitBoundaries.java> {line} (GhidraScript)\n"
        )


def test_spec_matches_the_reference_and_the_pinned_script(root: Path) -> None:
    check_reference(root, SPEC)
    script = boundary_script(root, SPEC)
    assert script["sha256"] == SPEC["script_sha256"]
    assert script["endpoint"] == "run_script_inline"
    assert len(SPEC["functions"]) == 10 and STARTS == sorted(STARTS, key=lambda value: int(value, 16))
    assert script["arguments"].split()[0] == "0x193cd0:0x193cdc:0x193d40"
    assert SPEC["stage"] == "ghidra-reconstruction" and SPEC["dependencies"][-1] == READABLE_NAMES_REPAIR_ID
    # The pinned text: Java the bridge compiles as RepairSplitBoundaries.java,
    # touching functions only (no flow, bytes, disassembly, analysis or saves).
    code = "\n".join(line for line in script["source"].splitlines() if not line.lstrip().startswith("//"))
    for forbidden in (
        "clearFlow", "ClearFlow", "setByte", "Disassemble", "disassemble", "analyze", "Analysis",
        "createFunction", "CreateFunction", "save", "runScript", "setFlowOverride", "Bookmark",
    ):
        assert forbidden not in code, forbidden
    assert "setThunkedFunction(null)" in code and "removeFunction" in code and "setBody" in code


def test_dependencies_are_the_groups_whose_scope_holds_an_entry(root: Path) -> None:
    from tools._socom.recon import recon_groups

    groups = recon_groups(root)["groups"]
    covering = {
        f"{group['id']}-apply" for group in groups if any(address in group["functions"] for address in STARTS)
    }
    assert covering == set(SPEC["dependencies"]) - {READABLE_NAMES_REPAIR_ID}


def test_dry_run_checks_everything_and_runs_nothing(root: Path) -> None:
    bridge = _LiveBridge()
    result = repair_boundaries(root, SPLIT_BOUNDARIES_REPAIR_ID, bridge, dry_run=True)
    assert bridge.posts == [] and result["bridge_call_count"] == 0
    assert result["script"]["sha256"] == SPEC["script_sha256"]
    assert result["source"].startswith("// soCOM governed repair")
    assert result["function_count_before"] == 21 and len(result["functions"]) == 10
    assert result["functions"][-1]["before"]["split_signature"].startswith("UIVarMixin * * __stdcall FUN_0039e3fc(")


def test_repair_runs_the_pinned_script_once_and_reads_every_function_back(root: Path) -> None:
    bridge = _LiveBridge()
    result = repair_boundaries(root, SPLIT_BOUNDARIES_REPAIR_ID, bridge, sleep=lambda _seconds: None)
    [(endpoint, body)] = bridge.posts
    assert endpoint == "run_script_inline"
    assert body["code"] == boundary_script(root, SPEC)["source"] and body["args"] == boundary_script(root, SPEC)["arguments"]
    assert result["function_count_before"] == 21 and result["function_count_after"] == 11
    assert result["analysis_wait_seconds"] == 1.0 and result["bridge_call_count"] == 1
    assert result["receipt_scope"] == {"schema_version": 1, "functions": STARTS, "types": [], "globals": []}
    first = result["functions"][0]
    assert first["after"] == {"thunk": False, "body": ["0x193cd0", "0x193d3f"], "signature": first["before"]["signature"]}
    assert first["lost"] == {"signature": None, "split_signature": "undefined FUN_00193cdc(void)"}
    # g076's prototype sat on FUN_0039e3fc: recorded, not restored.
    assert result["lost_signatures"] == {UIVAR: SPEC["functions"][-1]["wrong"]["signature"]}
    assert len(result["removed_functions"]) == 10


@pytest.mark.parametrize(
    "damage",
    ["rejoined", "extra function", "signature", "split name"],
)
def test_repair_refuses_any_other_starting_state(root: Path, damage: str) -> None:
    bridge = _LiveBridge()
    if damage == "rejoined":
        del bridge.functions[0x39E3FC]
        bridge.functions[0x39E3F0].update(thunk=False, body=(0x39E3F0, 0x39E41F))
    elif damage == "extra function":
        bridge.functions[0x193CE0] = {"name": "FUN_00193ce0", "thunk": False, "body": (0x193CE0, 0x193CE3), "signature": "x"}
        bridge.functions[0x193CDC]["body"] = (0x193CDC, 0x193CDF)
    elif damage == "signature":
        bridge.functions[0x1F01F0]["signature"] = "CTarget * * __stdcall std::find<CTarget*,CEntity*>(void)"
    else:
        bridge.functions[0x2FB5BC]["name"] = "std::find_body"
    with pytest.raises(BoundaryFailure, match="not in the recorded wrong state") as failure:
        repair_boundaries(root, SPLIT_BOUNDARIES_REPAIR_ID, bridge)
    assert failure.value.wrote is False and bridge.posts == []


def test_repair_refuses_an_unpinned_script(tmp_path: Path, root: Path) -> None:
    script = tmp_path / SPEC["script"]
    script.parent.mkdir(parents=True)
    script.write_bytes((root / SPEC["script"]).read_bytes() + b"// edited\n")
    bridge = _LiveBridge()
    with pytest.raises(SocomError, match="not the reviewed"):
        repair_boundaries(tmp_path, SPLIT_BOUNDARIES_REPAIR_ID, bridge)
    assert bridge.posts == []
    # CRLF checkouts hash as the LF text that is sent.
    script.write_bytes((root / SPEC["script"]).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert boundary_script(tmp_path, SPEC)["sha256"] == SPEC["script_sha256"]
    with pytest.raises(SocomError, match="not a boundary repair"):
        repair_boundaries(root, READABLE_NAMES_REPAIR_ID, bridge)


@pytest.mark.parametrize(
    ("script", "wrote", "message"),
    [
        ("disabled", False, "did not run the script"),
        ("refuse", False, "nothing changed"),
        ("silent", True, "no single result line"),
        ("partial", True, "does not match the spec|read-back differs"),
    ],
)
def test_a_failed_script_or_read_back_is_reported(root: Path, script: str, wrote: bool, message: str) -> None:
    bridge = _LiveBridge(script=script)
    with pytest.raises(BoundaryFailure, match=message) as failure:
        repair_boundaries(root, SPLIT_BOUNDARIES_REPAIR_ID, bridge, sleep=lambda _seconds: None)
    assert failure.value.wrote is wrote and len(bridge.posts) == 1


def _cli_root(tmp_path: Path, root: Path) -> Path:
    for relative in (SPEC["script"], "support/socom.elf"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    return tmp_path


def test_cli_dry_run_prints_the_script_and_writes_no_scope(tmp_path: Path, root: Path, monkeypatch, capsys) -> None:
    workspace = _cli_root(tmp_path, root)
    bridge = _LiveBridge(idle_after=1)
    item = {"id": SPLIT_BOUNDARIES_REPAIR_ID, "kind": "ghidra-repair"}
    monkeypatch.setattr(cli, "load_tracker", lambda _path: {"work_items": [item]})
    monkeypatch.setattr(cli, "require_ghidra_lease", lambda _tracker, item_id, owner: item)
    monkeypatch.setattr(cli, "live_preflight", lambda *_args, **_kwargs: {"ok": True, "errors": []})
    monkeypatch.setattr(cli, "GhidraBridge", lambda *_args, **_kwargs: bridge)

    def arguments(dry_run: bool) -> argparse.Namespace:
        return argparse.Namespace(
            root=str(workspace),
            item=SPLIT_BOUNDARIES_REPAIR_ID,
            owner="writer",
            scope_output="build/receipts/boundaries-scope.json",
            report_output="build/apply/boundaries-report.json",
            dry_run=dry_run,
            bridge_url=None,
        )

    assert cli._ghidra_repair_boundaries(arguments(True)) == 0
    captured = capsys.readouterr()
    assert SPEC["script_sha256"] in captured.err and "public class RepairSplitBoundaries" in captured.err
    assert json.loads(captured.out)["dry_run"] is True and bridge.posts == []
    assert not (workspace / "build/receipts/boundaries-scope.json").exists()

    assert cli._ghidra_repair_boundaries(arguments(False)) == 0
    scope = json.loads((workspace / "build/receipts/boundaries-scope.json").read_text(encoding="utf-8"))
    assert scope["functions"] == STARTS and len(bridge.posts) == 1
    report = json.loads((workspace / "build/apply/boundaries-report.json").read_text(encoding="utf-8"))
    assert report["ok"] is True and report["function_count_after"] == 11
    assert report["lost_signatures"] == {UIVAR: SPEC["functions"][-1]["wrong"]["signature"]}

    # A second run finds the target state, not the wrong one, and writes nothing.
    assert cli._ghidra_repair_boundaries(arguments(False)) == 1
    report = json.loads((workspace / "build/apply/boundaries-report.json").read_text(encoding="utf-8"))
    assert report["ok"] is False and report["script_may_have_run"] is False and len(bridge.posts) == 1


def test_boundary_repair_joins_the_stage_gate_once_its_applies_are_accepted(stage2_tracker: dict, root: Path) -> None:
    from tools._socom.recon import recon_groups
    from tools._socom.tracker import (
        RECON_SEED_ID,
        add_repair_item,
        audit_tracker,
        claim_work,
        decompose_reconstruction,
        record_stage_baseline,
        refresh_ready_and_stages,
        work_packet,
    )

    tracker = copy.deepcopy(stage2_tracker)
    record_stage_baseline(
        tracker, "debug-metadata-import", "reviewer", ["close-out.md"], receipt_sha256="9" * 64,
        receipt={"counts": {}, "indexes": {}},
    )
    decompose_reconstruction(tracker, recon_groups(root))
    add_repair_item(tracker, READABLE_NAMES_REPAIR_ID)
    with pytest.raises(SocomError, match="not accepted"):
        add_repair_item(tracker, SPLIT_BOUNDARIES_REPAIR_ID)
    for row in tracker["work_items"]:
        if row["id"] in SPEC["dependencies"]:
            row["status"] = "accepted"
    add_repair_item(tracker, SPLIT_BOUNDARIES_REPAIR_ID)
    gate = next(row for row in tracker["work_items"] if row["id"] == RECON_SEED_ID)
    assert gate["dependencies"][-1] == SPLIT_BOUNDARIES_REPAIR_ID
    refresh_ready_and_stages(tracker)
    repair = next(row for row in tracker["work_items"] if row["id"] == SPLIT_BOUNDARIES_REPAIR_ID)
    assert repair["kind"] == "ghidra-repair" and repair["status"] == "ready"
    assert repair["resources"] == ["ghidra:soCOM/socom.elf", "ghidra-writer"]
    assert [error for error in audit_tracker(tracker) if SPLIT_BOUNDARIES_REPAIR_ID in error] == []
    claim_work(tracker, SPLIT_BOUNDARIES_REPAIR_ID, "writer", 30)
    packet = work_packet(tracker, SPLIT_BOUNDARIES_REPAIR_ID, "writer")
    assert any("ghidra repair-boundaries" in line for line in packet["validation"])
