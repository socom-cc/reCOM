from __future__ import annotations

import copy

import pytest

from tools._socom import fingerprint
from tools._socom.ghidra import _digest
from tools._socom.util import SocomError


class _SweepBridge:
    def __init__(self, references: dict[str, list[dict]], drop: str | None = None) -> None:
        self.references = references
        self.drop = drop
        self.requested: list[str] = []

    def request(self, endpoint, **parameters):
        assert endpoint == "list_segments"
        return "\n".join(
            [
                "main: 00100000 - 00100004",
                "heap: 005e7f00 - 005e7f01",
                ".debug: .debug::00000000 - .debug::00000002",
                "not a segment line",
            ]
        )

    def post_json(self, endpoint, **body):
        assert endpoint == "get_bulk_xrefs"
        addresses = body["addresses"].split(",")
        self.requested.extend(addresses)
        return {
            address: self.references.get(address, [])
            for address in addresses
            if address != self.drop
        }


def test_segments_parse_physical_and_overlay_blocks() -> None:
    blocks = fingerprint._segments(_SweepBridge({}))
    assert blocks == [
        {"name": "main", "space": None, "start": 0x100000, "end": 0x100005},
        {"name": "heap", "space": None, "start": 0x5E7F00, "end": 0x5E7F02},
        {"name": ".debug", "space": ".debug", "start": 0, "end": 3},
    ]


def test_reference_sweep_covers_every_address_and_refuses_gaps(monkeypatch) -> None:
    monkeypatch.setattr(fingerprint, "SWEEP_CHUNK", 2)
    bridge = _SweepBridge(
        {
            "0x100004": [{"from": "00100000", "type": "DATA"}],
            ".debug::1": [{"from": "00100002", "type": "READ"}],
        }
    )
    blocks = fingerprint._segments(bridge)
    rows = fingerprint._references(bridge, blocks, lambda _message: None)
    assert bridge.requested == [
        "0x100000", "0x100001", "0x100002", "0x100003", "0x100004",
        "0x5e7f00", "0x5e7f01",
        ".debug::0", ".debug::1", ".debug::2",
    ]
    assert rows == [["00100000", "0x100004", "DATA"], ["00100002", ".debug::1", "READ"]]
    with pytest.raises(SocomError, match="did not answer every address"):
        fingerprint._references(_SweepBridge({}, drop="0x100003"), blocks, lambda _message: None)


def _fingerprint(functions, data, references) -> dict:
    sections = {
        "functions": functions,
        "data": data,
        "types": ["/project/A|4"],
        "bookmarks": {"count": 0},
        "blocks": [{"name": "main", "space": None, "start": 0, "end": 4}],
        "references": references,
    }
    digests = {name: _digest(value) for name, value in sections.items()}
    return {
        "kind": fingerprint.FINGERPRINT_KIND,
        "schema_version": fingerprint.FINGERPRINT_SCHEMA,
        "digests": digests,
        "fingerprint_sha256": _digest(digests),
        **sections,
    }


def test_fingerprint_diff_names_every_changed_signature_and_reference() -> None:
    functions = [
        {"address": "00140010", "name": "entry", "thunk": False, "external": False, "details": ["Signature: void entry(void)"]},
        {"address": "00140460", "name": "f", "thunk": True, "external": False, "details": ["Signature: undefined f(void)"]},
    ]
    data = [{"address": "00476f60", "name": "theGame", "type": "COurGame"}]
    references = [["00140010", "0x140460", "UNCONDITIONAL_CALL"]]
    before = _fingerprint(functions, data, references)
    assert fingerprint.compare_fingerprints(before, copy.deepcopy(before))["identical"] is True

    changed = copy.deepcopy(functions)
    changed[1]["details"] = ["Signature: void f(CGame * this)"]
    after = _fingerprint(changed, data, references + [["00140014", "0x476f60", "READ"]])
    diff = fingerprint.compare_fingerprints(before, after)
    assert diff["identical"] is False
    assert diff["sections_changed"] == ["functions", "references"]
    assert [(row["address"], row["fields"]) for row in diff["functions"]] == [("00140460", ["details"])]
    assert diff["references"] == {"removed": [], "added": [["00140014", "0x476f60", "READ"]]}
    assert diff["data"] == {"removed": [], "added": []}

    with pytest.raises(SocomError, match="not a schema 1 fingerprint"):
        fingerprint.compare_fingerprints(before, {**after, "schema_version": 2})
