"""Typed ELF comparisons used by linked and final validation."""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path
from typing import Any

from .elf import Elf32File
from .util import SocomError, sha256_file

LINKED_SECTIONS = ("main", "heap", ".mwcats", ".relmain", ".comment", ".reginfo")


def _difference_ranges(reference: bytes, candidate: bytes, limit: int = 100) -> dict[str, Any]:
    maximum = max(len(reference), len(candidate))
    ranges: list[dict[str, int]] = []
    different_bytes = 0
    start: int | None = None
    for index in range(maximum):
        left = reference[index] if index < len(reference) else None
        right = candidate[index] if index < len(candidate) else None
        differs = left != right
        if differs:
            different_bytes += 1
            if start is None:
                start = index
        elif start is not None:
            if len(ranges) < limit:
                ranges.append({"start": start, "end": index, "size": index - start})
            start = None
    if start is not None and len(ranges) < limit:
        ranges.append({"start": start, "end": maximum, "size": maximum - start})
    return {
        "different_byte_count": different_bytes,
        "range_count_at_least": len(ranges),
        "ranges_truncated": different_bytes > sum(row["size"] for row in ranges),
        "first_ranges": ranges,
    }


def compare_elf(
    reference_path: Path,
    candidate_path: Path,
    *,
    mode: str,
) -> dict[str, Any]:
    if mode not in {"linked", "final"}:
        raise SocomError(f"unknown ELF comparison mode: {mode}")
    reference = Elf32File(reference_path)
    candidate = Elf32File(candidate_path)
    errors = []

    header_fields = (
        "elf_class",
        "data_encoding",
        "elf_type",
        "machine",
        "version",
        "entry",
        "flags",
        "header_size",
        "program_entry_size",
        "program_count",
        "section_entry_size",
        "section_count",
        "section_name_index",
    )
    header_differences = {
        name: {
            "reference": getattr(reference.header, name),
            "candidate": getattr(candidate.header, name),
        }
        for name in header_fields
        if getattr(reference.header, name) != getattr(candidate.header, name)
    }
    if header_differences:
        errors.append("ELF header semantics differ")

    program_headers_equal = reference.program_headers == candidate.program_headers
    if not program_headers_equal:
        errors.append("program headers differ")

    reference_sections = {section.name: section for section in reference.sections}
    candidate_sections = {section.name: section for section in candidate.sections}
    section_names = (
        list(reference_sections)
        if mode == "final"
        else list(LINKED_SECTIONS)
    )
    section_results = []
    for name in section_names:
        left = reference_sections.get(name)
        right = candidate_sections.get(name)
        if not left or not right:
            section_results.append(
                {
                    "name": name,
                    "ok": False,
                    "error": "section missing",
                    "reference_present": left is not None,
                    "candidate_present": right is not None,
                }
            )
            errors.append(f"section {name!r} is missing")
            continue
        metadata_fields = (
            "type",
            "flags",
            "address",
            "size",
            "link",
            "info",
            "alignment",
            "entry_size",
        )
        metadata_differences = {
            field: {
                "reference": getattr(left, field),
                "candidate": getattr(right, field),
            }
            for field in metadata_fields
            if getattr(left, field) != getattr(right, field)
        }
        left_data = reference.section_data(left)
        right_data = candidate.section_data(right)
        content_equal = left_data == right_data
        ok = not metadata_differences and content_equal
        if not ok:
            errors.append(f"section {name!r} differs")
        section_results.append(
            {
                "name": name,
                "ok": ok,
                "metadata_differences": metadata_differences,
                "reference_sha256": hashlib.sha256(left_data).hexdigest(),
                "candidate_sha256": hashlib.sha256(right_data).hexdigest(),
                "difference": (
                    None
                    if content_equal
                    else _difference_ranges(left_data, right_data, limit=20)
                ),
            }
        )

    symbol_equal = reference.symbols() == candidate.symbols()
    relocation_equal = reference.relocations() == candidate.relocations()
    mwcats_equal = reference.mwcats() == candidate.mwcats()
    comments_equal = reference.comments() == candidate.comments()
    if mode == "final":
        if not symbol_equal:
            errors.append("symbol table differs")
        if not relocation_equal:
            errors.append("relocation table differs")
        if not mwcats_equal:
            errors.append(".mwcats records differ")
        if not comments_equal:
            errors.append("compiler/target comments differ")

    reference_bytes = reference_path.read_bytes()
    candidate_bytes = candidate_path.read_bytes()
    whole_file_equal = reference_bytes == candidate_bytes
    whole_file_difference = (
        None
        if whole_file_equal
        else _difference_ranges(reference_bytes, candidate_bytes)
    )
    if mode == "final" and not whole_file_equal:
        errors.append("whole-file bytes differ after typed comparison")

    return {
        "mode": mode,
        "ok": not errors,
        "reference": {
            "path": reference_path.as_posix(),
            "sha256": sha256_file(reference_path),
            "size": len(reference_bytes),
        },
        "candidate": {
            "path": candidate_path.as_posix(),
            "sha256": sha256_file(candidate_path),
            "size": len(candidate_bytes),
        },
        "header_differences": header_differences,
        "program_headers_equal": program_headers_equal,
        "sections": section_results,
        "symbol_table_equal": symbol_equal,
        "relocation_table_equal": relocation_equal,
        "mwcats_equal": mwcats_equal,
        "comments_equal": comments_equal,
        "whole_file_equal": whole_file_equal,
        "whole_file_difference": whole_file_difference,
        "errors": errors,
    }

