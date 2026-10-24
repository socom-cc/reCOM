"""Command records proven by their registration (``recon layout --records``).

A command table stores, per command, a name and callback pointers.  zAnim's
``CZAnimMain::AddCmd(this, name, parser, begin, tick, end)`` is the target
(``REGISTRARS["zanim"]``): every callback receives or returns a pointer to a
``_zanim_cmd_hdr`` that is really the command's own record (DWARF for
``zcam_main.cpp`` shows ``cmd_ptr = (_camera_params_cmd *)hdr``).  The
registrar is configured by its qualified name, the register holding the name
string and the role of each callback register; which register of a callback
holds the record, and whether it returns one, comes from the registrar's own
mangled parameter types (a callback parameter or result typed as a pointer to
the header), not from the configuration.

Facts, each with its cited proof:

* a registration is a direct call (or tail jump) to the registrar whose name
  register holds the address of a NUL-terminated string and whose role
  registers each hold a function address or NULL;
* a callback registered for role R of command X receives X's record in the
  registers R's function-pointer type types as the header (a function stored
  in a plain function pointer is static, so its a0 is no ``this``), and a
  parser returns X's record;
* a direct callee (call or tail jump) receives the record when the caller
  passes a record pointer, unchanged, in a register that the callee's mangled
  parameter types as the header or that a registration of the callee proves
  (so ``CTDoor::Begin`` jumping to ``CTMove::Begin`` gives it DOOR records);
* a function that returns a record returns, at every exit, NULL, the result
  of an allocator (the record's allocation: ``_calloc`` size a0*a1,
  ``_malloc`` a0), of a mover (``_realloc``: the record grows, and its
  argument was the record before the move), of another function (which then
  returns the record too) or of a tail jump (likewise); other exit values are
  listed as unrooted.

The facts are gathered first, without holder typing, so caller-to-callee
propagation does not depend on the callee-first order of the main analysis;
``_Collector`` roots the same registers and call results in that analysis.
A function entered several ways holds the records of every command that
reaches it (``record_key`` of all of them), and its accesses are attributed
to each.  Nothing here reads Ghidra or names.
"""

from __future__ import annotations

import re
from collections import defaultdict
from fnmatch import fnmatchcase
from typing import Any

from .mwdemangle import render_type
from .recon_facts import GPR
from .type_layout import (
    _JR_RA,
    RECORD,
    _Analysis,
    _copy_source,
    _hex,
    _is_const,
    _levels,
    _pointee_class,
    _string_at,
    _ZERO,
    parameter_registers,
    record_key,
)
from .util import SocomError

# One entry per command table.  ``roles`` maps each callback register of the
# registrar to its role name; ``header`` is the record header type every
# callback pointer type names; ``allocators`` give each allocation's size as
# the product of constant argument registers; ``movers`` return their
# argument register's object, moved (reallocated).  ``record_names`` is the
# naming rule for invented record types, after the DWARF records of the
# family (``_camera_params_cmd``, ``TASK_SELECT``).
REGISTRARS: dict[str, dict[str, Any]] = {
    "zanim": {
        "function": ["CZAnimMain", "AddCmd"],
        "name_register": "a1",
        "roles": [["a2", "parser"], ["a3", "begin"], ["t0", "tick"], ["t1", "end"]],
        "header": ["_zanim_cmd_hdr"],
        "allocators": {"_calloc": ["a0", "a1"], "_malloc": ["a0"]},
        "movers": {"_realloc": "a0"},
        "record_names": r"^(?:_[a-z][a-z0-9]*(?:_[a-z0-9]+)*_cmd|TASK_[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*)$",
        "record_names_text": "an invented record type is named _<module>_<name>_cmd (as the DWARF camera records) "
        "or TASK_<NAME> (as the DWARF TASK_HDR-derived AI records)",
    }
}
FAMILY_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def record_class(command: str) -> str:
    """The layout class name of one command's record (never a C++ name)."""

    return f"record {command}"


def registrar_config(name: str) -> dict[str, Any]:
    if name not in REGISTRARS:
        raise SocomError(f"unknown registrar {name!r}; known: {sorted(REGISTRARS)}")
    return REGISTRARS[name]


def _exit_values(ctx: Any, analysis: _Analysis, definitions: set[Any], register: int, depth: int = 0) -> list[Any] | None:
    """Every value ``register`` can hold given its reaching definitions (``_Holders._values`` without holders)."""

    values: list[Any] = []
    for definition in sorted(definitions, key=str):
        if definition == "entry" or definition not in analysis.states:
            return None
        value = analysis._transfer(definition, analysis.states[definition], record=False).get(register)
        if value is None:
            source = _copy_source(ctx.code.word(definition), register)
            if source is None or depth >= 8 or analysis._call_kind(definition):
                return None
            inner = _exit_values(ctx, analysis, analysis.flow.defs(definition, source), source, depth + 1)
            if inner is None:
                return None
            values.extend(inner)
        else:
            values.append(value)
    return values


def exits(ctx: Any, analysis: _Analysis) -> list[tuple[str, int, Any]]:
    """("return", pc, values or None) per ``jr ra`` and ("tail", pc, target or None) per outgoing transfer."""

    flow = analysis.flow
    found: list[tuple[str, int, Any]] = []
    for pc in range(analysis.start, analysis.end, 4):
        if not flow.reachable(pc):
            continue
        row = flow.fn.decoded.get(pc) or {}
        if ctx.code.word(pc) == _JR_RA:
            found.append(("return", pc, _exit_values(ctx, analysis, flow.after(pc + 4, 2), 2)))
        elif row.get("kind") == "jr":
            if not any(analysis.start <= target < analysis.end for target in analysis.successors.get(pc + 4, ())):
                found.append(("tail", pc, None))  # an indirect transfer out (a jump table's targets stay inside)
        elif row.get("kind") == "jump" and row.get("target") is not None and not (analysis.start <= row["target"] < analysis.end):
            found.append(("tail", pc, row["target"]))
    return found


class Registry:
    """Registrations of one command table and the record pointers they prove (see the module docstring)."""

    def __init__(self, family: Any, parameters: Any, key: str = "zanim") -> None:
        self.key = key
        self.config = registrar_config(key)
        self.family = family
        self.ctx = family.ctx
        self.symbols = family.symbols
        self.receivers = family.receivers
        self.parameters = parameters
        self.header = tuple(self.config["header"])
        self._analyses: dict[int, _Analysis] = {}
        self.problems: list[str] = []
        self.registrar = self._registrar()
        self.roles = self._roles()
        self.registrations = self._registrations()
        self.commands: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self.registrations:
            if row["command"] is not None:
                self.commands[row["command"]].append(row)
        # function -> register -> command -> proofs; function -> command -> proofs (it returns the record);
        # function -> root term -> command -> proofs (call results that are the record).
        self.entries: dict[int, dict[int, dict[str, set[str]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
        self.returns: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self.terms: dict[int, dict[tuple, dict[str, set[str]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
        self.allocations: dict[str, dict[tuple[int, int], dict[str, Any]]] = defaultdict(dict)
        self.unrooted: dict[str, dict[tuple[int, int, str], dict[str, Any]]] = defaultdict(dict)
        self.selected: frozenset[str] = frozenset()
        self._propagate()

    # -- registrations -------------------------------------------------------

    def _registrar(self) -> int:
        qualifier, name = list(self.config["function"][:-1]), self.config["function"][-1]
        found = [
            address for address, row in sorted(self.symbols.functions.items())
            if (row.get("parsed") or {}).get("name") == name and list((row.get("parsed") or {}).get("qualifier") or []) == qualifier
        ]
        if len(found) != 1:
            raise SocomError(f"registrar {'::'.join(self.config['function'])}: {len(found)} functions have that name")
        return found[0]

    def registrar_name(self) -> str:
        return self.symbols.readable(self.registrar)

    def _roles(self) -> list[dict[str, Any]]:
        parsed = self.symbols.parsed(self.registrar)
        has_this = bool(parsed.get("qualifier")) and self.receivers.proof(self.registrar) is not None
        rows, _complete = parameter_registers(parsed.get("params"), has_this, self.symbols.scalars)
        by_register = dict(rows)
        name_value = by_register.get(self.config["name_register"])
        if not name_value or name_value.get("kind") != "builtin" or name_value.get("name") != "char" or len(_levels(name_value)) != 1:
            raise SocomError(f"{self.registrar_name()}: {self.config['name_register']} is not a char * name parameter")
        roles = []
        for register, role in self.config["roles"]:
            value = by_register.get(register)
            if not value or value.get("kind") != "function" or _levels(value) != ["P"]:
                raise SocomError(f"{self.registrar_name()}: {register} ({role}) is not a function pointer parameter")
            callback, _complete = parameter_registers(value.get("params"), False, self.symbols.scalars)
            record_registers = [GPR.index(name) for name, item in callback if not name.startswith("f") and _pointee_class(item) == self.header]
            returns = _pointee_class(value.get("result") or {}) == self.header
            roles.append(
                {
                    "role": role,
                    "register": register,
                    "type": render_type(value),
                    "record_registers": record_registers,
                    "returns_record": returns,
                }
            )
        return roles

    def analysis(self, address: int) -> _Analysis:
        if address not in self._analyses:
            self._analyses[address] = _Analysis(self.ctx, self.symbols, address)
        return self._analyses[address]

    def _registrations(self) -> list[dict[str, Any]]:
        rows = []
        for caller in sorted(self.ctx.graph["callers"].get(self.registrar, [])):
            if caller not in self.ctx.size:
                continue
            for call in self.analysis(caller).calls:
                if call["callee"] != self.registrar:
                    continue
                value = call["arguments"].get(self.config["name_register"])
                name = _string_at(self.ctx, value[1]) if value is not None and value[0] == ("sym",) else None
                callbacks, problems = {}, []
                for spec in self.roles:
                    item = call["arguments"].get(spec["register"])
                    if item == _ZERO:
                        callbacks[spec["role"]] = None
                    elif item is not None and item[0] == ("sym",) and item[1] in self.symbols.functions:
                        callbacks[spec["role"]] = item[1]
                    else:
                        problems.append(f"{spec['register']} ({spec['role']}) is not a function address or NULL")
                if name is None:
                    problems.append(f"{self.config['name_register']} is not the address of a string")
                rows.append(
                    {
                        "site": call["site"],
                        "function": caller,
                        "command": name,
                        "callbacks": callbacks,
                        "problems": problems,
                    }
                )
        return rows

    def short(self, address: int | None) -> str:
        """A function's qualified name without its parameter list (proof texts)."""

        parsed = self.symbols.parsed(address)
        if not parsed:
            return self.symbols.readable(address)
        return "::".join([*(parsed.get("qualifier") or []), parsed["name"]])

    def registration_text(self, row: dict[str, Any]) -> str:
        return f"{self.short(self.registrar)} @0x{row['site']:x} in {self.short(row['function'])}"

    # -- propagation -----------------------------------------------------------

    def _role_spec(self, role: str) -> dict[str, Any]:
        return next(spec for spec in self.roles if spec["role"] == role)

    def _registered_registers(self, function: int) -> set[int]:
        """Registers a registration proves ``function`` receives the header in."""

        found: set[int] = set()
        for row in self.registrations:
            for role, address in row["callbacks"].items():
                if address == function:
                    found.update(self._role_spec(role)["record_registers"])
        return found

    def takes_header(self, function: int, register: int) -> bool:
        if register in self._registered_registers(function):
            return True
        value = self.parameters.value_of(function, GPR[register])
        return value is not None and _pointee_class(value) == self.header

    def _propagate(self) -> None:
        pending: set[int] = set()
        for row in self.registrations:
            if row["command"] is None:
                continue
            for role, address in sorted(row["callbacks"].items()):
                if address is None:
                    continue
                spec = self._role_spec(role)
                proof = f"{role} of {row['command']} ({spec['register']} of {self.registration_text(row)})"
                for register in spec["record_registers"]:
                    self.entries[address][register][row["command"]].add(proof)
                if spec["returns_record"]:
                    self.returns[address][row["command"]].add(proof)
                pending.add(address)
        while pending:
            function = min(pending)
            pending.discard(function)
            if function not in self.ctx.size:
                continue
            pending.update(self._visit(function))

    def _add(self, table: dict[str, set[str]], commands: dict[str, set[str]], proof: str) -> bool:
        changed = False
        for command in commands:
            if proof not in table[command]:
                table[command].add(proof)
                changed = True
        return changed

    def _visit(self, function: int) -> set[int]:
        analysis = self.analysis(function)
        changed: set[int] = set()
        name = self.short(function)
        commands = {command: set(proofs) for command, proofs in self.returns.get(function, {}).items()}
        if commands:
            for kind, pc, item in exits(self.ctx, analysis):
                if kind == "tail":
                    if item is None or item not in self.ctx.size:
                        self._unrooted(commands, function, pc, "returns through an indirect tail jump")
                    elif self._add(self.returns[item], commands, f"{name} tail-jumps to it @0x{pc:x}"):
                        changed.add(item)
                    continue
                if item is None:
                    self._unrooted(commands, function, pc, "the returned value is not proven at this exit")
                    continue
                for value in item:
                    changed |= self._returned(function, analysis, value, commands, pc)
        calls = {call["site"]: call for call in analysis.calls}
        for site in sorted(calls):
            call = calls[site]
            callee = call["callee"]
            if callee is None or callee not in self.ctx.size:
                continue
            for register_name, value in sorted(call["arguments"].items()):
                if register_name.startswith("f") or value[1] != 0:
                    continue
                passed = self.commands_of(function, value[0])
                register = GPR.index(register_name)
                if not passed or not self.takes_header(callee, register):
                    continue
                proof = f"{register_name} passed by {name} @0x{site:x}"
                if self._add(self.entries[callee][register], passed, proof):
                    changed.add(callee)
        return changed

    def commands_of(self, function: int, term: tuple) -> dict[str, set[str]]:
        """Commands whose record the phase-1 term holds in ``function`` (an entry register or a call result)."""

        if term[0] == "arg":
            return dict(self.entries.get(function, {}).get(term[1], {}))
        return dict(self.terms.get(function, {}).get(term, {}))

    def _unrooted(self, commands: dict[str, set[str]], function: int, pc: int, reason: str) -> None:
        for command in commands:
            self.unrooted[command][(function, pc, reason)] = {
                "function": _hex(function),
                "name": self.symbols.readable(function),
                "site": _hex(pc),
                "reason": reason,
            }

    def _returned(self, function: int, analysis: _Analysis, value: Any, commands: dict[str, set[str]], pc: int, depth: int = 0) -> set[int]:
        changed: set[int] = set()
        if value == _ZERO:
            return changed
        term, k = value
        name = self.short(function)
        if k != 0 or term[0] not in ("res", "arg") or depth > 8:
            self._unrooted(commands, function, pc, f"returns a value that is no call result or entry register ({term[0]}{'+' + _hex(k) if k else ''})")
            return changed
        if term[0] == "arg":
            if self._add(self.entries[function][term[1]], commands, f"{name} returns its entry {GPR[term[1]]} @0x{pc:x}"):
                changed.add(function)
            return changed
        site = term[1]
        call = next((row for row in analysis.calls if row["site"] == site), None)
        callee = call["callee"] if call else None
        self._add(self.terms[function][term], commands, f"{name} returns the result of the call @0x{site:x} (exit @0x{pc:x})")
        parsed = self.symbols.parsed(callee)
        allocator = None if parsed.get("qualifier") else parsed.get("name")
        if allocator in self.config["allocators"]:
            arguments = [call["arguments"].get(register) for register in self.config["allocators"][allocator]]
            size = 1
            for item in arguments:
                size = size * item[1] if size is not None and _is_const(item) and item[1] > 0 else None
            for command in commands:
                self.allocations[command][(function, site)] = {
                    "function": _hex(function),
                    "function_name": name,
                    "allocation_site": _hex(site),
                    "allocator": self.symbols.readable(callee),
                    "size": size,
                }
        elif allocator in self.config["movers"]:
            for command in commands:
                self.allocations[command][(function, site)] = {
                    "function": _hex(function),
                    "function_name": name,
                    "allocation_site": _hex(site),
                    "allocator": self.symbols.readable(callee),
                    "size": None,
                    "moves": self.config["movers"][allocator],
                }
            moved = call["arguments"].get(self.config["movers"][allocator])
            if moved is not None:
                changed |= self._returned(function, analysis, moved, commands, pc, depth + 1)
        elif callee is not None and callee in self.ctx.size:
            if self._add(self.returns[callee], commands, f"{name} returns its result @0x{site:x}"):
                changed.add(callee)
        else:
            self._unrooted(commands, function, pc, f"returns the result of an indirect call @0x{site:x}")
        return changed

    # -- selection and roots ------------------------------------------------------

    def select(self, selectors: list[str]) -> list[str]:
        """Expand command names and ``set::*`` / ``*`` patterns to the registered commands."""

        chosen: set[str] = set()
        for selector in selectors:
            matched = sorted(name for name in self.commands if fnmatchcase(name, selector)) if any(
                char in selector for char in "*?["
            ) else ([selector] if selector in self.commands else [])
            if not matched:
                near = sorted(name for name in self.commands if name.split("::")[-1].lower() == selector.split("::")[-1].lower())
                raise SocomError(
                    f"no command registered through {self.registrar_name()} matches {selector!r}"
                    + (f" (did you mean {', '.join(near)}?)" if near else "")
                )
            chosen.update(matched)
        self.selected = frozenset(chosen)
        return sorted(chosen)

    def _root(self, commands: dict[str, set[str]]) -> tuple[tuple[str, ...], str] | None:
        wanted = sorted(set(commands) & self.selected)
        if not wanted:
            return None
        proofs = sorted({f"{command}: {proof}" for command, items in commands.items() for proof in items})
        return record_key(wanted), "; ".join(proofs)

    def entry_roots(self, function: int) -> dict[int, tuple[tuple[str, ...], str]]:
        found = {}
        for register, commands in sorted(self.entries.get(function, {}).items()):
            root = self._root(commands)
            if root is not None:
                found[register] = root
        return found

    def term_roots(self, function: int) -> dict[tuple, tuple[tuple[str, ...], str]]:
        found = {}
        for term, commands in sorted(self.terms.get(function, {}).items(), key=lambda item: str(item[0])):
            root = self._root(commands)
            if root is not None:
                found[term] = root
        return found

    def callbacks(self, command: str) -> list[dict[str, Any]]:
        """Every function that receives or returns the command's record, with how."""

        rows = []
        for function, registers in sorted(self.entries.items()):
            for register, commands in sorted(registers.items()):
                if command in commands:
                    rows.append(
                        {
                            "function": _hex(function),
                            "name": self.symbols.readable(function),
                            "record": GPR[register],
                            "proofs": sorted(commands[command]),
                        }
                    )
        for function, commands in sorted(self.returns.items()):
            if command in commands:
                rows.append(
                    {
                        "function": _hex(function),
                        "name": self.symbols.readable(function),
                        "record": "return",
                        "proofs": sorted(commands[command]),
                    }
                )
        return sorted(rows, key=lambda row: (int(row["function"], 16), row["record"]))

    def registration_rows(self, command: str) -> list[dict[str, Any]]:
        return [
            {
                "site": _hex(row["site"]),
                "function": _hex(row["function"]),
                "function_name": self.symbols.readable(row["function"]),
                "callbacks": {
                    role: ({"function": _hex(address), "name": self.symbols.readable(address)} if address is not None else None)
                    for role, address in row["callbacks"].items()
                },
                "problems": row["problems"],
            }
            for row in self.commands.get(command, [])
        ]

    def summary(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "function": _hex(self.registrar),
            "name": self.registrar_name(),
            "name_register": self.config["name_register"],
            "header": "::".join(self.header),
            "roles": self.roles,
            "allocators": {name: list(registers) for name, registers in sorted(self.config["allocators"].items())},
            "movers": dict(sorted(self.config["movers"].items())),
            "record_names": self.config["record_names"],
            "record_names_text": self.config["record_names_text"],
            "registration_count": len(self.registrations),
            "command_count": len(self.commands),
            "unnamed_registrations": [
                {"site": _hex(row["site"]), "function": self.symbols.readable(row["function"]), "problems": row["problems"]}
                for row in self.registrations if row["command"] is None
            ],
        }


def record_family(
    root: Any, selectors: list[str], registrar: str, class_name: str | None, with_derived: bool, family: str | None
) -> list[str]:
    """Expand a records family for a plan item: the slug is valid, the class lays out, every selector matches."""

    from .type_layout import CallParameters, _Family

    if not family or not FAMILY_SLUG.match(family):
        raise SocomError("--family is a lower-case slug (letters, digits and hyphens) naming the records family")
    owner = _Family(root, class_name, with_derived, records=True)
    return Registry(owner, CallParameters(owner.symbols, owner.receivers), registrar).select(list(selectors))


__all__ = ["FAMILY_SLUG", "REGISTRARS", "Registry", "exits", "record_class", "record_family", "registrar_config"]
