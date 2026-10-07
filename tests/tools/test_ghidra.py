from __future__ import annotations

import collections
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from tools._socom import ghidra
from tools._socom.util import SocomError


def test_bridge_supplies_explicit_program(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({"ok": True}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(ghidra, "urlopen", fake_urlopen)
    bridge = ghidra.GhidraBridge("http://127.0.0.1:8089", timeout=7)
    assert bridge.request("get_metadata") == {"ok": True}
    assert parse_qs(urlparse(captured["url"]).query)["program"] == ["socom.elf"]
    assert captured["timeout"] == 7


def _preflight_bridge(executable_sha256: str | None):
    # Any import location other than this checkout's support/socom.elf.
    foreign_import = "/srv/other-checkout/support/socom.elf"

    class FakeBridge:
        def __init__(self, *_args, **_kwargs):
            pass

        def schema(self):
            return {"tools": []}

        def project_files(self):
            return {
                "project_name": "soCOM",
                "files": [
                    {
                        "name": "socom.elf",
                        "path": "/socom.elf",
                        "content_type": "Program",
                    }
                ],
            }

        def request(self, endpoint, **parameters):
            if endpoint == "list_open_programs":
                return {"programs": [{"name": "socom.elf", "path": "/socom.elf"}]}
            if endpoint == "get_current_program_info":
                return {
                    "name": "socom.elf",
                    "path": "/socom.elf",
                    "executable_path": foreign_import,
                    "language": ghidra.EXPECTED_LANGUAGE,
                    "compiler": ghidra.EXPECTED_COMPILER,
                    "address_size": ghidra.EXPECTED_ADDRESS_SIZE,
                    "image_base": ghidra.EXPECTED_IMAGE_BASE,
                }
            if endpoint == "get_program_options":
                assert parameters == {"group": "Program Information"}
                options = [{"name": "Executable Location", "value": foreign_import}]
                if executable_sha256 is not None:
                    options.append(
                        {"name": "Executable SHA256", "value": executable_sha256}
                    )
                return {"group": "Program Information", "options": options}
            if endpoint == "analysis_status":
                return {"analyzed": True, "analyzing": False}
            if endpoint == "get_entry_points":
                return "ENTRYPOINT @ 00140010 [Label] [external entry]\n"
            if endpoint == "list_bookmarks":
                return {"bookmarks": []}
            if endpoint == "disassemble_function":
                return "".join(
                    f"{0x140D00 + 4 * index:08x}: {instruction}\n"
                    for index, instruction in enumerate(ghidra.EXPECTED_SENTINEL)
                )
            raise AssertionError(endpoint)

    return FakeBridge


def test_preflight_identifies_program_by_hash_not_import_path(
    monkeypatch, root: Path
) -> None:
    monkeypatch.setattr(
        ghidra, "GhidraBridge", _preflight_bridge(ghidra.REFERENCE_SHA256)
    )
    monkeypatch.setattr(
        ghidra, "_local_profile_versions", lambda: [ghidra.EXPECTED_GHIDRA_VERSION]
    )
    report = ghidra.live_preflight(root, strict_baseline=False)
    assert report["errors"] == []
    assert report["ok"] is True
    assert report["program_executable_sha256"] == ghidra.REFERENCE_SHA256


@pytest.mark.parametrize("executable_sha256", [None, "0" * 64])
def test_preflight_rejects_missing_or_foreign_executable_hash(
    monkeypatch, root: Path, executable_sha256: str | None
) -> None:
    monkeypatch.setattr(ghidra, "GhidraBridge", _preflight_bridge(executable_sha256))
    monkeypatch.setattr(
        ghidra, "_local_profile_versions", lambda: [ghidra.EXPECTED_GHIDRA_VERSION]
    )
    report = ghidra.live_preflight(root, strict_baseline=False)
    assert report["ok"] is False
    assert report["errors"] == [
        f"program executable SHA-256 is {executable_sha256!r}, "
        f"expected {ghidra.REFERENCE_SHA256}"
    ]


def test_receipt_scope_is_canonical_and_rejects_unknown_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "scope.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "functions": ["0x00140d00", "0x140d00"],
                "types": ["/project/CGame", "/project/CGame"],
                "globals": ["0x00476fe8"],
            }
        ),
        encoding="utf-8",
    )
    assert ghidra.load_receipt_scope(path) == {
        "functions": ["0x140d00"],
        "types": ["/project/CGame"],
        "globals": ["0x476fe8"],
    }

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "functions": [],
                "types": [],
                "globals": [],
                "host_project_path": "forbidden",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SocomError, match="unknown fields"):
        ghidra.load_receipt_scope(path)


def test_receipt_scope_order_is_independent_of_input_and_case_ties(
    tmp_path: Path,
) -> None:
    path = tmp_path / "scope.json"
    orders = []
    for types in (
        ["/project/line_data", "/project/LINE_DATA", "/project/CGame"],
        ["/project/LINE_DATA", "/project/CGame", "/project/line_data"],
    ):
        path.write_text(
            json.dumps(
                {"schema_version": 1, "functions": [], "types": types, "globals": []}
            ),
            encoding="utf-8",
        )
        orders.append(ghidra.load_receipt_scope(path)["types"])
    assert orders[0] == orders[1] == [
        "/project/CGame",
        "/project/LINE_DATA",
        "/project/line_data",
    ]


def test_receipt_scope_rejects_empty_scope(tmp_path: Path) -> None:
    path = tmp_path / "scope.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "functions": [],
                "types": [],
                "globals": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        SocomError,
        match="must name at least one function, type, or global",
    ):
        ghidra.load_receipt_scope(path)


def test_semantic_receipt_is_deterministic_and_scoped(
    monkeypatch, root: Path
) -> None:
    preflight = {
        "ok": True,
        "errors": [],
        "analysis": {"analyzed": True, "analyzing": False},
        "counts": {
            "function_count": 1,
            "symbol_count": 2,
            "data_type_count": 1,
            "memory_block_count": 1,
        },
        "bookmark_profile": {
            "count": 0,
            "by_type": {},
            "by_category": {},
            "error_or_warning_count": 0,
        },
        "sentinel": [],
    }
    functions = [{"address": "00140d00", "name": "main"}]
    types = [
        {
            "name": "CGame",
            "category": "project",
            "size": 16,
            "path": "/project/CGame",
        }
    ]
    data = [
        {
            "address": "00476fe8",
            "name": "g_game",
            "type": "CGame *",
            "size": 4,
        }
    ]

    class FakeBridge:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, endpoint, **_parameters):
            if endpoint == "disassemble_function":
                return "00140d00: addiu sp,sp,-0x30\n"
            if endpoint == "get_function_by_address":
                return "Function: main at 00140d00\n"
            if endpoint == "audit_global":
                return {
                    "address": "00476fe8",
                    "name": "g_game",
                    "type": "CGame *",
                    "length": 4,
                    "plate_comment": "accepted fact",
                    "xref_count": 3,
                    "issues": ["not-authority"],
                    "fully_documented": False,
                }
            if endpoint == "get_struct_layout":
                return (
                    "Structure: CGame\nSize: 16 bytes\nAlignment: 1\n\nLayout:\n"
                    "Offset | Size | Type | Name\n-------|------|------|-----\n"
                    "     0 |    4 | int                  | m_state\n"
                )
            raise AssertionError(endpoint)

    monkeypatch.setattr(ghidra, "live_preflight", lambda *_args, **_kwargs: preflight)
    monkeypatch.setattr(ghidra, "GhidraBridge", FakeBridge)
    monkeypatch.setattr(ghidra, "_function_index", lambda _bridge: functions)
    monkeypatch.setattr(ghidra, "_type_index", lambda _bridge: types)
    monkeypatch.setattr(ghidra, "_data_index", lambda _bridge: data)

    scope = {
        "functions": ["0x140d00"],
        "types": ["/project/CGame"],
        "globals": ["0x476fe8"],
    }
    first = ghidra.semantic_receipt(root, scope=scope)
    second = ghidra.semantic_receipt(root, scope=scope)
    assert first == second
    assert first["receipt"]["scoped_facts"]["functions"][0]["name"] == "main"
    assert first["receipt"]["scoped_facts"]["types"][0]["path"] == "/project/CGame"
    # Scoped types bind their component layout, not only name and size.
    assert first["receipt"]["scoped_facts"]["types"][0]["layout"] == {
        "size": 16,
        "components": [[0, 4, "int", "m_state"]],
    }
    assert first["receipt"]["scoped_facts"]["globals"][0]["name"] == "g_game"
    assert set(first["receipt"]["scoped_facts"]["globals"][0]) == {
        "address",
        "name",
        "type",
        "length",
        "comment",
        "xref_count",
    }


def _zero_fill_bridge(*, mapped: bool = False, drift: bool = False, block: str = "main.bss", live=None):
    """A bridge with a real reference store; live is a set of (from, to, type)."""

    calls = []
    segments = "main: 00100000 - 004755ff\nheap: 005e7f00 - 005e7f03\n"

    class FakeBridge:
        def __init__(self, *_args, **_kwargs):
            self.created = mapped
            self.refs = set(live or ())

        def request(self, endpoint, **parameters):
            calls.append((endpoint, parameters))
            if endpoint == "list_segments":
                extra = f"{block}: 00475600 - 005e7eff\n" if self.created else ""
                return segments + extra
            if endpoint == "get_current_program_info":
                return {"function_count": 2, "symbol_count": 1, "data_type_count": 1, "memory_block_count": 27 + self.created}
            if endpoint == "read_memory":
                return {"error": "Unable to read bytes"}
            if endpoint == "list_functions":
                return "main at 00140d00\n"
            if endpoint == "list_bookmarks":
                return {"bookmarks": [{"type": "Analysis", "category": "Address Table"}]}
            raise AssertionError(endpoint)

        def paged_text(self, endpoint, **_parameters):
            assert endpoint == "list_data_items"
            rows = ["gopt @ 00438750 [undefined1] (1 bytes)"]
            if drift and self.refs:
                # An analyzer-style change outside the zero fill.
                rows.append("@3845 @ 00449bf0 [pointer] (4 bytes)")
            return rows

        def post_json(self, endpoint, **body):
            if endpoint != "get_bulk_xrefs":
                calls.append((endpoint, body))
            if endpoint == "create_memory_block":
                self.created = True
                return {"success": True, "start": "00475600", "end": "005e7eff"}
            if endpoint == "add_memory_reference":
                self.refs.add((int(body["from_address"], 16), int(body["to_address"], 16), body["ref_type"]))
                return {"status": "success"}
            if endpoint == "remove_reference":
                key = (int(body["from_address"], 16), int(body["to_address"], 16))
                self.refs = {ref for ref in self.refs if ref[:2] != key}
                return {"status": "success", "removed": 1}
            if endpoint == "get_bulk_xrefs":
                wanted = body["addresses"].split(",")
                by_target = {}
                for source, target, kind in self.refs:
                    by_target.setdefault(target, []).append({"from": f"{source:08x}", "type": kind})
                return {address: by_target.get(int(address, 16), []) for address in wanted}
            raise AssertionError(endpoint)

    return FakeBridge, calls


def test_relocation_references_cover_only_proven_zero_fill_targets(root: Path) -> None:
    references = ghidra.relocation_references(root, ghidra.zero_fill_ranges(root))
    kinds = collections.Counter(row["relocation"] for row in references)
    assert kinds == {"R_MIPS_LO16": 10542, "R_MIPS_GPREL16": 5727, "R_MIPS_32": 64}
    assert all(0x475600 <= row["to"] < 0x5E7F00 for row in references)
    # main loads theGame through a lui/addiu pair completed at 0x140db0.
    assert {"from": 0x140DB0, "to": 0x476F60, "ref_type": "DATA", "operand_index": 2, "relocation": "R_MIPS_LO16"} in references
    targets = {row["from"]: row["to"] for row in references}
    # HI16s of the .bss section symbol interleave across functions; dataflow
    # pairs SendPendingMessages' lw with s4 = lui 0x59, not the latest HI16.
    assert targets[0x411DAC] == targets[0x411DB4] == 0x58A268
    assert targets[0x412C7C] == 0x58A25C
    # crt0's _start has no sized function symbol.
    assert targets[0x1401B8] == 0x476D80


def test_zero_fill_mapping_adds_relocation_references_without_analysis(
    monkeypatch, root: Path
) -> None:
    bridge, calls = _zero_fill_bridge()
    monkeypatch.setattr(ghidra, "GhidraBridge", bridge)
    monkeypatch.setattr(ghidra, "live_preflight", lambda *_args, **_kwargs: {"ok": True, "errors": []})
    report = ghidra.map_zero_fill(root)
    create = next(body for endpoint, body in calls if endpoint == "create_memory_block")
    # PT_LOAD 0: file bytes end at 0x475600, memory at 0x5e7f00, flags RWX.
    assert create["name"] == "main.bss"
    assert create["address"] == "0x475600" and create["size"] == 0x172900
    assert (create["read"], create["write"], create["execute"]) == (True, True, True)
    endpoints = {endpoint for endpoint, _ in calls}
    assert not endpoints & {"run_analysis", "reanalyze"}
    added = [body for endpoint, body in calls if endpoint == "add_memory_reference"]
    assert len(added) == report["reference_count"] == 16333
    assert {"from_address": "0x140db0", "to_address": "0x476f60", "ref_type": "DATA", "source_type": "IMPORTED", "operand_index": 2} in added
    assert report["blocks"][0]["end"] == "0x5e7eff"
    assert "0x476f60" in report["receipt_scope"]["globals"]  # theGame
    assert all(0x475600 <= int(value, 16) < 0x5E7F00 for value in report["receipt_scope"]["globals"])


def test_zero_fill_mapping_refuses_overlap_and_outside_changes(
    monkeypatch, root: Path
) -> None:
    monkeypatch.setattr(ghidra, "live_preflight", lambda *_args, **_kwargs: {"ok": True, "errors": []})
    bridge, _calls = _zero_fill_bridge(mapped=True, block="bss")
    monkeypatch.setattr(ghidra, "GhidraBridge", bridge)
    with pytest.raises(SocomError, match="overlaps blocks"):
        ghidra.map_zero_fill(root)
    bridge, _calls = _zero_fill_bridge(drift=True)
    monkeypatch.setattr(ghidra, "GhidraBridge", bridge)
    with pytest.raises(SocomError, match="data outside the zero fill changed"):
        ghidra.map_zero_fill(root)


def test_zero_fill_mapping_reconciles_an_existing_block(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(ghidra, "live_preflight", lambda *_args, **_kwargs: {"ok": True, "errors": []})
    references = ghidra.relocation_references(root, ghidra.zero_fill_ranges(root))
    live = {(row["from"], row["to"], row["ref_type"]) for row in references}
    live.discard((0x411DAC, 0x58A268, "READ"))
    live.add((0x411DAC, 0x5AA268, "READ"))  # the wrong pairing a previous run saved
    live.add((0x15FB74, 0x47AE80, "PARAM"))  # analysis noise without a relocation
    live.add((0x412C7C, 0x58A25C, "PARAM"))  # a second reference on a proven pair
    bridge, calls = _zero_fill_bridge(mapped=True, live=live)
    monkeypatch.setattr(ghidra, "GhidraBridge", bridge)
    report = ghidra.map_zero_fill(root)
    assert report["mode"] == "reconcile"
    assert {(row["from"], row["to"]) for row in report["removed_references"]} == {
        ("0x15fb74", "0x47ae80"),
        ("0x411dac", "0x5aa268"),
        ("0x412c7c", "0x58a25c"),
    }
    assert report["reconciled_additions"] == [
        {"from": "0x411dac", "to": "0x58a268"},
        {"from": "0x412c7c", "to": "0x58a25c"},
    ]
    assert not any(endpoint == "create_memory_block" for endpoint, _ in calls)


def test_zero_fill_sweep_requires_every_address_answered() -> None:
    class Partial:
        def post_json(self, endpoint, **body):
            assert endpoint == "get_bulk_xrefs"
            return {address: [] for address in body["addresses"].split(",")[1:]}

    with pytest.raises(SocomError, match="did not answer every address"):
        ghidra.zero_fill_references_live(Partial(), [{"start": 0x475600, "size": 8}])


def test_strict_preflight_defers_bootstrap_counts_to_tracker(monkeypatch, root: Path) -> None:
    import argparse

    from tools._socom import cli

    seen = []

    def fake(_root, **kwargs):
        seen.append(kwargs["strict_baseline"])
        return {"ok": True, "errors": []}

    monkeypatch.setattr(cli, "live_preflight", fake)
    for strict in (True, False):
        arguments = argparse.Namespace(root=str(root), bridge_url=None, strict=strict)
        assert cli._ghidra_preflight(arguments) == 0
    # --strict lets the tracker decide (counts bind only during bootstrap);
    # the plain check never enforces bootstrap counts.
    assert seen == [None, False]


def test_scoped_type_facts_record_only_exact_readbacks() -> None:
    from collections import Counter

    def layout(name: str, size: int) -> str:
        return (
            f"Structure: {name}\nSize: {size} bytes\nAlignment: 1\n\nLayout:\n"
            "Offset | Size | Type | Name\n-------|------|------|-----\n"
            "     0 |    4 | int                  | m_x\n"
        )

    class FakeBridge:
        def request(self, endpoint, **parameters):
            name = parameters.get("struct_name") or parameters.get("enum_name")
            if endpoint == "get_struct_layout":
                if name == "line_data":
                    # The bridge ignores case and answers with another type.
                    return layout("LINE_DATA", 20)
                if name == "CGame":
                    return layout("CGame", 16)
                if name.startswith("alloc_ptr"):
                    return "Structure not found: alloc_ptr<node"
                return f"Data type is not a structure: {name}"
            if name == "GAME_NAME":
                return "Enumeration: GAME_NAME\nSize: 1 bytes\n\nValues:\nName | Value\n-----|------\nnameFTS | 1 (0x1)\n"
            if name.startswith("alloc_ptr"):
                return "Enumeration not found: alloc_ptr<node"
            return f"Data type is not an enumeration: {name}"

    def row(name, size):
        return {"name": name, "category": "project", "size": size, "path": f"/project/{name}"}

    rows = [row("CGame", 16), row("line_data", 4), row("Unique", 4), row("GAME_NAME", 1), row("alloc_ptr<node&, x>", 8), row("_word128", 16)]
    counts = Counter(value["name"].casefold() for value in rows + [row("LINE_DATA", 20)])
    facts = {value["name"]: ghidra._scoped_type_facts(FakeBridge(), value, counts) for value in rows}
    assert facts["CGame"]["layout"]["components"] == [[0, 4, "int", "m_x"]]
    assert facts["line_data"]["detail"] == "ambiguous-name" and "layout" not in facts["line_data"]
    assert facts["GAME_NAME"]["enum"] == {"size": 1, "values": [["nameFTS", 1]]}
    assert facts["alloc_ptr<node&, x>"]["detail"] == "unreadable-name"
    assert facts["_word128"]["detail"] == "no-component-readback"
    # A unique name whose read-back reports another type is never recorded.
    mismatch = ghidra._scoped_type_facts(FakeBridge(), row("line_data", 4), Counter({"line_data": 1}))
    assert mismatch["detail"] == "mismatched-readback" and "layout" not in mismatch


def test_qualified_receipt_scope_preserves_overlay_and_validates_case(
    monkeypatch, root: Path
) -> None:
    preflight = {
        "ok": True,
        "errors": [],
        "analysis": {"analyzed": True, "analyzing": False},
        "counts": {},
        "bookmark_profile": {},
        "sentinel": [],
    }
    calls = []

    class FakeBridge:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, endpoint, **parameters):
            calls.append((endpoint, parameters))
            if endpoint == "get_address_spaces":
                return {
                    "address_spaces": [
                        {"name": "ram", "is_overlay": False},
                        {"name": ".comment", "is_overlay": True},
                    ]
                }
            if endpoint == "audit_global":
                return {
                    "address": ".comment::00000000",
                    "name": "ElfComment[0]",
                    "type": "string-utf8",
                    "length": 30,
                    "plate_comment": "",
                    "xref_count": 1,
                }
            raise AssertionError(endpoint)

    monkeypatch.setattr(ghidra, "live_preflight", lambda *_args, **_kwargs: preflight)
    monkeypatch.setattr(ghidra, "GhidraBridge", FakeBridge)
    monkeypatch.setattr(ghidra, "_function_index", lambda _bridge: [])
    monkeypatch.setattr(ghidra, "_type_index", lambda _bridge: [])
    monkeypatch.setattr(ghidra, "_data_index", lambda _bridge: [])
    scope = {"functions": [], "types": [], "globals": [".comment::0"]}
    result = ghidra.semantic_receipt(root, scope=scope)
    assert result["receipt"]["scoped_facts"]["globals"][0]["address"] == ".comment::00000000"
    audit_call = next(row for row in calls if row[0] == "audit_global")
    assert audit_call[1]["address"] == ".comment::0"
    assert audit_call[1]["strict_mode"] == "off"

    bad_scope = {"functions": [], "types": [], "globals": [".Comment::0"]}
    with pytest.raises(SocomError, match="unknown or mis-cased"):
        ghidra.semantic_receipt(root, scope=bad_scope)


def test_qualified_function_receipt_uses_direct_qualified_calls(
    monkeypatch, root: Path
) -> None:
    preflight = {
        "ok": True,
        "errors": [],
        "analysis": {},
        "counts": {},
        "bookmark_profile": {},
        "sentinel": [],
    }
    calls = []

    class FakeBridge:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, endpoint, **parameters):
            calls.append((endpoint, parameters))
            if endpoint == "get_address_spaces":
                return {"address_spaces": [{"name": ".text", "is_overlay": True}]}
            if endpoint == "disassemble_function":
                return ".text::00000010: jr ra\n"
            if endpoint == "get_function_by_address":
                return "Function: overlay_fn at .text::00000010\n"
            raise AssertionError(endpoint)

    monkeypatch.setattr(ghidra, "live_preflight", lambda *_args, **_kwargs: preflight)
    monkeypatch.setattr(ghidra, "GhidraBridge", FakeBridge)
    monkeypatch.setattr(ghidra, "_function_index", lambda _bridge: [])
    monkeypatch.setattr(ghidra, "_type_index", lambda _bridge: [])
    monkeypatch.setattr(ghidra, "_data_index", lambda _bridge: [])
    scope = {"functions": [".text::10"], "types": [], "globals": []}
    result = ghidra.semantic_receipt(root, scope=scope)
    fact = result["receipt"]["scoped_facts"]["functions"][0]
    assert fact["address"] == ".text::00000010"
    assert fact["disassembly"][0]["address"] == ".text::00000010"
    assert {
        parameters["address"]
        for endpoint, parameters in calls
        if endpoint in {"disassemble_function", "get_function_by_address"}
    } == {".text::10"}


def test_data_overlap_uses_first_strict_reset_and_address_space_inventory(
    monkeypatch, root: Path
) -> None:
    monkeypatch.setattr(
        ghidra,
        "live_preflight",
        lambda *_args, **_kwargs: {"ok": True, "errors": []},
    )

    class FakeBridge:
        def __init__(self, *_args, **_kwargs):
            pass

        def paged_text(self, endpoint):
            assert endpoint == "list_data_items"
            return [
                "outer @ 00000100 [byte[16]] (16 bytes)",
                "alias @ 00000100 [byte[4]] (4 bytes)",
                "inner @ 00000108 [byte[4]] (4 bytes)",
                "overlay0 @ 00000000 [byte[4]] (4 bytes)",
                "overlay1 @ 00000008 [byte[4]] (4 bytes)",
            ]

        def request(self, endpoint, **_parameters):
            assert endpoint == "get_address_spaces"
            return {
                "address_spaces": [
                    {"name": "ram", "is_overlay": False},
                    {"name": ".debug", "is_overlay": True},
                    {"name": ".line", "is_overlay": True},
                ]
            }

    monkeypatch.setattr(ghidra, "GhidraBridge", FakeBridge)
    report = ghidra.data_overlaps(root)
    assert report["physical_item_count"] == 3
    assert report["excluded_overlay_item_count"] == 2
    assert report["overlay_address_space_count"] == 2
    assert report["finding_count"] == 1
    assert "overlay_group_count" not in report
