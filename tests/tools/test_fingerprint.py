from __future__ import annotations

import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tools._socom import fingerprint
from tools._socom.ghidra import GhidraBridge, _digest
from tools._socom.util import SocomError


class _EchoHandler(BaseHTTPRequestHandler):
    """Answers each call with what it received; HTTP/1.1 keep-alive like the bridge."""

    protocol_version = "HTTP/1.1"
    peers: list = []
    drop_after_answer = False

    def do_GET(self) -> None:
        self._answer(None)

    def do_POST(self) -> None:
        self._answer(self.rfile.read(int(self.headers["Content-Length"])))

    def _answer(self, body: bytes | None) -> None:
        type(self).peers.append(self.client_address)
        if self.path.startswith("/fail"):
            status, payload = 500, b"boom"
        elif self.path.startswith("/text"):
            status, payload = 200, "not json é".encode("utf-8")
        else:
            status = 200
            payload = json.dumps(
                {"path": self.path, "body": body.decode("utf-8") if body else None, "type": self.headers.get("Content-Type")}
            ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        if type(self).drop_after_answer:
            self.close_connection = True  # close without telling the client, like an idle timeout

    def log_message(self, *_arguments) -> None:
        pass


@pytest.fixture()
def echo_server():
    _EchoHandler.peers = []
    _EchoHandler.drop_after_answer = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_persistent_bridge_sends_and_parses_exactly_like_ghidra_bridge(echo_server) -> None:
    plain = GhidraBridge(echo_server, timeout=10)
    persistent = fingerprint._PersistentBridge(plain)
    try:
        for call in (
            lambda bridge: bridge.request("get_function_by_address", address="0x140010"),
            lambda bridge: bridge.request("/list_functions_enhanced", offset=0, limit=1_000_000, unused=None),
            lambda bridge: bridge.request("text"),
            lambda bridge: bridge.post_json("get_bulk_xrefs", addresses="0x1,.debug::2"),
        ):
            assert call(persistent) == call(plain)
        assert persistent.request("get_function_by_address", address="0x140010") == {
            "path": "/get_function_by_address?address=0x140010&program=socom.elf",
            "body": None,
            "type": None,
        }
        assert persistent.request("text") == "not json é"
        with pytest.raises(SocomError, match="HTTP Error 500"):
            persistent.request("fail")
    finally:
        persistent.close()


def test_persistent_bridge_reuses_one_connection_and_resends_once_after_a_silent_close(echo_server) -> None:
    persistent = fingerprint._PersistentBridge(GhidraBridge(echo_server, timeout=10))
    try:
        for _ in range(5):
            persistent.post_json("get_bulk_xrefs", addresses="0x1")
        assert len(set(_EchoHandler.peers)) == 1
        _EchoHandler.drop_after_answer = True
        persistent.request("get_function_by_address", address="0x1")
        assert persistent.request("get_function_by_address", address="0x2")["path"].startswith("/get_function_by_address?address=0x2")
        first, second = _EchoHandler.peers[0], _EchoHandler.peers[-1]
        assert first != second and _EchoHandler.peers == [first] * 6 + [second]
    finally:
        persistent.close()


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


def test_concurrent_reference_sweep_sends_the_same_calls_and_returns_the_same_rows(monkeypatch) -> None:
    monkeypatch.setattr(fingerprint, "SWEEP_CHUNK", 2)
    references = {
        "0x100004": [{"from": "00100000", "type": "DATA"}],
        "0x5e7f01": [{"from": "00100004", "type": "WRITE"}, {"from": "00100001", "type": "READ"}],
        ".debug::1": [{"from": "00100002", "type": "READ"}],
    }
    legacy_bridge, concurrent_bridge = _SweepBridge(references), _SweepBridge(references)
    blocks = fingerprint._segments(legacy_bridge)
    logged: list[str] = []
    legacy = fingerprint._references(legacy_bridge, blocks, lambda _message: None, workers=1)
    concurrent = fingerprint._references(concurrent_bridge, blocks, logged.append, workers=3)
    assert concurrent == legacy
    assert sorted(concurrent_bridge.requested) == sorted(legacy_bridge.requested)
    assert len(concurrent_bridge.requested) == len(set(concurrent_bridge.requested)) == 10
    assert logged == [
        "  references through main: 1",
        "  references through heap: 3",
        "  references through .debug: 4",
    ]
    with pytest.raises(SocomError, match="did not answer every address of main at 100002"):
        fingerprint._references(_SweepBridge({}, drop="0x100003"), blocks, lambda _message: None, workers=3)


def test_in_order_yields_in_item_order_when_calls_finish_out_of_order() -> None:
    second_done = threading.Event()

    def call(item: int) -> int:
        if item == 0:
            assert second_done.wait(timeout=10)
        if item == 2:
            second_done.set()
        return item * 10

    assert list(fingerprint._in_order(call, range(9), 3)) == [item * 10 for item in range(9)]
    assert list(fingerprint._in_order(call, [], 3)) == []


class _FunctionBridge:
    def request(self, endpoint, **parameters):
        if endpoint == "list_functions_enhanced":
            return {
                "functions": [
                    {"address": "00140460", "name": "f", "isThunk": True},
                    {"address": "00140010", "name": "entry"},
                    {"address": "EXTERNAL:00000001", "name": "ext", "isExternal": True},
                ]
            }
        assert endpoint == "get_function_by_address"
        return "\n".join([f"Function: at {parameters['address']}", "Signature: void x(void)", "ignored line"])


def test_function_rows_do_not_depend_on_the_sweep_mode() -> None:
    legacy = fingerprint._functions(_FunctionBridge(), lambda _message: None, workers=1)
    concurrent = fingerprint._functions(_FunctionBridge(), lambda _message: None, workers=3)
    assert concurrent == legacy
    assert [row["address"] for row in legacy] == ["00140010", "00140460", "EXTERNAL:00000001"]
    assert legacy[0]["details"] == ["Function: at 0x140010", "Signature: void x(void)"]
    assert "details" not in legacy[2]


def test_sweep_mode_selects_workers_and_rejects_unknown_modes() -> None:
    assert fingerprint._workers("legacy") == 1
    assert fingerprint._workers("concurrent") == fingerprint.SWEEP_WORKERS == 3
    with pytest.raises(SocomError, match="unknown fingerprint sweep mode"):
        fingerprint._workers("parallel")


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
