"""Reference census generation and invariant checks."""

from __future__ import annotations

import collections
import dataclasses
import hashlib
from pathlib import Path, PureWindowsPath
from typing import Any

from .constants import (
    EXPECTED_COMPILER_COMMENT,
    EXPECTED_ENTRY,
    EXPECTED_MACHINE,
    EXPECTED_RELOCATION_COUNT,
    EXPECTED_SECTION_COUNT,
    EXPECTED_SYMBOL_COUNT,
    REFERENCE_ID,
    REFERENCE_SHA256,
)
from .dwarf1 import Dwarf1Debug, Dwarf1Line, debug_summary, line_summary
from .elf import Elf32File, SHT_NOBITS
from .util import SocomError, sha256_file, stable_id


def _section_record(section: Any, elf: Elf32File) -> dict[str, Any]:
    data = elf.section_data(section)
    return {
        "id": stable_id("section", section.index, section.name),
        "index": section.index,
        "name": section.name,
        "type": section.type_name,
        "flags": section.flags,
        "address": section.address,
        "offset": section.offset,
        "size": section.size,
        "file_backed": section.type != SHT_NOBITS,
        "link": section.link,
        "info": section.info,
        "alignment": section.alignment,
        "entry_size": section.entry_size,
        "content_sha256": hashlib.sha256(data).hexdigest() if data else None,
    }


def _source_correlation(source_paths: list[str], root: Path) -> dict[str, Any]:
    source_root = root / "src"
    current = {
        path.relative_to(source_root).as_posix().casefold(): path
        for path in source_root.rglob("*")
        if path.is_file()
    }
    rows = []
    exact = 0
    for original in source_paths:
        pure = PureWindowsPath(original)
        lowered = str(pure).casefold()
        marker = "z:\\dev\\"
        if not lowered.startswith(marker):
            continue
        relative = str(pure)[len(marker) :].replace("\\", "/")
        candidate = current.get(relative.casefold())
        match = candidate.relative_to(root).as_posix() if candidate else None
        if match:
            exact += 1
        rows.append(
            {
                "original_path": original,
                "expected_relative_path": f"src/{relative}",
                "current_exact_match": match,
                "status": "exact-path" if match else "requires-correlation",
            }
        )
    return {
        "current_source_file_count": len(current),
        "original_z_dev_path_count": len(rows),
        "exact_relative_path_count": exact,
        "requires_correlation_count": len(rows) - exact,
        "rows": rows,
    }


def build_census(root: Path, *, include_rows: bool = True) -> dict[str, Any]:
    reference = root / "support" / "socom.elf"
    digest = sha256_file(reference)
    elf = Elf32File(reference)
    symbols = elf.symbols()
    relocations = elf.relocations()
    mwcats = elf.mwcats()
    comments = elf.comments()
    debug_parser = Dwarf1Debug(elf.section_data(".debug"))
    dies = debug_parser.parse(strict=True)
    debug = debug_summary(dies)
    lines = line_summary(Dwarf1Line(elf.section_data(".line")).parse())

    aliases: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    for symbol in symbols:
        if symbol.value and symbol.name:
            aliases[(symbol.section_index, symbol.value)].append(symbol.index)
    alias_groups = [
        {
            "id": stable_id("alias-group", section, address),
            "section_index": section,
            "address": address,
            "symbol_indices": indices,
        }
        for (section, address), indices in sorted(aliases.items())
        if len(indices) > 1
    ]

    relocation_types = collections.Counter(item.type_name for item in relocations)
    pending_hi: dict[int, list[int]] = collections.defaultdict(list)
    hi_lo_groups = []
    unmatched_lo = []
    for relocation in relocations:
        if relocation.type == 5:
            pending_hi[relocation.symbol_index].append(relocation.index)
        elif relocation.type == 6:
            pending = pending_hi.pop(relocation.symbol_index, [])
            if pending:
                hi_lo_groups.append(
                    {
                        "id": stable_id(
                            "reloc-pair",
                            relocation.symbol_index,
                            *pending,
                            relocation.index,
                        ),
                        "symbol_index": relocation.symbol_index,
                        "hi16_indices": pending,
                        "lo16_index": relocation.index,
                    }
                )
            else:
                unmatched_lo.append(relocation.index)

    census: dict[str, Any] = {
        "schema_version": 1,
        "reference": {
            "id": REFERENCE_ID,
            "path": "support/socom.elf",
            "sha256": digest,
            "size": reference.stat().st_size,
        },
        "elf_header": dataclasses.asdict(elf.header),
        "program_headers": [dataclasses.asdict(item) for item in elf.program_headers],
        "sections": [_section_record(section, elf) for section in elf.sections],
        "symbol_summary": {
            "count": len(symbols),
            "local_cutoff": elf.section(".symtab").info,
            "alias_group_count": len(alias_groups),
            "alias_groups": alias_groups,
        },
        "relocation_summary": {
            "count": len(relocations),
            "type_counts": dict(sorted(relocation_types.items())),
            "hi16_lo16_group_count": len(hi_lo_groups),
            "hi16_lo16_groups": hi_lo_groups,
            "unmatched_hi16_indices": sorted(
                index for values in pending_hi.values() for index in values
            ),
            "unmatched_lo16_indices": unmatched_lo,
            "raw_section_sha256": hashlib.sha256(
                elf.section_data(".relmain")
            ).hexdigest(),
        },
        "mwcats": {
            "record_count": len(mwcats),
            "records": [dataclasses.asdict(item) for item in mwcats],
        },
        "comments": list(comments),
        "debug": debug,
        "line": lines,
        "source_correlation": _source_correlation(
            list(debug["source_paths"]), root
        ),
    }
    if include_rows:
        census["symbols"] = [
            {
                "id": stable_id("symbol", symbol.index, symbol.name),
                "index": symbol.index,
                "name": symbol.name,
                "value": symbol.value,
                "size": symbol.size,
                "binding": symbol.binding_name,
                "type": symbol.type_name,
                "section_index": symbol.section_index,
                "other": symbol.other,
            }
            for symbol in symbols
        ]
        census["relocations"] = [
            {
                "id": stable_id("relocation", item.index),
                "index": item.index,
                "offset": item.offset,
                "symbol_index": item.symbol_index,
                "type": item.type_name,
                "addend": item.addend,
            }
            for item in relocations
        ]
    return census


def verify_census(census: dict[str, Any]) -> list[str]:
    errors = []
    reference = census["reference"]
    header = census["elf_header"]
    if str(reference["sha256"]).casefold() != REFERENCE_SHA256:
        errors.append(
            f"reference SHA-256 mismatch: {reference['sha256']} != {REFERENCE_SHA256}"
        )
    if header["machine"] != EXPECTED_MACHINE:
        errors.append(f"ELF machine {header['machine']} is not EM_MIPS")
    if header["entry"] != EXPECTED_ENTRY:
        errors.append(
            f"ELF entry 0x{header['entry']:x} != expected 0x{EXPECTED_ENTRY:x}"
        )
    if header["section_count"] != EXPECTED_SECTION_COUNT:
        errors.append(
            f"section count {header['section_count']} != {EXPECTED_SECTION_COUNT}"
        )
    if census["symbol_summary"]["count"] != EXPECTED_SYMBOL_COUNT:
        errors.append(
            f"symbol count {census['symbol_summary']['count']} != "
            f"{EXPECTED_SYMBOL_COUNT}"
        )
    if census["relocation_summary"]["count"] != EXPECTED_RELOCATION_COUNT:
        errors.append(
            f"relocation count {census['relocation_summary']['count']} != "
            f"{EXPECTED_RELOCATION_COUNT}"
        )
    if EXPECTED_COMPILER_COMMENT not in census["comments"]:
        errors.append(
            f"missing compiler comment {EXPECTED_COMPILER_COMMENT!r}"
        )
    if "PlayStation2" not in census["comments"]:
        errors.append("missing PlayStation2 target comment")
    return errors


def require_valid_census(census: dict[str, Any]) -> None:
    if errors := verify_census(census):
        raise SocomError("reference census failed:\n- " + "\n- ".join(errors))

