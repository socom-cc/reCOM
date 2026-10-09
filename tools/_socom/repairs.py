"""Governed repairs of accepted live Ghidra state.

A repair item exists only when an accepted apply changed something outside
its scope that no later batch will correct.  Each spec here records the
exact wrong state the live program must still hold and the state to restore;
`ghidra repair-signatures` refuses any other starting point and reads every
restored signature back.
"""

from __future__ import annotations

from typing import Any, Callable

from .batch_apply import _FUNCTION_LINE, _SIGNATURE_LINE
from .util import SocomError

BATCH_001_APPLY_ID = "socom:debug-batch:cb1cc66c6e35fc967c25-apply"
BATCH_010_APPLY_ID = "socom:debug-batch:873c518eab3c45871ed4-apply"
BATCH_013_APPLY_ID = "socom:debug-batch:d73cfb813babeb1ce7f8-apply"
BATCH_014_APPLY_ID = "socom:debug-batch:1791d0faee0ad2d6713e-apply"
THUNK_REPAIR_ID = "socom:work:ghidra-repair-batch-001-thunk-signatures"
COPY_NAMES_REPAIR_ID = "socom:work:ghidra-repair-file-local-copy-names"

# Batch 001 set prototypes on COurGame::StopPlay (0x140500) and StartPlay
# (0x140510). Each is a thunk (j 0x20e790 / j 0x20e7a0; nop), and a Ghidra
# thunk shares its target's signature, so the CGame functions took
# `COurGame * this`. They have no DWARF record, so no batch restores them;
# batch 001's before-snapshot shows the thunks displaying their targets'
# import-time signature `undefined NAME(void)` (unknown calling convention).
# The bridge accepts only __stdcall and __thiscall (a first attempt with
# "unknown" was refused after the signature had applied), so the repair
# restores `undefined __stdcall NAME(void)`: no return type or parameters,
# with the compiler spec's default convention every applied function uses.
REPAIRS: dict[str, dict[str, Any]] = {
    THUNK_REPAIR_ID: {
        "kind": "signatures",
        "title": "Restore the CGame signatures batch 001 changed through COurGame thunks",
        "dependencies": [BATCH_001_APPLY_ID],
        "functions": [
            {
                "address": "0x20e790",
                "name": "StopPlay__5CGameFv",
                "thunk": "0x140500",
                "thunk_name": "COurGame::StopPlay",
                "wrong_return": "void __stdcall",
                "wrong_parameters": "COurGame * this",
            },
            {
                "address": "0x20e7a0",
                "name": "StartPlay__5CGameFv",
                "thunk": "0x140510",
                "thunk_name": "COurGame::StartPlay",
                "wrong_return": "void __stdcall",
                "wrong_parameters": "COurGame * this",
            },
        ],
        "restore_prototype": "undefined socom_prototype(void)",
        "restore_calling_convention": "__stdcall",
        "restored_return": "undefined __stdcall",
        "restored_parameters": "void",
    },
    # Batches 001, 10, 13 and 14 gave readable names to file-local copies
    # (one per compile unit) that are not canonical: RTTI copies their class
    # vtable does not reference, and statics with no canonical copy. The
    # first batch to reach a copy won. Deleting the readable label leaves the
    # mangled label primary.
    COPY_NAMES_REPAIR_ID: {
        "kind": "labels",
        "title": "Return non-canonical file-local copies to their mangled names",
        "dependencies": [BATCH_001_APPLY_ID, BATCH_010_APPLY_ID, BATCH_013_APPLY_ID, BATCH_014_APPLY_ID],
        "labels": [
            {"address": "0x444498", "readable": "CGame::__RTTI", "mangled": "__RTTI__5CGame"},
            {"address": "0x4489b8", "readable": "C2DFade::__RTTI", "mangled": "__RTTI__7C2DFade"},
            {
                "address": "0x4489e8",
                "readable": "std::list<C2D*,std::allocator<C2D*>>::__RTTI",
                "mangled": "__RTTI__Q23std36list<P3C2D,Q23std16allocator<P3C2D>>",
            },
            {"address": "0x448a08", "readable": "C2Dlist::__RTTI", "mangled": "__RTTI__7C2Dlist"},
            {"address": "0x448a38", "readable": "C2D::__RTTI", "mangled": "__RTTI__3C2D"},
            {"address": "0x448a78", "readable": "C2DBitmap::__RTTI", "mangled": "__RTTI__9C2DBitmap"},
            {
                "address": "0x44c958",
                "readable": "zdb::tag_NODE_PARAMS::__RTTI",
                "mangled": "__RTTI__Q23zdb15tag_NODE_PARAMS",
            },
            {"address": "0x44c980", "readable": "zdb::CNode::__RTTI", "mangled": "__RTTI__Q23zdb5CNode"},
            {"address": "0x4756d8", "readable": "std::__msl_ios_base_ninit", "mangled": "__msl_ios_base_ninit__3std"},
            {"address": "0x4756dc", "readable": "std::__msl_ios_base_winit", "mangled": "__msl_ios_base_winit__3std"},
        ],
    },
}


def _signature(prefix: str, name: str, parameters: str) -> str:
    return f"{prefix} {name}({parameters})"


def _read(bridge: Any, address: str) -> tuple[str | None, str | None]:
    text = bridge.request("get_function_by_address", address=address)
    lines = text.splitlines() if isinstance(text, str) else []
    function = next((match for line in lines if (match := _FUNCTION_LINE.match(line))), None)
    signature = next((match for line in lines if (match := _SIGNATURE_LINE.match(line))), None)
    return (function.group(1) if function else None, signature.group(1) if signature else None)


def repair_signatures(
    item_id: str,
    bridge: Any,
    *,
    log: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    """Restore each recorded function (and so its thunk) to its prior signature."""

    spec = REPAIRS.get(item_id)
    if spec is None:
        raise SocomError(f"{item_id} has no recorded repair")
    if spec.get("kind") != "signatures":
        raise SocomError(f"{item_id} is not a signature repair")
    plans = []
    for function in spec["functions"]:
        target, thunk = function["address"], function["thunk"]
        plans.append(
            {
                "function": function,
                "names": {target: function["name"], thunk: function["thunk_name"]},
                "wrong": {
                    target: _signature(function["wrong_return"], function["name"], function["wrong_parameters"]),
                    thunk: _signature(function["wrong_return"], function["thunk_name"], function["wrong_parameters"]),
                },
                "restored": {
                    target: _signature(spec["restored_return"], function["name"], spec["restored_parameters"]),
                    thunk: _signature(spec["restored_return"], function["thunk_name"], spec["restored_parameters"]),
                },
            }
        )
    # Check every starting state before the first write.
    befores = []
    for plan in plans:
        before = {address: _read(bridge, address) for address in plan["names"]}
        for address, (name, signature) in before.items():
            if name != plan["names"][address]:
                raise SocomError(f"function at {address} is {name!r}, expected {plan['names'][address]!r}")
            if signature != plan["wrong"][address]:
                raise SocomError(
                    f"{address} signature is {signature!r}, not the recorded wrong state {plan['wrong'][address]!r}"
                )
        befores.append(before)
    rows = []
    for plan, before in zip(plans, befores):
        function = plan["function"]
        target, thunk = function["address"], function["thunk"]
        names, restored = plan["names"], plan["restored"]
        log(f"restoring {function['name']} at {target}")
        response = bridge.post_json(
            "set_function_prototype",
            function_address=target,
            prototype=spec["restore_prototype"],
            calling_convention=spec["restore_calling_convention"],
        )
        if not (isinstance(response, str) and response.startswith("Successfully set prototype")):
            raise SocomError(f"set_function_prototype failed at {target}: {response!r}")
        after = {address: _read(bridge, address) for address in (target, thunk)}
        for address, (name, signature) in after.items():
            if name != names[address] or signature != restored[address]:
                raise SocomError(
                    f"{address} reads back {name!r} {signature!r}, expected {restored[address]!r}; "
                    "close socom.elf without saving before retrying"
                )
        rows.append(
            {
                "address": target,
                "thunk": thunk,
                "before": {address: before[address][1] for address in (target, thunk)},
                "after": {address: after[address][1] for address in (target, thunk)},
            }
        )
    scope = {
        "schema_version": 1,
        # load_receipt_scope's order (casefold, spelling) for 0x-prefixed hex.
        "functions": sorted({address for row in rows for address in (row["address"], row["thunk"])}),
        "types": [],
        "globals": [],
    }
    return {"functions": rows, "receipt_scope": scope, "bridge_call_count": len(rows)}


def repair_labels(
    item_id: str,
    bridge: Any,
    *,
    log: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    """Delete each recorded readable label so the mangled label is primary again."""

    spec = REPAIRS.get(item_id)
    if spec is None:
        raise SocomError(f"{item_id} has no recorded repair")
    if spec.get("kind") != "labels":
        raise SocomError(f"{item_id} is not a label repair")

    def audit(address: str) -> dict[str, Any]:
        value = bridge.request("audit_global", address=address, strict_mode="off")
        if not isinstance(value, dict):
            raise SocomError(f"audit_global failed at {address}: {value!r}")
        return value

    # Check every starting state before the first write.
    before = {}
    for label in spec["labels"]:
        state = audit(label["address"])
        if state.get("is_code_address") or state.get("is_function_entry"):
            raise SocomError(f"{label['address']} is code in the live program")
        if state.get("name") != label["readable"]:
            raise SocomError(
                f"{label['address']} primary name is {state.get('name')!r}, not the recorded {label['readable']!r}"
            )
        before[label["address"]] = state
    rows = []
    for label in spec["labels"]:
        address = label["address"]
        log(f"removing {label['readable']} at {address}")
        # delete_label removes only labels of exactly this name.
        response = bridge.post_json("delete_label", address=address, name=label["readable"])
        if not (
            isinstance(response, dict)
            and response.get("success") is True
            and response.get("deleted_count") == 1
            and response.get("deleted_names") == [label["readable"]]
        ):
            raise SocomError(
                f"delete_label at {address} did not remove exactly {label['readable']!r}: {response!r}; "
                "close socom.elf without saving before retrying"
            )
        after = audit(address)
        if after.get("name") != label["mangled"] or after.get("type") != before[address].get("type"):
            raise SocomError(
                f"{address} reads back {after.get('name')!r} {after.get('type')!r}, expected {label['mangled']!r}; "
                "close socom.elf without saving before retrying"
            )
        rows.append({"address": address, "before": label["readable"], "after": after.get("name"), "type": after.get("type")})
    scope = {
        "schema_version": 1,
        "functions": [],
        "types": [],
        "globals": sorted({label["address"] for label in spec["labels"]}),
    }
    return {"labels": rows, "receipt_scope": scope, "bridge_call_count": len(rows)}
