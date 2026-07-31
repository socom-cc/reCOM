"""Fail-closed typed coverage catalog for the reference ELF."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .elf import Elf32File
from .tracker import load_tracker

SEMANTIC_KINDS = {"code", "data", "provider", "padding", "zero-fill"}


def _interval(start: int, end: int, *, kind: str, source: str) -> dict[str, Any]:
    return {"start": start, "end": end, "size": end - start, "kind": kind, "source": source}


def _union(rows: Iterable[dict[str, Any]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for row in sorted(rows, key=lambda value: (value["start"], value["end"])):
        start, end = int(row["start"]), int(row["end"])
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def _gaps(targets: Iterable[tuple[int, int]], coverage: Iterable[dict[str, Any]]) -> list[dict[str, int]]:
    merged = _union(coverage)
    result: list[dict[str, int]] = []
    for target_start, target_end in targets:
        cursor = target_start
        for start, end in merged:
            if end <= cursor or start >= target_end:
                continue
            if start > cursor:
                result.append({"start": cursor, "end": min(start, target_end), "size": min(start, target_end) - cursor})
            cursor = max(cursor, min(end, target_end))
            if cursor >= target_end:
                break
        if cursor < target_end:
            result.append({"start": cursor, "end": target_end, "size": target_end - cursor})
    return result


def _overlaps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    ordered = sorted(rows, key=lambda value: (value["start"], value["end"]))
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if right["start"] >= left["end"]:
                break
            if right["end"] > left["start"]:
                result.append(
                    {
                        "range": [max(left["start"], right["start"]), min(left["end"], right["end"])],
                        "sources": [left["source"], right["source"]],
                    }
                )
    return result


def final_elf_catalog(root: Path) -> dict[str, Any]:
    elf = Elf32File(root / "support" / "socom.elf")
    tracker = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    header = elf.header
    mechanical = [
        _interval(0, header.header_size, kind="elf-header", source="ELF header"),
        _interval(header.program_offset, header.program_offset + header.program_entry_size * header.program_count, kind="program-header-table", source="ELF program headers"),
        _interval(header.section_offset, header.section_offset + header.section_entry_size * header.section_count, kind="section-header-table", source="ELF section headers"),
    ]
    loaded_file_targets: list[tuple[int, int]] = []
    loaded_memory_targets: list[tuple[int, int]] = []
    load_file_ranges: list[tuple[int, int]] = []
    for segment in elf.load_segments():
        if segment.file_size:
            loaded_file_targets.append((segment.offset, segment.offset + segment.file_size))
            load_file_ranges.append((segment.offset, segment.offset + segment.file_size))
        if segment.memory_size:
            loaded_memory_targets.append((segment.virtual_address, segment.virtual_address + segment.memory_size))
    for section in elf.sections:
        if not section.file_backed:
            continue
        section_range = (section.offset, section.offset + section.size)
        if any(start <= section.offset and section_range[1] <= end for start, end in load_file_ranges):
            continue
        mechanical.append(_interval(*section_range, kind="nonloaded-section", source=f"section:{section.name or '<null>'}"))

    semantic_file: list[dict[str, Any]] = []
    semantic_memory: list[dict[str, Any]] = []
    excluded_reference_rows = 0
    ambiguous_providers: list[str] = []
    invalid_rows: list[str] = []
    for collection in ("semantic_spans", "storage_contributions"):
        for row in tracker.get(collection, []):
            if row.get("status") != "accepted":
                if row.get("status") == "reference-evidence":
                    excluded_reference_rows += 1
                continue
            identifier = str(row.get("id", "<unknown>"))
            kind = str(row.get("classification") or row.get("kind") or "")
            if kind not in SEMANTIC_KINDS:
                invalid_rows.append(f"{identifier}: missing accepted semantic classification")
                continue
            if kind == "provider" and not row.get("provider"):
                ambiguous_providers.append(identifier)
            for key, target in (("file_range", semantic_file), ("memory_range", semantic_memory)):
                value = row.get(key)
                if value is None:
                    continue
                if not isinstance(value, list) or len(value) != 2 or not all(isinstance(part, int) for part in value) or value[1] <= value[0]:
                    invalid_rows.append(f"{identifier}: invalid {key}")
                    continue
                target.append(_interval(value[0], value[1], kind=kind, source=identifier))

    loaded_file_gaps = _gaps(loaded_file_targets, semantic_file)
    loaded_memory_gaps = _gaps(loaded_memory_targets, semantic_memory)
    whole_file_coverage = [*mechanical, *semantic_file]
    whole_file_gaps = _gaps([(0, len(elf.data))], whole_file_coverage)
    file_overlaps = _overlaps(semantic_file)
    memory_overlaps = _overlaps(semantic_memory)
    errors: list[str] = []
    if loaded_file_gaps:
        errors.append(f"{len(loaded_file_gaps)} loaded file ranges lack accepted semantic coverage")
    if loaded_memory_gaps:
        errors.append(f"{len(loaded_memory_gaps)} loaded memory ranges lack accepted semantic coverage")
    if whole_file_gaps:
        errors.append(f"{len(whole_file_gaps)} file ranges remain untyped")
    if file_overlaps or memory_overlaps:
        errors.append("accepted semantic coverage contains overlaps")
    if ambiguous_providers:
        errors.append("accepted provider coverage has ambiguous provider identities")
    errors.extend(invalid_rows)
    return {
        "ok": not errors,
        "complete": not errors,
        "mechanical_interval_count": len(mechanical),
        "semantic_file_interval_count": len(semantic_file),
        "semantic_memory_interval_count": len(semantic_memory),
        "excluded_reference_evidence_rows": excluded_reference_rows,
        "loaded_file_gaps": loaded_file_gaps,
        "loaded_memory_gaps": loaded_memory_gaps,
        "whole_file_gaps": whole_file_gaps,
        "file_overlaps": file_overlaps,
        "memory_overlaps": memory_overlaps,
        "ambiguous_providers": ambiguous_providers,
        "invalid_rows": invalid_rows,
        "errors": errors,
    }
