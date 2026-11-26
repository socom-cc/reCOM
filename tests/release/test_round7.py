"""Registration calls, the vtable a constructor stores, and a function's own ordered calls."""
from __future__ import annotations

import elfimage
import functions
import mips
import pairing
from asm import A0, A1, A2, JR_RA, NOP, RA, SP, V0, addiu, frame, jal, lui, lw, sw, unframe
from test_pairing import BASE, body, match


def la(register, address):
    return [lui(register, (address + 0x8000) >> 16), addiu(register, register, address & 0xFFFF)]


def test_handlers_registered_under_the_same_string_pair():
    # a registrar called twice: AddCmd("ONE", h1) and AddCmd("TWO", h2); in the release h1 and h2 swap places
    def registrar_caller(strings_at, order):
        def build(starts):
            words = [frame(), sw(RA, 0, SP)]
            for text_index, handler_index in order:
                words += la(A0, strings_at + 16 * text_index) + la(A1, starts[handler_index]) + [jal(starts[1]), NOP]
            return words + [lw(RA, 0, SP), JR_RA, unframe()]
        return build

    def image(order, role):
        handlers = [body(41, 12), body(42, 12)]
        if role == "r":  # both handlers changed a little: no exact pair, only the strings tell them apart
            handlers = [h[:3] + [addiu(V0, A2, 77)] + h[4:] for h in reversed(handlers)]
        items = [None, body(9), handlers[0], handlers[1], body(3)]
        strings_at = BASE + 0x1000
        sizes = [len(registrar_caller(strings_at, order)([0] * 6))] + [len(x) for x in items[1:]]
        starts, address = [], BASE
        for size in sizes:
            starts.append(address)
            address += ((size + 3) // 4) * 16
        words = []
        for item in [registrar_caller(strings_at, order)(starts)] + items[1:]:
            words += item
            while len(words) % 4:
                words.append(0)
        while BASE + 4 * len(words) < strings_at:
            words.append(0)
        for text in ("CMD_ONE", "CMD_TWO"):
            data = text.encode() + b"\0" * (16 - len(text))
            words += list(mips.words_of(data))
        img = elfimage.synthetic(words, BASE, entry=starts[0], role=role)
        spans = [(s, s + 4 * n) for s, n in zip(starts, sizes)]
        return functions.build(role[0], img, mips.words_of(img.data), spans, None), starts

    P, ps = image([(0, 2), (1, 3)], "p")
    R, rs = image([(0, 3), (1, 2)], "r")  # the handlers swapped places; "ONE" registers the one at 3
    m = pairing.Matcher(P, R, ps[0], rs[0])
    m.run()
    assert m.pairs[ps[2]].r.address == rs[3] and m.pairs[ps[3]].r.address == rs[2]
    places = {(a, b) for a, b, _ in m.registration_correspondences()}
    assert places == {(ps[2], rs[3]), (ps[3], rs[2])}


def test_callee_check_moves_a_pair_to_the_function_whose_calls_fit():
    # the release function makes the calls of prototype B in B's order; order paired it with A
    def caller(*targets):
        def build(starts):
            words = [frame(), sw(RA, 0, SP)]
            for t in targets:
                words += [jal(starts[t]), NOP, addiu(V0, A2, 3 + t)]
            return words + [lw(RA, 0, SP), JR_RA, unframe()]
        return build

    proto = [body(1), body(2), body(3), body(4), caller(0, 1), caller(2, 3, 0, 1), body(5)]
    release = [body(1), body(2), body(3), body(4), caller(2, 3, 0, 1), body(5)]
    m, ps, rs = match(proto, release)
    assert m.pairs[ps[5]].r.address == rs[4]
    assert ps[4] not in m.pairs


def test_class_check_unpairs_destructors_of_different_classes():
    m, ps, rs = match([body(1), body(2)], [body(1), body(2)])
    m._own_classes = ({ps[1]: "CStickAccelerationTuner"}, {rs[1]: "CStickInertiaTuner"})
    assert m.class_check() == 1 and ps[1] not in m.pairs
