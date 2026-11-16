"""A header move stated by stage 4 plans (``header_moves``): validated, applied as a move, followed by stage 5.

The unit tests use small trees under tmp_path and in-memory trackers; the
route test runs every command on the synthetic stage 4 workspace
(``amendable``), with the skeleton wave's records built by hand as in
``test_order_reopen`` (the synthetic workspace has no skeleton manifest, so
the skeleton re-apply is its merge over a hand-made render).  Nothing writes
the real tracker or src/.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools._socom.order_plan import ORDER_APPLY_KIND, ORDER_SKELETON_PREPARE_ID
from tools._socom.order_reopen import (
    base_changes,
    base_header_moves,
    fenced_includers,
    follow_header_moves,
    snapshot_reseal,
    with_blocks,
)
from tools._socom.order_skeleton_merge import put_blob, sha
from tools._socom.order_skeleton_route import BASE_DIR, ROUTE_DIR, SNAPSHOT_PATH, _merge_scope, _prior_rows, blocks_sha256
from tools._socom.source_apply import content_sha256, parse_blocks
from tools._socom.source_header_move import (
    header_move_conflicts,
    header_move_report,
    include_spelling,
    includers,
    own_relative_includes,
    recorded_header_moves,
)
from tools._socom.source_plan import derive_annotations, graph_digest, plan_path, validate_source_plan
from tools._socom.tracker import audit_tracker, refresh_ready_and_stages
from tools._socom.util import SocomError

import test_source_apply
import test_source_gate
from test_order_plan import _accept, _cited, _decompose, _handoff
from test_order_reopen import _accept_order_plans, _stage5, _write_snapshot
from test_source_amend import (  # noqa: F401 - amendable is a fixture
    FIRST,
    SECOND,
    _accept_amendment,
    _amend,
    _plan,
    _reapply,
    _revise,
    amendable,
)
from test_source_apply import SEGMENT_1, SEGMENT_3, _claim, _load, _revision, _run, _save, stage3_tracker, workspace  # noqa: F401
from test_source_gate import DEFERRALS, _receipt, _stage3_receipt, closing  # noqa: F401
from test_source_plan import MAIN, _reservation, _workspace, segment_plan, synthetic, synthetic_graph  # noqa: F401

OLD = "src/gamez/zFoo/zfoo.h"
NEW = "src/gamez/zBaz/b_box.h"
UNIT_A = "src/gamez/zBar/a.cpp"
UNIT_B = "src/gamez/zBaz/b.cpp"
HOOK = "port/test-hooks/box/hook_box.cpp"
APPLY_1 = "socom:work:order-segment-001-apply"
APPLY_3 = "socom:work:order-segment-003-apply"
# The provisional header before the skeleton wave: an include guard, an include beside it, one in-class body (line 8).
HEADER = ('#ifndef ZFOO_H\n#define ZFOO_H\n#include "zfoo_types.h"\n\nclass CBox\n{\npublic:\n\tint Get() { return 1; }\n};\n#endif\n')
BODY = (8, "int Get() { return 1; }")
REGION = "\t/* @socom-skeleton decl 4CBox */\n\tvoid Put();\n\t/* @socom-skeleton end 4CBox */\n"
HEADER_RENDER = HEADER.replace("};\n#endif", REGION + "};\n#endif")
PORT_EDIT = "\tint m_port; /* port: a later edit */\n"


def _moved(plan: dict, graph: dict, *, directories: list[str] | None = None) -> dict:
    """``plan`` revised for the move: its emits name the new header, the move is stated, the reservation covers both."""

    plan = copy.deepcopy(plan)
    plan["schema_version"] = 2
    for row in plan["header_emits"]:
        if row["header"] == OLD:
            row["header"] = NEW
    plan["header_moves"] = [{"from": OLD, "to": NEW, "reason": "user decision: CBox's header goes next to b.cpp",
                             "evidence": ["decision file, CBox"]}]
    if directories is not None:
        plan["reservation"] = _reservation(directories, "corrected")
    plan["annotations"] = derive_annotations(plan, graph, MAIN)
    return plan


# -- the statement ------------------------------------------------------------------------------


def _valid(graph: dict) -> dict:
    plan = segment_plan(graph)
    plan["retire_files"] = []
    return _moved(plan, graph, directories=["src/gamez/zFoo", "src/gamez/zBaz"])


def test_a_plan_states_the_move_of_a_header_it_emits_from(tmp_path: Path, synthetic: tuple[dict, dict]) -> None:
    tracker, graph = synthetic
    root = _workspace(tmp_path)
    (root / OLD).write_text(HEADER, encoding="utf-8")
    (root / "src/gamez/zFoo/zfoo_types.h").write_text("typedef int box_t;\n", encoding="utf-8")
    (root / UNIT_B).parent.mkdir(parents=True)
    (root / UNIT_B).write_text('/* @socom-skeleton decl include */\n#include "gamez/zFoo/zfoo.h"\n/* @socom-skeleton end include */\n',
                               encoding="utf-8")
    (root / HOOK).parent.mkdir(parents=True)
    (root / HOOK).write_text('#include "gamez/zFoo/zfoo.h"\n#include "gamez/zFoo/zfoo_types.h"\n', encoding="utf-8")
    plan = _valid(graph)
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert report["ok"], report["problems"]
    assert report["summary"]["header_moves"] == 1
    (row,) = report["header_moves"]
    assert (row["from"], row["to"], row["state"]) == (OLD, NEW, "pending")
    # The tools rewrite no #include: each line that names the old path is listed by kind, with the new spelling.
    assert [(entry["path"], entry["line"], entry["kind"], entry["suggested"]) for entry in row["includers"]] == [
        (UNIT_B, 2, "fenced", '#include "b_box.h"'),
        (HOOK, 1, "authored", '#include "gamez/zBaz/b_box.h"'),
    ]
    # The header's own include beside it stops resolving from the new directory: a hand edit too.
    assert row["own_relative_includes"] == [{"line": 3, "text": '#include "zfoo_types.h"', "suggested": '#include "gamez/zFoo/zfoo_types.h"'}]
    assert any("2 #include lines still name the old path (1 generated by stage 5 include regions" in line for line in report["review"])
    # The annotation follows the emit row: the edge is derived in the new header.
    assert ("emits", NEW) in {(entry["relation"], entry["path"]) for entry in plan["annotations"]}

    # Once an apply recorded the move the statement is checked in its applied state.
    applied = {"moves": [{"from": OLD, "to": NEW, "kind": "header", "performed": True}], "created": [], "retired": []}
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN, applied=applied)
    assert any("the apply moved the header but src/gamez/zFoo/zfoo.h exists again" in line for line in report["problems"])
    assert any(f"the apply moved the header but {NEW} is missing" in line for line in report["problems"])
    (root / NEW).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(root / OLD, root / NEW)
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN, applied=applied)
    assert report["ok"] and report["header_moves"][0]["state"] == "applied", report["problems"]
    # Unapplied, the same tree is refused: the move is the apply's, never a hand move.
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert any("must name an existing header under src/ exactly" in line for line in report["problems"])
    assert any("exists already (a header move needs a free target)" in line for line in report["problems"])


def _defect(change, message: str):
    return pytest.param(change, message, id=message[:40])


HEADER_MOVE_DEFECTS = [
    _defect(lambda plan: plan.update(schema_version=1), "unknown fields ['header_moves']"),
    _defect(lambda plan: plan.update(header_moves={}), "header_moves must be a list"),
    _defect(lambda plan: plan["header_moves"][0].pop("evidence"), "must be {from, to, reason, evidence}"),
    _defect(lambda plan: plan["header_moves"][0].update(reason=" "), "needs a reason and evidence lines"),
    _defect(lambda plan: plan["header_moves"][0].update(to="src/gamez/zBaz/b_box.cpp"), "to must be a repo-relative header path"),
    _defect(lambda plan: plan["header_moves"][0].update({"from": "build/zfoo.h"}), "from must be a repo-relative header path"),
    _defect(lambda plan: plan["header_moves"][0].update(to=OLD), "a move needs two different paths"),
    _defect(lambda plan: plan["header_moves"].append(dict(plan["header_moves"][0])), "is listed twice"),
    _defect(lambda plan: plan["header_moves"].append({**plan["header_moves"][0], "from": NEW, "to": "src/gamez/zBaz/c.h"}),
            "a header moves once"),
    _defect(lambda plan: plan.update(reservation=_reservation(["src/gamez/zFoo"], "confirmed")),
            "lies outside the reservation of socom:work:source-segment-001-apply"),
    _defect(lambda plan: plan.update(reservation=_reservation(["src/gamez/zBaz", "src/gamez/zBar"], "corrected")),
            "the apply removes the old header and writes the new one"),
    _defect(lambda plan: plan["header_emits"][0].update(header=OLD), "no header-emit row names src/gamez/zBaz/b_box.h"),
    _defect(lambda plan: plan["header_emits"][0].update(header=OLD), "an owner or header-emit row still names"),
    _defect(lambda plan: plan["retire_files"].append({"path": OLD, "reason": "moved", "evidence": ["x"]}),
            "is also listed in retire_files"),
    _defect(lambda plan: plan["header_moves"][0].update({"from": "src/gamez/zFoo/none.h"}),
            "src/gamez/zFoo/none.h must name an existing header under src/ exactly"),
    _defect(lambda plan: plan["header_moves"][0].update(to="src/gamez/zfoo/b_box.h"), "differs in letter case"),
]


@pytest.mark.parametrize(("change", "message"), HEADER_MOVE_DEFECTS)
def test_header_move_defects_are_refused(tmp_path: Path, synthetic: tuple[dict, dict], change, message: str) -> None:
    tracker, graph = synthetic
    root = _workspace(tmp_path)
    plan = _valid(graph)
    change(plan)
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert not report["ok"]
    assert any(message in problem for problem in report["problems"]), report["problems"]


def test_only_a_segment_plan_states_a_header_move(tmp_path: Path, synthetic: tuple[dict, dict]) -> None:
    from test_source_plan import provider_plan

    tracker, graph = synthetic
    plan = provider_plan(graph)
    plan.update(schema_version=2, header_moves=[{"from": OLD, "to": NEW, "reason": "r", "evidence": ["e"]}])
    report = validate_source_plan(_workspace(tmp_path), tracker, plan, graph, section_of=MAIN)
    assert any("only a segment plan states a header move" in line for line in report["problems"]), report["problems"]


def test_every_plan_names_a_moved_header_at_its_new_path(tmp_path: Path, synthetic: tuple[dict, dict]) -> None:
    tracker, graph = synthetic
    root = _workspace(tmp_path)
    plan = _valid(graph)
    other = test_source_apply.plans(graph)[SEGMENT_3]
    other["header_emits"] = [{"artifact": other["owners"][0]["artifacts"][0], "header": OLD, "reason": "inline", "evidence": ["x"]}]
    path = root / plan_path(SEGMENT_3)
    path.parent.mkdir(parents=True)
    item = next(row for row in tracker["work_items"] if row["id"] == SEGMENT_3)

    def checked(status: str, emits: str, moves: list | None = None, amended: bool = False) -> dict:
        current = copy.deepcopy(tracker)
        next(row for row in current["work_items"] if row["id"] == SEGMENT_3)["status"] = status
        if amended:
            next(row for row in current["stages"] if row["name"] == "source-correlation")["amendments"] = [
                {"id": SECOND, "status": "open", "item": SEGMENT_3, "applies": [f"{SEGMENT_3}-apply"]}]
        document = copy.deepcopy(other)
        document["header_emits"][0]["header"] = emits
        if moves is not None:
            document["header_moves"] = moves
        path.write_text(json.dumps(document), encoding="utf-8")
        return validate_source_plan(root, current, plan, graph, section_of=MAIN)

    assert item["status"] != "accepted"
    still = f"{SEGMENT_3} (accepted) still names {OLD} in a header-emit row; it must name {NEW} and state the same move"
    # An accepted plan that still names the old header is a problem; one in review or under an open amendment a note.
    report = checked("accepted", OLD)
    assert any(still in line for line in report["problems"]), report["problems"]
    for status, amended, where in (("awaiting_acceptance", False, "awaiting_acceptance"), ("ready", True, f"ready, amended by {SECOND}")):
        report = checked(status, OLD, amended=amended)
        assert report["ok"] and any(f"{SEGMENT_3} ({where}) still names {OLD}" in line for line in report["review"]), report
    # A plan nobody accepted or amended (still being drafted) is not compared.
    report = checked("ready", OLD)
    assert report["ok"] and not any(SEGMENT_3 in line for line in report["review"])
    same = [{"from": OLD, "to": NEW, "reason": "r", "evidence": ["e"]}]
    assert checked("accepted", NEW, same)["ok"]
    report = checked("accepted", NEW)
    assert any(f"{SEGMENT_3} (accepted) emits into {NEW} without stating the move" in line for line in report["problems"])
    report = checked("accepted", "src/gamez/zBaz/other.h", [{**same[0], "to": "src/gamez/zBaz/other.h"}])
    assert any(f"contradicts {SEGMENT_3} (accepted)'s {OLD} -> src/gamez/zBaz/other.h" in line for line in report["problems"])
    # The other way round: a plan that states nothing learns of the accepted plan's move.
    unmoved = segment_plan(graph)
    path.write_text(json.dumps({**other, "header_emits": [{**other["header_emits"][0], "header": NEW}], "header_moves": same}),
                    encoding="utf-8")
    current = copy.deepcopy(tracker)
    next(row for row in current["work_items"] if row["id"] == SEGMENT_3)["status"] = "accepted"
    report = validate_source_plan(root, current, unmoved, graph, section_of=MAIN)
    assert any(f"{SEGMENT_3} (accepted) moves {OLD} to {NEW}: this plan's header-emit rows still name {OLD}" in line
               for line in report["problems"]), report["problems"]


def test_the_gate_holds_every_accepted_plan_to_a_stated_move() -> None:
    def plan(emits: list[str], moves: list[tuple[str, str]] = ()) -> dict:
        return {"header_emits": [{"artifact": "a", "header": header, "reason": "inline"} for header in emits],
                "header_moves": [{"from": source, "to": target, "reason": "r", "evidence": ["e"]} for source, target in moves]}

    stated = plan([NEW], [(OLD, NEW)])
    assert header_move_conflicts([("p1", plan([OLD]), True), ("p2", plan(["src/x.h"]), True)]) == []
    assert header_move_conflicts([("p1", stated, True), ("p2", stated, True), ("d", plan([NEW]), False)]) == []
    problems = header_move_conflicts([("p1", stated, True), ("p2", plan([OLD]), True), ("p3", plan([NEW]), True), ("d", plan([OLD]), False)])
    assert problems == [
        f"p1: header_moves {OLD} -> {NEW}: p2 still names {OLD} in a header-emit row; it must name {NEW} and state the same move",
        f"p1: header_moves {OLD} -> {NEW}: p3 emits into {NEW} without stating the move",
        f"p1: header_moves {OLD} -> {NEW}: d still names {OLD} in a header-emit row; it must name {NEW}",
    ]
    # Two statements about one header that differ are reported once.
    problems = header_move_conflicts([("p1", stated, True), ("p2", plan(["src/y.h"], [(OLD, "src/y.h")]), True)])
    assert problems == [f"p1: header_moves {OLD} -> {NEW} contradicts p2's {OLD} -> src/y.h"]


# -- includers ------------------------------------------------------------------------------------


def test_includers_are_listed_by_kind_and_the_tools_rewrite_none(tmp_path: Path) -> None:
    files = {
        "src/gamez/zFoo/zfoo.h": HEADER,
        "src/gamez/zFoo/zfoo_types.h": "typedef int box_t;\n",
        "src/gamez/zFoo/near.cpp": '#include "zfoo.h"\n#include "zfoo_other.h"\n',
        "src/gamez/zBar/far.cpp": ('// a comment naming zfoo.h\n/* @socom-skeleton decl include */\n#include "gamez/zFoo/zfoo.h"\n'
                                   '/* @socom-skeleton end include */\n#  include "gamez/zFoo/zfoo.h" /* authored */\n'),
        "src/gamez/zBar/zfoo.h": "// another header of the same name\n",
        "src/gamez/zBar/own.cpp": '#include "zfoo.h"\n',
        "port/hooks/hook.cpp": '#include <gamez/zFoo/zfoo.h>\n',
        "build/ignored.cpp": '#include "gamez/zFoo/zfoo.h"\n',
    }
    for path, text in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    before = {path: (tmp_path / path).read_bytes() for path in files}
    tracker = {"work_items": [{"id": APPLY_1, "kind": ORDER_APPLY_KIND, "resources": ["src/gamez/zBar/far.cpp"]}]}
    rows = includers(tmp_path, tracker, OLD, NEW)
    assert [(row["path"], row["line"], row["kind"], row.get("item"), row["suggested"]) for row in rows] == [
        ("src/gamez/zBar/far.cpp", 3, "fenced", APPLY_1, '#include "gamez/zBaz/b_box.h"'),
        ("src/gamez/zBar/far.cpp", 5, "authored", None, '#include "gamez/zBaz/b_box.h"'),
        ("src/gamez/zFoo/near.cpp", 1, "authored", None, '#include "gamez/zBaz/b_box.h"'),
        ("port/hooks/hook.cpp", 1, "authored", None, '#include "gamez/zBaz/b_box.h"'),
    ]
    assert include_spelling(NEW, UNIT_B) == "b_box.h"
    assert own_relative_includes(tmp_path, OLD, NEW) == [
        {"line": 3, "text": '#include "zfoo_types.h"', "suggested": '#include "gamez/zFoo/zfoo_types.h"'}]
    (report,) = header_move_report(tmp_path, {"work_items": [], "stages": []}, [(OLD, NEW)])
    assert report["from_exists"] and not report["to_exists"]
    assert report["stale_fenced"] == ["src/gamez/zBar/far.cpp"] and len(report["stale_authored"]) == 3
    assert {path: (tmp_path / path).read_bytes() for path in files} == before
    # With the item's stored render the region is read exactly: a line the port lane added inside it is authored.
    render = b'/* @socom-skeleton decl include */\n#include "gamez/zBar/zbar.h"\n/* @socom-skeleton end include */\n'
    put_blob(tmp_path, render)
    tracker["work_items"][0]["order_skeleton"] = {"files": [{"path": "src/gamez/zBar/far.cpp", "rendered_sha256": sha(render)}]}
    rows = [row for row in includers(tmp_path, tracker, OLD, NEW) if row["path"] == "src/gamez/zBar/far.cpp"]
    assert [(row["line"], row["kind"], row.get("in_region"), row.get("item")) for row in rows] == [
        (3, "authored", True, None), (5, "authored", None, None)]
    generated = render.replace(b"gamez/zBar/zbar.h", b"gamez/zFoo/zfoo.h")
    put_blob(tmp_path, generated)
    tracker["work_items"][0]["order_skeleton"]["files"][0]["rendered_sha256"] = sha(generated)
    rows = [row for row in includers(tmp_path, tracker, OLD, NEW) if row["path"] == "src/gamez/zBar/far.cpp"]
    assert [(row["line"], row["kind"], row.get("item")) for row in rows] == [(3, "fenced", APPLY_1), (5, "authored", None)]


# -- stage 5: the frozen base, the snapshot, the reservations, the merge ancestor --------------------------


BLOCK = (
    "/* socom-owner-annotations begin socom:work:source-segment-001\n"
    " * Generated by source annotate from the accepted owner plan; do not edit.\n"
    " * @socom-artifact emits .text socom:function:0x100010\n"
    " * socom-owner-annotations end socom:work:source-segment-001 */\n"
)
AMENDMENT = "socom:source-amendment:009"
STAGE4_APPLY = "socom:work:source-segment-001-apply"


def _moved_tracker(*, kind: str | None = "header", retired: list[dict] | None = None) -> dict:
    move = {"from": OLD, "to": NEW, **({"kind": kind} if kind else {})}
    return {
        "stages": [{"name": "source-correlation", "amendments": [{"id": AMENDMENT, "applies": [STAGE4_APPLY]}]}],
        "work_items": [{"id": STAGE4_APPLY, "kind": "source-apply-segment", "source_apply": {
            "files": [{"path": NEW}], "moves": [move], "retired": retired or [], "removed": [OLD]}}],
    }


def _moved_tree(tmp_path: Path) -> tuple[Path, bytes, str]:
    """The base holds the provisional header at the old path; src/ holds the moved, port-edited header with new blocks."""

    base = tmp_path / BASE_DIR
    old = (BLOCK + "\n" + HEADER).encode().replace(b"\n", b"\r\n")
    (base / OLD).parent.mkdir(parents=True)
    (base / OLD).write_bytes(old)
    (base / "src/gamez/zFoo/other.cpp").write_bytes(b"int other;\n")
    new_block = BLOCK.replace("0x100010", "0x100018")
    (tmp_path / NEW).parent.mkdir(parents=True)
    (tmp_path / NEW).write_bytes((new_block + "\n" + HEADER_RENDER.replace("public:\n", "public:\n" + PORT_EDIT)).encode())
    return base, old, new_block


def test_the_frozen_base_follows_a_recorded_header_move_and_nothing_else(tmp_path: Path) -> None:
    base, old, new_block = _moved_tree(tmp_path)
    tracker = _moved_tracker()
    assert recorded_header_moves(tracker) == {OLD: NEW} == base_header_moves(tmp_path, tracker, [AMENDMENT])
    changes = base_changes(tmp_path, tracker, [AMENDMENT])
    # The base's own authored content (never the skeleton or the port edits) under the current blocks, at the new path.
    assert changes == {NEW: (new_block + "\n" + HEADER).encode().replace(b"\n", b"\r\n"), OLD: None}
    assert with_blocks(changes[NEW], parse_blocks(old.decode())[1]) == old
    # A move stage 4 did not record as a header move, a retirement, and an occupied target still refuse.
    with pytest.raises(SocomError, match="a stage 4 move after the skeleton wave"):
        base_changes(tmp_path, _moved_tracker(kind=None), [AMENDMENT])
    with pytest.raises(SocomError, match=r"other\.cpp \(a stage 4 retirement after the skeleton wave\)"):
        base_changes(tmp_path, _moved_tracker(retired=[{"path": "src/gamez/zFoo/other.cpp"}]), [AMENDMENT])
    with pytest.raises(SocomError, match=r"zfoo\.h \(a stage 4 retirement after the skeleton wave\)"):
        base_changes(tmp_path, {**tracker, "work_items": [{**tracker["work_items"][0], "source_apply": {
            "files": [{"path": NEW}], "moves": [], "retired": [{"path": OLD}]}}]}, [AMENDMENT])
    (base / NEW).parent.mkdir(parents=True)
    (base / NEW).write_bytes(b"// another file\n")
    with pytest.raises(SocomError, match="already holds a file at the header's new path"):
        base_changes(tmp_path, tracker, [AMENDMENT])


def test_the_body_snapshot_is_re_keyed_for_a_moved_header(tmp_path: Path) -> None:
    from tools._socom.order_skeleton import source_digest
    from tools._socom.order_skeleton_write import DECISIONS_KIND, decisions_path

    base, _old, _new_block = _moved_tree(tmp_path)
    tracker = {**_moved_tracker(), "work_items": _moved_tracker()["work_items"] + [
        {"id": ORDER_SKELETON_PREPARE_ID, "kind": "order-skeleton-prepare"}]}
    snapshot = _write_snapshot(tmp_path, [("src/gamez/zFoo/other.cpp", 1, "int other;"), (OLD, *BODY)])
    assert [row["id"] for row in snapshot["bodies"]] == ["src/gamez/zFoo/other.cpp:1", f"{OLD}:8"]
    changes = base_changes(tmp_path, tracker, [AMENDMENT])
    moves = base_header_moves(tmp_path, tracker, [AMENDMENT])
    sealed = snapshot_reseal(tmp_path, tracker, changes, tmp_path / SNAPSHOT_PATH, moves)
    document = sealed.pop("document")
    assert sealed["resealed"] and sealed["moved"] == [{"from": OLD, "to": NEW, "bodies": 1}]
    assert sealed["rekeyed"] == [{"from": f"{OLD}:8", "to": f"{NEW}:8"}] and "re-keyed to the new path" in sealed["why"]
    # Only the key moves: the same text, digest and lines, kept in path and line order.
    assert [(row["id"], row["path"]) for row in document["bodies"]] == [
        (f"{NEW}:8", NEW), ("src/gamez/zFoo/other.cpp:1", "src/gamez/zFoo/other.cpp")]
    moved = next(row for row in document["bodies"] if row["path"] == NEW)
    assert {key: moved[key] for key in ("span", "sha256", "text")} == {key: snapshot["bodies"][1][key] for key in ("span", "sha256", "text")}
    assert document["bodies"][1] == snapshot["bodies"][0]
    # The re-sealed digest is the advanced base's.
    (base / NEW).parent.mkdir(parents=True)
    (base / NEW).write_bytes(changes[NEW])
    (base / OLD).unlink()
    assert document["src_sha256"] == sealed["src_sha256"] == source_digest(base) != sealed["src_sha256_before"]
    (base / OLD).write_bytes((BLOCK + "\n" + HEADER).encode().replace(b"\n", b"\r\n"))
    (base / NEW).unlink()

    # A delta that is not the recorded move, changed authored content, and a decision keyed by a moved body refuse.
    with pytest.raises(SocomError, match="leaves the base without a recorded header move"):
        snapshot_reseal(tmp_path, tracker, changes, tmp_path / SNAPSHOT_PATH)
    with pytest.raises(SocomError, match="the moved header's authored content changes"):
        snapshot_reseal(tmp_path, tracker, {**changes, NEW: changes[NEW].replace(b"return 1", b"return 2")}, tmp_path / SNAPSHOT_PATH, moves)
    decisions = tmp_path / decisions_path(ORDER_SKELETON_PREPARE_ID)
    decisions.parent.mkdir(parents=True)
    decisions.write_text(json.dumps({"kind": DECISIONS_KIND, "schema_version": 1, "work_item_id": ORDER_SKELETON_PREPARE_ID, "decisions": [
        {"kind": "overload-tie", "key": f"{OLD}:8", "value": "Get__4CBoxFv", "basis": "the only candidate"}]}), encoding="utf-8")
    with pytest.raises(SocomError, match="decisions are keyed by bodies of a moved header"):
        snapshot_reseal(tmp_path, tracker, changes, tmp_path / SNAPSHOT_PATH, moves)


def _skeleton_row(path: str, action: str, base: bytes | None, render: bytes) -> dict:
    return {"path": path, "action": action, "base_sha256": sha(base), "base_content_sha256": content_sha256(base) if base else None,
            "before_sha256": sha(base), "before_content_sha256": content_sha256(base) if base else None,
            "stage4_blocks_sha256": blocks_sha256(base), "ancestor_sha256": sha(base), "rendered_sha256": sha(render),
            "after_sha256": sha(render), "after_stage4_blocks_sha256": blocks_sha256(render), "merge": "render"}


def test_the_item_that_reserved_the_old_path_reserves_the_new_one_and_keeps_its_merge_ancestor(tmp_path: Path) -> None:
    render = (BLOCK + "\n" + HEADER_RENDER).encode()
    unit = (BLOCK + '\n/* @socom-skeleton decl include */\n#include "gamez/zFoo/zfoo.h"\n/* @socom-skeleton end include */\n').encode()
    prepare = {"id": ORDER_SKELETON_PREPARE_ID, "kind": "order-skeleton-prepare", "status": "blocked",
               "resources": ["src/gamez/zBar/zbar.h", OLD], "batch": {"files": ["src/gamez/zBar/zbar.h", OLD]},
               "order_skeleton": {"files": [_skeleton_row(OLD, "header", (BLOCK + "\n" + HEADER).encode(), render)]}}
    apply = {"id": APPLY_3, "kind": ORDER_APPLY_KIND, "status": "accepted", "resources": [UNIT_B], "batch": {"files": [UNIT_B]},
             "order_skeleton": {"files": [_skeleton_row(UNIT_B, "unit", BLOCK.encode(), unit)]}}
    tracker = _moved_tracker()
    tracker["work_items"] += [prepare, apply]
    rows = follow_header_moves(tracker, [AMENDMENT])
    assert rows == [{"from": OLD, "to": NEW, "item": ORDER_SKELETON_PREPARE_ID}]
    assert prepare["resources"] == prepare["batch"]["files"] == ["src/gamez/zBar/zbar.h", NEW]
    # The record keeps its row at the old path until the re-apply; the merge there starts from that row's render.
    prior = _prior_rows(tracker, prepare)
    assert OLD not in prior and prior[NEW]["path"] == NEW and prior[NEW]["rendered_sha256"] == sha(render)
    assert _prior_rows({**tracker, "work_items": tracker["work_items"][1:]}, prepare)[OLD]["path"] == OLD  # no recorded move
    # The apply whose stored render generates an include of the old path in its region is found for the re-apply.
    found = [{"path": UNIT_B, "item": APPLY_3, "from": OLD, "to": NEW}]
    (tmp_path / UNIT_B).parent.mkdir(parents=True)
    (tmp_path / UNIT_B).write_bytes(unit)
    assert fenced_includers(tmp_path, tracker, {OLD: NEW}) == found  # no render stored: the live region decides
    put_blob(tmp_path, unit)
    (tmp_path / UNIT_B).write_bytes(unit.replace(b"gamez/zFoo/zfoo.h", b"b_box.h"))  # a hand edit hides nothing
    assert fenced_includers(tmp_path, tracker, {OLD: NEW}) == found
    assert fenced_includers(tmp_path, tracker, {"src/gamez/zFoo/none.h": NEW}) == []
    # An include the port lane added inside the region is not generated: its item is not sent back for it.
    plain = unit.replace(b'#include "gamez/zFoo/zfoo.h"\n', b'#include "other.h"\n')
    put_blob(tmp_path, plain)
    apply["order_skeleton"]["files"][0].update(rendered_sha256=sha(plain), after_sha256=sha(plain))
    (tmp_path / UNIT_B).write_bytes(unit)
    assert fenced_includers(tmp_path, tracker, {OLD: NEW}) == []
    apply["order_skeleton"]["files"][0].update(rendered_sha256=sha(unit), after_sha256=sha(unit))
    # Another item's reservation of the new path is a contradiction, never silently merged.
    tracker = _moved_tracker()
    tracker["work_items"] += [{**prepare, "resources": [OLD]}, {**apply, "resources": [NEW]}]
    with pytest.raises(SocomError, match=f"moved to {NEW}, which {APPLY_3} reserves already"):
        follow_header_moves(tracker, [AMENDMENT])


def test_an_authored_include_of_a_moved_header_counts_as_the_new_path() -> None:
    from tools._socom.order_skeleton_headers import _included

    scan = SimpleNamespace(includes=["gamez/zFoo/zfoo.h", "local.h"])
    plain = _included(UNIT_A, scan)
    assert OLD in plain and NEW not in plain and "src/gamez/zBar/local.h" in plain
    # The frozen base keeps its #include lines: no include region and no forward declaration is generated for them.
    assert _included(UNIT_A, scan, {OLD: NEW}) == plain | {NEW}
    assert _included(UNIT_A, None, {OLD: NEW}) == set()


# -- the whole route on the synthetic workspace ------------------------------------------------------


def _graph_with_an_inline_b() -> dict:
    graph = synthetic_graph()
    row = graph["artifacts"][5]  # b_main: an inline instance, so segment 3 may emit it from the header too
    row["binding"] = "13"
    row["names"][0]["binding"] = "13"
    graph["graph_sha256"] = graph_digest(graph)
    return graph


def _plans_sharing_the_header(graph: dict) -> dict[str, dict]:
    chosen = test_source_apply.plans(graph)
    plan = chosen[SEGMENT_3]
    plan["header_emits"] = [{"artifact": plan["owners"][0]["artifacts"][0], "header": OLD, "reason": "inline",
                             "evidence": ["binding 13 instance; class CBox"]}]
    plan["annotations"] = derive_annotations(plan, graph, MAIN)
    return chosen


@pytest.fixture()
def emitters(request, monkeypatch) -> bool:
    """Whether segment 3 emits from the header as well (two plans then state the move): set before the workspace is built."""

    both = bool(getattr(request, "param", True))
    if both:
        monkeypatch.setattr(test_source_apply, "synthetic_graph", _graph_with_an_inline_b)
        monkeypatch.setattr(test_source_gate, "plans", _plans_sharing_the_header)
    return both


def _blocks(root: Path, path: str) -> dict[str, str]:
    return parse_blocks((root / path).read_bytes().decode("utf-8"))[1]


def _unit_render(root: Path, include: str) -> bytes:
    region = f'/* @socom-skeleton decl include */\n#include "{include}"\n/* @socom-skeleton end include */\n'
    return with_blocks((region + "\n/* @socom-skeleton stub b_main__Fv */\nvoid b_main()\n{\n}\n").encode(), _blocks(root, UNIT_B))


def _skeleton_wave(root: Path) -> dict[str, bytes]:
    """The skeleton route as the wave left it: the prepare accepted with the header's record, segment 3's apply accepted
    with b.cpp's (an include region naming the header), the base frozen before the wave, src/ port-edited after it."""

    from tools._socom.capabilities import capability_opening
    from tools._socom.order_plan import ORDER_SKELETON_ROUTE_ID, add_skeleton_prepare
    from tools._socom.order_skeleton_route import (
        ACCEPT_ROUTE, HANDOFF_ROUTE, RECORD_CITATION, RECORD_KIND, _digest, record_sha256, record_skeleton,
    )
    from tools._socom.tracker import open_capability_gate

    # src/ before the wave: the provisional header with its content, a.cpp and a test hook including it by hand.
    (root / OLD).write_bytes(with_blocks(HEADER.encode(), _blocks(root, OLD)))
    (root / "src/gamez/zFoo/zfoo_types.h").write_bytes(b"typedef int box_t;\n")
    (root / UNIT_A).write_bytes(with_blocks(b'#include "gamez/zFoo/zfoo.h"\n// provisional\n', _blocks(root, UNIT_A)))
    (root / HOOK).parent.mkdir(parents=True)
    (root / HOOK).write_bytes(b'#include "gamez/zFoo/zfoo.h"\n')
    base = root / BASE_DIR
    shutil.copytree(root / "src", base / "src")
    _write_snapshot(root, [(OLD, *BODY)])
    # The wave: the header gets its class region, b.cpp its include region and stub; then the port lane edits both.
    renders = {OLD: with_blocks(HEADER_RENDER.encode(), _blocks(root, OLD)), UNIT_B: _unit_render(root, "gamez/zFoo/zfoo.h")}
    (root / OLD).write_bytes(renders[OLD].replace(b"public:\n", b"public:\n" + PORT_EDIT.encode()))
    (root / UNIT_B).write_bytes(renders[UNIT_B].replace(b"{\n}\n", b"{\n\tport_main();\n}\n"))
    for data in renders.values():
        put_blob(root, data)

    tracker = _load(root)
    commands = set((capability_opening(ORDER_SKELETON_ROUTE_ID) or {}).get("commands") or [])
    open_capability_gate(tracker, ORDER_SKELETON_ROUTE_ID, commands)
    refresh_ready_and_stages(tracker)
    units = {row["id"]: sorted(f"{row['batch']['directories'][0]}/{unit}" for unit in row["batch"]["units"])
             for row in tracker["work_items"] if row.get("kind") == ORDER_APPLY_KIND}
    assert units == {APPLY_1: [UNIT_A], APPLY_3: [UNIT_B]}
    add_skeleton_prepare(tracker, prepare_files=[OLD], unit_files=units, manifest_sha256="m" * 64, write_sha256="w" * 64,
                         counts={"header": 1})
    items = {row["id"]: row for row in tracker["work_items"]}
    for item_id, path, action in ((ORDER_SKELETON_PREPARE_ID, OLD, "header"), (APPLY_3, UNIT_B, "unit")):
        row = _skeleton_row(path, action, (base / path).read_bytes(), renders[path])
        record = {"kind": RECORD_KIND, "schema_version": 1, "item": item_id, "applied_by": "worker-p", "files": [row],
                  "files_sha256": _digest([row]),
                  "inputs": {"manifest_sha256": "m" * 64, "snapshot_sha256": "s" * 64, "base_tree_sha256": "t" * 64,
                             "stage4_baseline_sha256": "4" * 64},
                  "write_sha256": "w" * 64, "known_conflicts": [], "waiting": [], "waiting_by_kind": {}, "flags": {}, "decisions": None}
        item = items[item_id]
        record_skeleton(item, record, "2026-11-02T00:00:00Z")
        item.update(status="accepted", lease=None, handoff={"owner": "worker-p", "summary": "applied", "route": HANDOFF_ROUTE},
                    accepted={"by": "verifier-p", "at": "2026-11-02T00:00:00Z", "route": ACCEPT_ROUTE})
        item["evidence"] = sorted(set(item["evidence"]) | {f"{RECORD_CITATION}{record_sha256(item['order_skeleton'])}"})
    _save(root, tracker)
    return renders


def _tree(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.mark.parametrize("emitters", [True, False], indirect=True, ids=["two-plans", "one-plan"])
def test_a_header_moves_through_stage_4_and_stage_5_follows_it(
    emitters: bool, amendable: tuple[Path, dict, str], capsys, monkeypatch
) -> None:
    from tools._socom.order_skeleton import source_digest

    root, graph, _gap = amendable
    assert _decompose(root, capsys)[0] == 0
    _accept_order_plans(root, capsys)
    renders = _skeleton_wave(root)
    live_header = (root / OLD).read_bytes()
    base_before = _tree(root / BASE_DIR)
    amended = [(SEGMENT_1, FIRST)] + ([(SEGMENT_3, SECOND)] if emitters else [])
    names = tuple(name for _item, name in amended)

    # Open the amendments, then their stage 5 side: the prepare reserves the header, so it is sent back for each.
    for item, name in amended:
        code, report = _amend(root, capsys, item, reason="user decision: CBox's header goes next to b.cpp")
        assert code == 0 and report["amendment"] == name, report
    for _item, name in amended:
        code, report = _run(capsys, "--root", str(root), "progress", "reopen-order-skeleton", "--amendment", name, "--by",
                            "socom-reopener-r4", "--reason", "the header moves", "--evidence", f"{name} opened",
                            "--expected-revision", _revision(root))
        assert code == 0 and ORDER_SKELETON_PREPARE_ID in report["reopening"]["items"], report
    held = {key for row in _stage5(root)["reopenings"] for key in row["items"]}
    assert (APPLY_3 in held) == emitters

    # The revised plans state the move once each; segment 1's reservation is corrected for the new directory.
    revised = {SEGMENT_1: _moved(_plan(root, SEGMENT_1), graph, directories=["src/gamez/zFoo", "src/gamez/zBar", "src/gamez/zBaz"])}
    if emitters:
        revised[SEGMENT_3] = _moved(_plan(root, SEGMENT_3), graph)
    candidate = root / "build" / "candidate.json"
    candidate.write_text(json.dumps(revised[SEGMENT_1]), encoding="utf-8")
    code, valid = _run(capsys, "--root", str(root), "source", "plan", "validate", "--plan", "build/candidate.json")
    assert code == 0 and valid["ok"], valid
    (row,) = valid["header_moves"]
    assert row["state"] == "pending" and [(entry["path"], entry["kind"], entry.get("item")) for entry in row["includers"]] == [
        (UNIT_A, "authored", None), (UNIT_B, "fenced", APPLY_3), (HOOK, "authored", None)]
    assert row["own_relative_includes"][0]["suggested"] == '#include "gamez/zFoo/zfoo_types.h"'
    if emitters:
        # The other plan is still the accepted one under revision: a note now, a gate problem if it stayed.
        assert any(f"{SEGMENT_3} (ready, amended by {SECOND}) still names {OLD}" in line for line in valid["review"]), valid["review"]
    for item, plan in revised.items():
        _revise(root, capsys, item, plan)

    # Stage 4 re-apply: the first apply moves the file with its content; a second one that states the move finds it done.
    _claim(root, capsys, f"{SEGMENT_1}-apply", owner="worker-2")
    code, report = _run(capsys, "--root", str(root), "source", "annotate", "--plan", plan_path(SEGMENT_1), "--check")
    assert code == 1 and {"path": f"{OLD} -> {NEW}", "state": "pending-move"} in report["drift"], report
    code, report = test_source_apply._apply(root, capsys, f"{SEGMENT_1}-apply", "--dry-run", owner="worker-2")
    performed = {"from": OLD, "to": NEW, "kind": "header", "performed": True}
    assert code == 0 and performed in report["record"]["moves"], report
    assert report["header_moves"][0]["stale_fenced"] == [UNIT_B] and (root / OLD).is_file() and not (root / NEW).exists()
    code, report = _run(capsys, "--root", str(root), "progress", "work", "release", "--item", f"{SEGMENT_1}-apply", "--owner",
                        "worker-2", "--expected-revision", _revision(root))
    assert code == 0, report
    applied = _reapply(root, capsys, f"{SEGMENT_1}-apply")
    # Beside the unit move the first apply made long ago, the record lists the header move.
    assert applied["record"]["moves"] == [{"from": "src/gamez/zFoo/a.cpp", "to": UNIT_A}, performed]
    assert sorted(applied["record"]["changed"]) == sorted([NEW, OLD])
    assert not (root / OLD).exists()
    moved = (root / NEW).read_bytes()
    # The authored content went with the file, byte for byte: the include guard, the region, the port edit.
    assert parse_blocks(moved.decode())[2] == parse_blocks(live_header.decode())[2] and PORT_EDIT.encode() in moved
    assert b"#ifndef ZFOO_H" in moved and set(_blocks(root, NEW)) == ({SEGMENT_1, SEGMENT_3} if emitters else {SEGMENT_1})
    (move,) = applied["header_moves"]
    assert (move["from_exists"], move["to_exists"]) == (False, True) and "include guard" in move["authored_content"]
    assert move["stale_authored"] == [HOOK, UNIT_A] and move["stale_fenced"] == [UNIT_B]
    assert move["fenced_items"] == [{"item": APPLY_3, "held_by": next(iter(sorted(
        row["id"] for row in _stage5(root)["reopenings"] if APPLY_3 in row["items"])), None)}]
    item = next(row for row in _load(root)["work_items"] if row["id"] == f"{SEGMENT_1}-apply")
    assert f"source-moved {OLD} -> {NEW} header" in item["evidence"]
    assert item["resources"] == ["src/gamez/zBar", "src/gamez/zBaz", "src/gamez/zFoo"]
    if emitters:
        before = _tree(root / "src")
        second = _reapply(root, capsys, f"{SEGMENT_3}-apply")
        assert second["record"]["moves"] == [{**performed, "performed": False}]
        assert second["record"]["changed"] == [] and _tree(root / "src") == before
    for item_id, _name in amended:
        code, report = _run(capsys, "--root", str(root), "source", "apply-check", "--item", f"{item_id}-apply")
        assert code == 0 and report["problems"] == [] and report["header_moves"][0]["to_exists"], report
        code, report = _run(capsys, "--root", str(root), "source", "annotate", "--plan", plan_path(item_id), "--check")
        assert code == 0 and report["drift"] == [], report
    # An undone move fails the check; the worker's hand edits (include guard, includers) are drift, never a failure.
    (root / OLD).write_bytes(moved)
    code, report = _run(capsys, "--root", str(root), "source", "apply-check", "--item", f"{SEGMENT_1}-apply")
    assert code == 1 and any(f"{OLD} was removed by the apply but exists" in line for line in report["problems"]), report
    (root / OLD).unlink()
    edited = moved.replace(b"ZFOO_H", b"B_BOX_H").replace(b'#include "zfoo_types.h"', b'#include "gamez/zFoo/zfoo_types.h"')
    (root / NEW).write_bytes(edited)
    (root / UNIT_A).write_bytes((root / UNIT_A).read_bytes().replace(b"gamez/zFoo/zfoo.h", b"gamez/zBaz/b_box.h"))
    (root / HOOK).write_bytes(b'#include "gamez/zBaz/b_box.h"\n')
    code, report = _run(capsys, "--root", str(root), "source", "apply-check", "--item", f"{SEGMENT_1}-apply")
    assert code == 0 and NEW in report["drift"] and report["header_moves"][0]["stale_authored"] == [], report
    assert report["header_moves"][0]["own_relative_includes"] == [] and report["header_moves"][0]["stale_fenced"] == [UNIT_B]

    # The amendments are accepted together: every gate check passes with the header at its new path.
    _receipt(monkeypatch, _stage3_receipt(root))
    code, accepted = _accept_amendment(root, capsys, amendments=names)
    assert code == 0 and accepted["stage_status"] == "accepted", accepted
    code, report = _run(capsys, "--root", str(root), "source", "gate-check", "--deferrals", DEFERRALS)
    assert code == 0 and report["ok"], report

    # Stage 5 follows the move instead of refusing it.
    rebase = ["--root", str(root), "progress", "rebase-function-order", "--by", "socom-rebaser-r5", "--reason",
              "absorb the header move", "--evidence", "accept-source-amendment recorded the baseline"]
    code, preview = _run(capsys, *rebase, "--expected-revision", _revision(root), "--dry-run")
    assert code == 0 and preview["errors"] == [], preview
    assert preview["rebase"]["base"]["header_moves"] == [{"from": OLD, "to": NEW}]
    assert _tree(root / BASE_DIR) == base_before
    code, report = _run(capsys, *rebase, "--expected-revision", _revision(root))
    assert code == 0, report
    entry = report["rebase"]
    assert entry["header_moves"] == [{"from": OLD, "to": NEW, "item": ORDER_SKELETON_PREPARE_ID,
                                      "fenced_includers": [{"path": UNIT_B, "item": APPLY_3}]}]
    reopened = {row["item"]: row["why"] for row in entry["reopened"]}
    if emitters:
        assert APPLY_3 not in reopened  # held by its own amendment's reopening: re-applied anyway
    else:
        # Segment 3 was not amended: its apply is sent back because its include region names the moved header.
        assert "name a header stage 4 moved" in reopened[APPLY_3] and UNIT_B in reopened[APPLY_3]
    tracker = _load(root)
    items = {row["id"]: row for row in tracker["work_items"]}
    prepare = items[ORDER_SKELETON_PREPARE_ID]
    assert prepare["resources"] == prepare["batch"]["files"] == [NEW]
    assert items[APPLY_3]["status"] != "accepted" and audit_tracker(tracker, strict=True) == []
    # The base's copy moved with its own authored content under the current blocks; nothing else in the base changed.
    base_after = _tree(root / BASE_DIR)
    assert f"{OLD}" not in base_after and base_after[NEW] == with_blocks(HEADER.encode(), _blocks(root, NEW))
    changed = {path for path in set(base_before) | set(base_after) if base_before.get(path) != base_after.get(path)}
    assert changed == {OLD, NEW}
    history = report["rebase"]["base"]["history"]
    assert history.startswith(f"{ROUTE_DIR}/base-history/") and (root / history / OLD).read_bytes() == base_before[OLD]
    # The snapshot's body is re-keyed, and its digest is the advanced base's.
    sealed = entry["base"]["snapshot"]
    stored = json.loads((root / SNAPSHOT_PATH).read_text(encoding="utf-8"))
    assert sealed["moved"] == [{"from": OLD, "to": NEW, "bodies": 1}] and sealed["rekeyed"] == [{"from": f"{OLD}:8", "to": f"{NEW}:8"}]
    assert [(row["id"], row["path"], row["text"]) for row in stored["bodies"]] == [(f"{NEW}:8", NEW, BODY[1])]
    assert stored["src_sha256"] == sealed["src_sha256"] == source_digest(root / BASE_DIR)
    assert preview["rebase"]["base"]["snapshot"]["snapshot_sha256"] == sealed["snapshot_sha256"] == stored["snapshot_sha256"]

    # The reopened order plans are re-planned as in phase A.
    for item_id in sorted(key for key, row in items.items() if row.get("kind") == "order-plan-segment" and row["status"] != "accepted"):
        _claim(root, capsys, item_id, owner="planner-9")
        code, drafted = _run(capsys, "--root", str(root), "order", "plan", "draft", "--item", item_id)
        assert code == 0, drafted
        assert _handoff(root, capsys, item_id, "planner-9", _cited(root, item_id))[0] == 0
        assert _accept(root, capsys, item_id)[0] == 0
    tracker = _load(root)
    items = {row["id"]: row for row in tracker["work_items"]}
    assert audit_tracker(tracker, strict=True) == []

    # The skeleton re-apply merges the moved header from its own previous render: the same render keeps src/ as it is.
    render = with_blocks(HEADER_RENDER.encode(), _blocks(root, NEW))
    assert sha(render) == sha(renders[OLD])  # the blocks name no path: the header renders as before
    rendered = {"files": {NEW: render}, "manifest": {"files": [{"path": NEW, "action": "header"}], "deleted": []}}
    rows, changes, _blobs = _merge_scope(root, tracker, items[ORDER_SKELETON_PREPARE_ID], rendered, root / BASE_DIR, None)
    assert [(row["path"], row["merge"], row["ancestor_sha256"]) for row in rows] == [(NEW, "kept", sha(renders[OLD]))]
    assert changes == {} and (root / NEW).read_bytes() == edited
    # The unit's include region is rewritten by its item's re-apply; the port edit beside it stays.
    unit = _unit_render(root, "b_box.h")
    rendered = {"files": {UNIT_B: unit}, "manifest": {"files": [{"path": UNIT_B, "action": "unit"}], "deleted": []}}
    rows, changes, _blobs = _merge_scope(root, tracker, items[APPLY_3], rendered, root / BASE_DIR, None)
    assert rows[0]["merge"] == "clean" and b'#include "b_box.h"' in changes[UNIT_B] and b"port_main();" in changes[UNIT_B]
    (root / UNIT_B).write_bytes(changes[UNIT_B])

    # The header is at its new path in the tree and in the base, no include names the old one, and the checks pass.
    assert (root / NEW).is_file() and not (root / OLD).exists()
    assert (root / BASE_DIR / NEW).is_file() and not (root / BASE_DIR / OLD).exists()
    assert includers(root, tracker, OLD) == []
    for item_id, _name in amended:
        code, report = _run(capsys, "--root", str(root), "source", "apply-check", "--item", f"{item_id}-apply")
        assert code == 0 and report["problems"] == [] and report["header_moves"][0]["stale_includers"] == [], report
    _receipt(monkeypatch, _stage3_receipt(root))
    code, report = _run(capsys, "--root", str(root), "source", "gate-check", "--deferrals", DEFERRALS)
    assert code == 0 and report["ok"], report
    code, report = _run(capsys, "--root", str(root), "audit", "source-baseline", "--strict")
    assert code == 0 and report["ok"], report
    code, report = _run(capsys, "--root", str(root), "progress", "audit", "--strict")
    assert code == 0 and report["ok"], report
    # A second rebase finds nothing to absorb; a retirement that is no recorded move would still be refused (unit test).
    code, refused = _run(capsys, *rebase, "--expected-revision", _revision(root))
    assert code == 2 and "nothing to absorb" in refused["error"], refused
