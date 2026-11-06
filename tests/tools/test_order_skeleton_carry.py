"""Stage 5 re-apply: the fence-keyed carry of entries the new render moves, before the per-file merge.

Small files under tmp_path: a holding file and a unit file whose previous
render, live src/ content and new render are given per test.  Nothing writes
the real tracker or src/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools._socom.order_plan import ORDER_APPLY_KIND, ORDER_PREPARE_KIND
from tools._socom.order_skeleton_carry import parse_entries
from tools._socom.order_skeleton_merge import DELETION_SUFFIX, conflict_marker_root, conflict_report_path, fence_lines, put_blob, sha
from tools._socom.order_skeleton_route import _merge_scope, carried_entries, verify_written
from tools._socom.util import SocomError

HOLD = "src/gamez/zDemo/zdemo_holding.cpp"
UNIT = "src/gamez/zDemo/demo_main.cpp"
PREPARE = "socom:work:order-skeleton-prepare"
APPLY = "socom:work:order-segment-001-apply"
NOTE = "/* Unbuilt holding file (stage 5 BD4) */\n"
BLOCK = (
    "/* socom-owner-annotations begin socom:work:source-segment-001\n"
    " * @socom-artifact defines .text socom:function:0x100000\n"
    " * socom-owner-annotations end socom:work:source-segment-001 */\n"
)


def _held(name: str, source: str, text: str) -> str:
    return f"/* @socom-skeleton body {name} */\n/* held from {source} */\n{text}"


def _fence(kind: str, name: str, text: str) -> str:
    return f"/* @socom-skeleton {kind} {name} */\n{text}"


def _file(head: str, *entries: str) -> bytes:
    return (head + "".join("\n" + entry for entry in entries)).encode()


F_OLD = _held("f__FPc", "src/demo.cpp:3", "void f(char* s)\n{\n}\n")
F_NEW = _fence("body", "f__FPCc", "void f(const char* s)\n{\n}\n")
G = _held("g__Fv", "src/demo.cpp:9", "void g()\n{\n}\n")
H = _fence("stub", "h__Fv", "void h()\n{\n}\n")


def _workspace(tmp_path: Path, files: dict[str, tuple[bytes | None, bytes | None, bytes | None]],
               owners: dict[str, list[str]], *, entries: list[dict] | None = None) -> tuple[dict, dict]:
    """(tracker, rendered): per path (previous render, live src/, new render); each item's record rendered the previous."""

    base = tmp_path / "base"
    items = []
    for item_id, paths in owners.items():
        rows = []
        for path in paths:
            previous, live, _new = files[path]
            (base / path).parent.mkdir(parents=True, exist_ok=True)
            (base / path).write_bytes(BLOCK.encode() if path == UNIT else NOTE.encode())
            if live is not None:
                (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
                (tmp_path / path).write_bytes(live)
            put_blob(tmp_path, previous)
            rows.append({"path": path, "action": "unit", "after_sha256": sha(previous)})
        kind = ORDER_PREPARE_KIND if item_id == PREPARE else ORDER_APPLY_KIND
        items.append({"id": item_id, "kind": kind, "status": "in_progress", "resources": paths,
                      "order_skeleton": {"kind": "socom-order-skeleton-apply", "item": item_id, "files": rows}})
    rendered = {"files": {path: new for path, (_old, _live, new) in files.items()},
                "manifest": {"files": [{"path": path, "action": "unit"} for path, row in files.items() if row[2] is not None],
                             "deleted": [{"path": path} for path, row in files.items() if row[2] is None],
                             "entries": entries or [{"path": UNIT, "name": "f__FPCc", "source": "src/demo.cpp:3"}]}}
    return {"work_items": items}, rendered


def _item(tracker: dict, item_id: str) -> dict:
    return next(row for row in tracker["work_items"] if row["id"] == item_id)


def _merge(tmp_path: Path, tracker: dict, rendered: dict, item_id: str, resolutions: Path | None = None) -> tuple[dict, dict, list]:
    rows, changes, blobs = _merge_scope(tmp_path, tracker, _item(tracker, item_id), rendered, tmp_path / "base", resolutions)
    return {row["path"]: row for row in rows}, changes, blobs


def _commit(tmp_path: Path, tracker: dict, item_id: str, rows: dict, changes: dict, blobs: list) -> None:
    """What a real apply does: write the changes, store the blobs, record the rows (and their carried entries)."""

    for path, data in changes.items():
        if data is None:
            (tmp_path / path).unlink()
        else:
            (tmp_path / path).write_bytes(data)
    for data in blobs:
        put_blob(tmp_path, data)
    record = _item(tracker, item_id)["order_skeleton"]
    record["files"] = list(rows.values())
    record["carried"] = carried_entries(list(rows.values()))


EDITED_F = F_OLD.replace("{\n}\n", "{\n\tport_init();\n}\n")


def test_entries_are_top_level_fences_and_regions() -> None:
    text = (NOTE + "\n" + _fence("decl", "Q23zdb4CFoo", "class CFoo {};\n/* @socom-skeleton end Q23zdb4CFoo */\n") + "\n"
            + _fence("stub", "f__Fv", "void f()\n{\n\t/* @socom-skeleton stub local$1 */\n\tstatic int local;\n}\n") + "\n\n" + G)
    entries = parse_entries(text.splitlines(keepends=True))
    assert [(entry.kind, entry.name, entry.source) for entry in entries] == [
        ("decl", "Q23zdb4CFoo", None), ("stub", "f__Fv", None), ("body", "g__Fv", "src/demo.cpp:9")]
    assert entries[1].end - entries[1].start == 6  # the indented local static belongs to f; trailing blank lines do not


def test_a_moved_body_carries_its_live_edit_to_the_renders_new_place(tmp_path: Path) -> None:
    # The render moves f from the holding file to the unit (its fence renamed by the declarator rewrite, matched by
    # the held body id); the port lane edited f in the holding file.
    files = {HOLD: (_file(NOTE, F_OLD, G), _file(NOTE, EDITED_F, G), _file(NOTE, G)),
             UNIT: (_file(BLOCK, H), _file(BLOCK, H), _file(BLOCK, H, F_NEW))}
    tracker, rendered = _workspace(tmp_path, files, {APPLY: [HOLD, UNIT]})
    rows, changes, blobs = _merge(tmp_path, tracker, rendered, APPLY)
    assert changes[HOLD] == _file(NOTE, G)  # the edit left with the entry: no conflict, no loss
    assert b"void f(const char* s)\n{\n\tport_init();\n}\n" in changes[UNIT]
    assert fence_lines(changes[UNIT]) == fence_lines(files[UNIT][2])
    assert rows[HOLD]["merge"] == rows[UNIT]["merge"] == "carried"
    (carried,) = rows[UNIT]["carried"]
    assert (carried["name"], carried["live_name"], carried["from"], carried["to"], carried["state"]) == (
        "f__FPCc", "f__FPc", HOLD, UNIT, "merged")
    # apply-check re-runs the recorded merge over the stored effective inputs.
    _commit(tmp_path, tracker, APPLY, rows, changes, blobs)
    assert verify_written(tmp_path, {"files": list(rows.values())}, {HOLD: files[HOLD][2], UNIT: files[UNIT][2]}) == ([], [])
    forged = {"files": [{**rows[UNIT], "after_sha256": sha(files[UNIT][2])}]}
    assert any("does not reproduce" in text for text in verify_written(tmp_path, forged, {UNIT: files[UNIT][2]})[0])


def test_a_carried_entry_both_sides_changed_is_an_entry_conflict_with_both_sides(tmp_path: Path) -> None:
    edited = F_OLD.replace("void f(char* s)\n", "void f(char* s) /* port: the ELF has f__FPCc */\n")
    files = {HOLD: (_file(NOTE, F_OLD, G), _file(NOTE, edited, G), _file(NOTE, G)),
             UNIT: (_file(BLOCK, H), _file(BLOCK, H), _file(BLOCK, H, F_NEW))}
    tracker, rendered = _workspace(tmp_path, files, {APPLY: [HOLD, UNIT]})
    with pytest.raises(SocomError, match="1 files conflict"):
        _merge(tmp_path, tracker, rendered, APPLY)
    report = json.loads((tmp_path / conflict_report_path(APPLY)).read_text(encoding="utf-8"))
    (row,) = report["files"]
    assert row["path"] == UNIT and row["reason"] == "1 carried entries conflict" and row["carry_sha256"]
    (entry,) = row["entries"]
    assert (entry["entry"], entry["from"], entry["to"]) == ("f__FPCc", HOLD, UNIT)
    (hunk,) = entry["hunks"]
    assert "/* port: the ELF has f__FPCc */" in hunk["ours"] and "void f(const char* s)" in hunk["theirs"]
    marked = (tmp_path / conflict_marker_root(APPLY) / UNIT).read_bytes()
    assert b"<<<<<<< ours (src/)" in marked and b"/* @socom-skeleton body f__FPCc */" in marked
    # The destination file is resolved as a whole; the holding file merged (its edit went with the entry).
    resolutions = tmp_path / "build" / "resolved"
    (resolutions / UNIT).parent.mkdir(parents=True)
    (resolutions / UNIT).write_bytes(files[UNIT][2].replace(b"void f(const char* s)\n", b"void f(const char* s) /* port */\n"))
    rows, changes, _blobs = _merge(tmp_path, tracker, rendered, APPLY, resolutions)
    assert rows[UNIT]["merge"] == "resolved" and rows[HOLD]["merge"] == "carried" and changes[HOLD] == _file(NOTE, G)


def test_an_entry_moved_to_another_items_file_is_pending_until_that_item_carries_it(tmp_path: Path) -> None:
    files = {HOLD: (_file(NOTE, F_OLD, G), _file(NOTE, EDITED_F, G), _file(NOTE, G)),
             UNIT: (_file(BLOCK, H), _file(BLOCK, H), _file(BLOCK, H, F_NEW))}
    tracker, rendered = _workspace(tmp_path, files, {PREPARE: [HOLD], APPLY: [UNIT]})
    rows, changes, blobs = _merge(tmp_path, tracker, rendered, PREPARE)
    assert changes == {HOLD: _file(NOTE, G)}
    (pending,) = rows[HOLD]["carried"]
    assert (pending["state"], pending["to"], pending["to_item"], pending["from"]) == ("pending", UNIT, APPLY, HOLD)
    assert sha(EDITED_F.split("\n", 1)[1].encode()) == pending["live_sha256"]
    _commit(tmp_path, tracker, PREPARE, rows, changes, blobs)
    assert verify_written(tmp_path, {"files": list(rows.values())}, {HOLD: files[HOLD][2]}) == ([], [])
    # The segment apply takes the edit from the prepare's record: src/ no longer holds it anywhere.
    rows, changes, _blobs = _merge(tmp_path, tracker, rendered, APPLY)
    assert b"\tport_init();" in changes[UNIT]
    (merged,) = rows[UNIT]["carried"]
    assert (merged["state"], merged["via"], merged["from"]) == ("merged", PREPARE, HOLD)


def test_an_entry_the_destination_item_carried_first_is_carried_by_it(tmp_path: Path) -> None:
    files = {HOLD: (_file(NOTE, F_OLD, G), _file(NOTE, EDITED_F, G), _file(NOTE, G)),
             UNIT: (_file(BLOCK, H), _file(BLOCK, H), _file(BLOCK, H, F_NEW))}
    tracker, rendered = _workspace(tmp_path, files, {PREPARE: [HOLD], APPLY: [UNIT]})
    rows, changes, blobs = _merge(tmp_path, tracker, rendered, APPLY)  # the unit's item first: from the live holding file
    assert b"\tport_init();" in changes[UNIT] and rows[UNIT]["carried"][0]["from"] == HOLD
    _commit(tmp_path, tracker, APPLY, rows, changes, blobs)
    rows, changes, _blobs = _merge(tmp_path, tracker, rendered, PREPARE)
    assert rows[HOLD]["carried"][0]["state"] == "carried-by" and changes == {HOLD: _file(NOTE, G)}
    # An edit of the holding file's entry after that carry would be lost: a conflict.
    (tmp_path / HOLD).write_bytes(_file(NOTE, EDITED_F.replace("port_init", "port_init2"), G))
    with pytest.raises(SocomError, match="1 files conflict"):
        _merge(tmp_path, tracker, rendered, PREPARE)
    (row,) = json.loads((tmp_path / conflict_report_path(PREPARE)).read_text(encoding="utf-8"))["files"]
    assert "before its later edit here" in row["entries"][0]["reason"]


def test_port_added_fences_follow_the_render_or_become_port_comments(tmp_path: Path) -> None:
    port_p = _fence("stub", "p__Fv", "void p()\n{\n\tport_p();\n}\n")
    port_q = _fence("stub", "q__Fv", "void q()\n{\n\tport_q();\n}\n")
    files = {HOLD: (_file(NOTE, F_OLD, G), _file(NOTE, F_OLD, G, port_p), _file(NOTE, F_OLD, G)),
             UNIT: (_file(BLOCK, H), _file(BLOCK, H, port_q), _file(BLOCK, H, _fence("stub", "p__Fv", "void p()\n{\n}\n")))}
    tracker, rendered = _workspace(tmp_path, files, {APPLY: [HOLD, UNIT]})
    rows, changes, _blobs = _merge(tmp_path, tracker, rendered, APPLY)
    # p, which the render now places in the unit, takes the port's code there (a canonical stub has no other text).
    assert changes[HOLD] == files[HOLD][2] and b"void p()\n{\n\tport_p();\n}\n" in changes[UNIT]
    # q, placed nowhere, keeps its code; its fence becomes a port comment, reported.
    assert b"/* port: stub q__Fv (no owner in the render) */\nvoid q()\n{\n\tport_q();\n}\n" in changes[UNIT]
    assert fence_lines(changes[UNIT]) == fence_lines(files[UNIT][2])
    states = {row["name"]: (row["state"], row["from"], row["to"]) for row in carried_entries(list(rows.values()))}
    assert states == {"p__Fv": ("merged", HOLD, UNIT), "q__Fv": ("port-comment", UNIT, None)}


def test_a_deleted_file_whose_only_edits_were_carried_is_deleted_else_a_resolvable_conflict(tmp_path: Path) -> None:
    files = {HOLD: (_file(NOTE, F_OLD), _file(NOTE, EDITED_F), None),
             UNIT: (_file(BLOCK, H), _file(BLOCK, H), _file(BLOCK, H, F_NEW))}
    tracker, rendered = _workspace(tmp_path, files, {APPLY: [HOLD, UNIT]})
    rows, changes, _blobs = _merge(tmp_path, tracker, rendered, APPLY)
    assert changes[HOLD] is None and rows[HOLD]["merge"] == "carried" and rows[HOLD]["after_sha256"] is None
    assert b"\tport_init();" in changes[UNIT]
    # A live change outside the carried entries: the deletion conflicts, a resolution settles it.
    (tmp_path / HOLD).write_bytes(_file(NOTE + '#include "demo.h"\n', EDITED_F))
    with pytest.raises(SocomError, match="1 files conflict"):
        _merge(tmp_path, tracker, rendered, APPLY)
    (row,) = json.loads((tmp_path / conflict_report_path(APPLY)).read_text(encoding="utf-8"))["files"]
    assert row["path"] == HOLD and "absent in theirs" in row["reason"]
    resolutions = tmp_path / "build" / "resolved"
    (resolutions / HOLD).parent.mkdir(parents=True)
    (resolutions / (HOLD + DELETION_SUFFIX)).write_bytes(b"")
    rows, changes, _blobs = _merge(tmp_path, tracker, rendered, APPLY, resolutions)
    assert changes[HOLD] is None and rows[HOLD]["merge"] == "resolved" and rows[HOLD]["resolution"]["deleted"] is True
    assert verify_written(tmp_path, {"files": [rows[HOLD]]}, {HOLD: None})[0] == []
    # Or as content: the kept file may hold port code, but no fence.
    (resolutions / (HOLD + DELETION_SUFFIX)).unlink()
    (resolutions / HOLD).write_bytes(b'#include "demo.h"\n')
    rows, changes, _blobs = _merge(tmp_path, tracker, rendered, APPLY, resolutions)
    assert changes[HOLD] == b'#include "demo.h"\n' and rows[HOLD]["merge"] == "resolved"
    (resolutions / HOLD).write_bytes(_file(NOTE, EDITED_F))
    with pytest.raises(SocomError, match="may hold no @socom-skeleton fence"):
        _merge(tmp_path, tracker, rendered, APPLY, resolutions)


def test_a_clean_merge_that_breaks_the_renders_fences_is_a_resolvable_conflict(tmp_path: Path) -> None:
    region = _fence("decl", "Q23zdb4CFoo", "class CFoo {};\n/* @socom-skeleton end Q23zdb4CFoo */\n")
    files = {UNIT: (_file(BLOCK, H), _file(BLOCK, region, H), _file(BLOCK, H, _fence("stub", "k__Fv", "void k()\n{\n}\n")))}
    tracker, rendered = _workspace(tmp_path, files, {APPLY: [UNIT]})
    with pytest.raises(SocomError, match="1 files conflict"):
        _merge(tmp_path, tracker, rendered, APPLY)
    (row,) = json.loads((tmp_path / conflict_report_path(APPLY)).read_text(encoding="utf-8"))["files"]
    assert row["reason"] == "the merge breaks the render's structure" and "fence lines differ" in row["check"][0]
    marked = (tmp_path / conflict_marker_root(APPLY) / UNIT).read_bytes()
    assert region.encode() in marked  # the merged file, for the worker to fix
    resolutions = tmp_path / "build" / "resolved"
    (resolutions / UNIT).parent.mkdir(parents=True)
    (resolutions / UNIT).write_bytes(marked.replace(region.encode() + b"\n", b""))
    rows, changes, _blobs = _merge(tmp_path, tracker, rendered, APPLY, resolutions)
    assert rows[UNIT]["merge"] == "resolved" and changes[UNIT] == files[UNIT][2]


def test_an_edit_next_to_a_moved_block_merges_entry_by_entry(tmp_path: Path) -> None:
    # The port lane added includes to the preamble and edited the last kept entry; the render moves the next entries
    # away. Line merge3 sees adjacent changes; merging the preamble and each entry on its own does not.
    kept = _held("k__Fv", "src/demo.cpp:1", "void k()\n{\n}\n")
    files = {HOLD: (_file(NOTE, kept, F_OLD, G),
                    _file(NOTE + '#include "demo.h"\n', kept.replace("}\n", "} /* port */\n"), F_OLD, G),
                    _file(NOTE, kept)),
             UNIT: (_file(BLOCK, H), _file(BLOCK, H), _file(BLOCK, H, F_NEW, G))}
    tracker, rendered = _workspace(tmp_path, files, {APPLY: [HOLD, UNIT]})
    rows, changes, _blobs = _merge(tmp_path, tracker, rendered, APPLY)
    assert changes[HOLD] == _file(NOTE + '#include "demo.h"\n', kept.replace("}\n", "} /* port */\n"))
    assert rows[HOLD]["merge"] == "carried" and rows[HOLD]["entry_merges"] == ["(preamble)", "k__Fv"]
