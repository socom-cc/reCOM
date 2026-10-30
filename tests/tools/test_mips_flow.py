from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from tools._socom import cli
from tools._socom.mips_flow import _Function, decode
from tools._socom.util import SocomError

A0, AT, V1, RA = 4, 1, 3, 31


def lui(rt: int, imm: int) -> int:
    return (0x0F << 26) | (rt << 16) | imm


def addiu(rt: int, rs: int, imm: int) -> int:
    return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def lw(rt: int, base: int, imm: int) -> int:
    return (0x23 << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)


def jal(target: int) -> int:
    return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)


def branch(opcode: int, rs: int, rt: int, offset_words: int) -> int:
    return (opcode << 26) | (rs << 21) | (rt << 16) | (offset_words & 0xFFFF)


NOP = 0


class _Code:
    def __init__(self, base: int, words: list[int]) -> None:
        self.words = {base + 4 * index: word for index, word in enumerate(words)}

    def word(self, address: int) -> int:
        return self.words[address]


def _function(words: list[int], base: int = 0x1000) -> _Function:
    return _Function(_Code(base, words), base, base + 4 * len(words), set())


def test_decode_marks_always_taken_branches_and_calls() -> None:
    assert decode(branch(0x04, 0, 0, 3), 0x1000)["kind"] == "jump"  # b
    conditional = decode(branch(0x04, A0, 0, 3), 0x1000)
    assert conditional["kind"] == "branch" and not conditional["likely"]
    assert decode(branch(0x15, A0, 0, 3), 0x1000)["likely"] is True  # bnel
    call = decode(jal(0x2000), 0x1000)
    assert call["kind"] == "call" and call["writes"] == frozenset([RA])
    assert decode(branch(0x01, 0, 0x11, 3), 0x1000)["kind"] == "call"  # bal


def test_syscall_writes_v0() -> None:
    # The EE kernel returns its result in v0; the code field is not a register.
    assert decode(0x0000000C, 0x1000)["writes"] == frozenset([2])
    assert decode(0x0000F80C, 0x1000)["writes"] == frozenset([2])  # syscall 0x3e0: code bits, not rd
    # li v1,32 ; syscall ; jr ra ; nop: the exit's v0 is the syscall's.
    function = _function([addiu(V1, 0, 32), 0x0000000C, 0x03E00008, NOP])
    assert function.definitions(0x100C, 2) == {0x1004}


def test_call_clobbers_take_effect_after_the_delay_slot() -> None:
    # lui a0,0x47 ; jal f ; addiu a0,a0,0x6f60 (delay slot) ; lw v1,0(a0)
    function = _function([lui(A0, 0x47), jal(0x9000), addiu(A0, A0, 0x6F60), lw(V1, A0, 0)])
    assert function.definitions(0x1008, A0) == {0x1000}
    # After the call returns, a0 is the callee's, not the lui's.
    assert function.definitions(0x100C, A0) == {0x1008}


def test_padding_after_an_unconditional_branch_is_not_an_entry() -> None:
    # 0: lui at ; 4: b +4 (to 0x18) ; 8: nop ; c: nop (dead) ; 10: lw v1,lo(at) ;
    # 14: b -2 (back to 0x10) ; 18: nop -> 0x10 is reached only from 0x18
    words = [
        lui(AT, 0x47),
        branch(0x04, 0, 0, 4),
        NOP,
        NOP,
        lw(V1, AT, 0x6F44),
        branch(0x04, 0, 0, -2),
        NOP,
    ]
    function = _function(words)
    assert function.definitions(0x1010, AT) == {0x1000}


def test_restore_accepted_requires_the_baseline_import(monkeypatch, tmp_path: Path) -> None:
    tracker = {
        "verification_targets": [
            {"id": "socom:verification:ghidra-program", "baseline_receipt_sha256": "b" * 64}
        ],
        "work_items": [
            {
                "id": "socom:work:x-apply",
                "kind": "debug-import-apply-batch",
                "status": "accepted",
                "resources": ["ghidra:soCOM/socom.elf", "ghidra-writer"],
            }
        ],
    }
    monkeypatch.setattr(cli, "load_tracker", lambda _path: tracker)
    monkeypatch.setattr(cli, "require_ghidra_lease", lambda *_args: None)
    arguments = argparse.Namespace(
        root=str(tmp_path), item="socom:work:memory", owner="writer", report_output="build/r.json", bridge_url=None
    )
    monkeypatch.setattr(cli, "semantic_receipt", lambda *_args, **_kwargs: {"receipt_sha256": "c" * 64})
    with pytest.raises(SocomError, match="not the recorded baseline import"):
        cli._ghidra_restore_accepted(arguments)
    monkeypatch.setattr(cli, "semantic_receipt", lambda *_args, **_kwargs: {"receipt_sha256": "b" * 64})
    with pytest.raises(SocomError, match="no replay route"):
        cli._ghidra_restore_accepted(arguments)
