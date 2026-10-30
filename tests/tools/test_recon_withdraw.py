"""Withdrawal candidates and by-value rows: read-only reports over accepted plans (2026-10-29)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools._socom import recon
from tools._socom.recon_byvalue import by_value_rows
from tools._socom.recon_withdraw import applied_rows, withdrawal_candidates


def _item(item_id: str, kind: str, status: str, functions: list[str], number: int | None = None) -> dict:
    batch = {"functions": functions, **({"repair_number": number} if number else {"group_number": 1})}
    return {"id": item_id, "kind": kind, "status": status, "batch": batch}


def _row(address: str, return_type: str | None, evidence: list[str] | None = None, **extra) -> dict:
    prototype = None
    if return_type is not None:
        prototype = {"return_type": return_type, "parameters": [{"name": "p", "type": "int"}], "evidence": evidence or ["x"]}
    return {"address": address, "current_name": f"f_{address}", "prototype": prototype, **extra}


@pytest.fixture()
def plans(tmp_path: Path, monkeypatch) -> dict:
    """Plan files under tmp_path, found through recon.plan_path_for."""

    stored: dict[str, Path] = {}

    def write(item_id: str, rows: list[dict]) -> None:
        path = tmp_path / f"{item_id.replace(':', '-')}.json"
        path.write_text(json.dumps({"functions": rows}), encoding="utf-8")
        stored[item_id] = path

    monkeypatch.setattr(recon, "plan_path_for", lambda root, item_id: stored.get(item_id.removesuffix("-apply"), tmp_path / "missing.json"))
    return {"write": write}


GROUP = "socom:recon-group:aaaa"
REPAIR = "socom:work:recon-repair-001"
PENDING = "socom:work:recon-repair-002"


def _tracker() -> dict:
    functions = ["0x226320", "0x46b9d0", "0x17cbe0", "0x3defd8", "0x2986e0", "0x14fd60", "0x3e0658", "0x3e0550", "0x150050", "0x16a790"]
    return {
        "revision": 7,
        "work_items": [
            _item(GROUP, "recon-plan-group", "accepted", functions),
            _item(f"{GROUP}-apply", "recon-apply-group", "accepted", []),
            _item(REPAIR, "recon-repair-plan", "accepted", ["0x226320", "0x3e0658"], 1),
            _item(f"{REPAIR}-apply", "recon-repair-apply", "accepted", []),
            _item(PENDING, "recon-repair-plan", "ready", ["0x14fd60"], 2),
            _item(f"{PENDING}-apply", "recon-repair-apply", "blocked", []),
        ],
    }


def test_withdrawal_candidates_follow_the_rules(root: Path, plans: dict) -> None:
    plans["write"](GROUP, [
        _row("0x226320", "void"),  # recon void: open -> candidate
        _row("0x46b9d0", "void"),  # the drafter's __sinit_ rule
        _row("0x17cbe0", "void"),  # its own DWARF FT_void
        _row("0x3defd8", "void"),  # recon void: VERDICT void
        _row("0x2986e0", "void", ["DWARF ANIM_CALLBACK.m_func points to subroutine_type 0x132b4 with FT_void"]),
        _row("0x14fd60", "int", ["Sony libdma; int sceDmaReset(int mode) per libdma.h", "returns s1 (andi s1,a1,0x1)"]),
        _row("0x3e0658", "int", ["stdio.h int fflush(FILE *fp)"]),
        _row("0x3e0550", "int", ["the live FILE is the 160-byte /stdio.h/FILE"]),  # a type path, not a citation
        _row("0x150050", "undefined", ["libdma.h"], unresolved=["x"]),
        _row("0x16a790", "double", ["newlib libm s_ceil.c double ceil(double x); matches the live signature"]),
    ])
    plans["write"](REPAIR, [
        {"address": "0x226320", "current_name": "x", "keep": True, "keep_reason": ["kept"]},  # the group row stays
        _row("0x3e0658", "uint", ["stdlib.h", "errno.h"]),  # supersedes the group row
    ])
    plans["write"](PENDING, [])
    tracker = _tracker()
    rows = applied_rows(root, tracker)
    assert rows[0x226320]["source"] == GROUP and rows[0x3e0658]["source"] == REPAIR
    assert rows[0x14fd60]["pending_repairs"] == [PENDING]
    result = withdrawal_candidates(root, tracker)
    assert result["mutation_performed"] is False and result["rules_version"] == 21
    void = result["void"]
    assert [row["address"] for row in void["candidates"]] == ["0x226320"]
    assert void["candidates"][0]["verdict"] == "VERDICT open: the function's address is taken or stored in a table"
    assert (void["applied_void_rows"], void["recon_void"], void["dwarf_void"], void["sinit_rule"], void["dwarf_void_type_cited"]) == (5, 1, 1, 1, 1)
    assert void["excluded_cited_void_types"] == [{"address": "0x2986e0", "name": "f_0x2986e0", "subroutine_types": ["0x132b4"]}]
    header = result["header"]
    found = {row["address"]: row for row in header["candidates"]}
    assert set(found) == {"0x14fd60", "0x3e0658"}
    assert found["0x14fd60"]["headers"] == ["libdma.h"] and found["0x14fd60"]["library"] == "sdk"
    assert found["0x14fd60"]["other_evidence"] == ["returns s1 (andi s1,a1,0x1)"]
    assert found["0x14fd60"]["pending_repairs"] == [PENDING]
    assert found["0x3e0658"]["headers"] == ["errno.h", "stdlib.h"] and found["0x3e0658"]["source"] == REPAIR
    assert header["by_library"] == {"c-library": 1, "sdk": 1}
    assert [row["address"] for row in header["provider_rows_without_header"]] == ["0x16a790"]
    assert withdrawal_candidates(root, tracker, kinds=("header",)).get("void") is None
    with pytest.raises(Exception, match="unknown candidate kind"):
        withdrawal_candidates(root, tracker, kinds=("nope",))


def test_cited_void_subroutine_types_in_every_spelling(root: Path) -> None:
    from tools._socom.recon_facts import context
    from tools._socom.recon_withdraw import _cited_void_types

    ctx = context(root)
    for text in (
        "ANIM_CALLBACK.m_func points to subroutine_type 0x132b4 with FT_void",
        "subroutine type DIE 0x132b4 = void (void *, void *)",
        "subroutine_type DIE 0x132b4 (member m_func)",
        "subroutine type 0x132b4 = void (void *, void *)",
    ):
        assert _cited_void_types(ctx, [text]) == ["0x132b4"], text
    # A DIE that is not a void subroutine_type never excludes the row.
    assert _cited_void_types(ctx, ["subroutine type DIE 0xb932: uchar (int)"]) == []


def test_syscall_stub_voids_are_withdrawal_candidates(root: Path, plans: dict) -> None:
    # ExitThread is `li v1,35; syscall; jr ra`: v0 is the kernel's result, so
    # recon void no longer proves the applied void (it did while syscall wrote nothing).
    plans["write"](GROUP, [_row("0x15b350", "void", ["SDK stub"])])
    tracker = {"revision": 1, "work_items": [
        _item(GROUP, "recon-plan-group", "accepted", ["0x15b350"]),
        _item(f"{GROUP}-apply", "recon-apply-group", "accepted", []),
    ]}
    void = withdrawal_candidates(root, tracker, kinds=("void",))["void"]
    assert [row["address"] for row in void["candidates"]] == ["0x15b350"] and void["recon_void"] == 0
    assert void["candidates"][0]["verdict"].startswith("VERDICT open: some exit can return a value")


def test_by_value_rows_lists_accepted_and_applied_rows(root: Path, plans: dict) -> None:
    by_value = {"return_type": "void", "evidence": ["x"],
                "parameters": [{"name": "this", "type": "Source *"}, {"name": "e", "type": "CPnt4D"}]}
    eight = {"return_type": "void", "evidence": ["x"], "parameters": [{"name": "p", "type": "PNT2D"}]}
    plans["write"](GROUP, [
        {"address": "0x2392d0", "current_name": "CheckExtents", "prototype": by_value},
        {"address": "0x2fe4a0", "current_name": "SetCenterPos", "prototype": eight},
    ])
    plans["write"](REPAIR, [{"address": "0x2392d0", "current_name": "CheckExtents", "keep": True, "keep_reason": ["x"]}])
    plans["write"](PENDING, [{"address": "0x2392d0", "current_name": "CheckExtents", "prototype": by_value}])
    tracker = _tracker()
    for item in tracker["work_items"]:
        if item["id"] == GROUP:
            item["batch"]["functions"] = ["0x2392d0", "0x2fe4a0"]
        elif item["id"] == REPAIR:
            item["batch"]["functions"] = ["0x2392d0"]
    result = by_value_rows(root, tracker)
    assert result["addresses"] == ["0x2392d0"] and result["row_count"] == 1 and result["live_count"] == 1
    (row,) = result["rows"]
    assert row["item"] == GROUP and row["live"] and row["parameters"][0]["type"] == "CPnt4D"
    assert "16 bytes" in row["parameters"][0]["problem"]
