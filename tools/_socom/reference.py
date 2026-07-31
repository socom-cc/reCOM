"""Target-specific reference-evidence queries."""

from __future__ import annotations

from typing import Any

from .util import SocomError


def query_relocations(
    census: dict[str, Any],
    *,
    at: str | None = None,
    size: int = 1,
    symbol: str | None = None,
    relocation_type: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    if size < 1:
        raise SocomError("relocation query size must be positive")
    if limit < 1:
        raise SocomError("relocation query limit must be positive")
    start = int(at, 0) if at is not None else None
    end = start + size if start is not None else None
    symbols = {int(row["index"]): row for row in census.get("symbols", [])}
    relocations = {int(row["index"]): row for row in census.get("relocations", [])}
    pair_by_index: dict[int, dict[str, Any]] = {}
    for pair in census.get("relocation_summary", {}).get("hi16_lo16_groups", []):
        hi_indices = [int(value) for value in pair.get("hi16_indices", [])]
        lo_index = int(pair["lo16_index"])
        for index in hi_indices:
            pair_by_index[index] = {
                "pair_id": pair["id"],
                "role": "hi16",
                "partner_indices": [lo_index],
            }
        pair_by_index[lo_index] = {
            "pair_id": pair["id"],
            "role": "lo16",
            "partner_indices": hi_indices,
        }

    folded_symbol = symbol.casefold() if symbol else None
    folded_type = relocation_type.casefold() if relocation_type else None
    matches: list[dict[str, Any]] = []
    total_matches = 0
    for row in census.get("relocations", []):
        offset = int(row["offset"])
        target = symbols.get(int(row["symbol_index"]), {})
        if start is not None and not (start <= offset < end):
            continue
        if folded_symbol and folded_symbol not in str(target.get("name", "")).casefold():
            continue
        if folded_type and str(row.get("type", "")).casefold() != folded_type:
            continue
        total_matches += 1
        if len(matches) >= limit:
            continue
        pair = pair_by_index.get(int(row["index"]))
        pair_context = None
        if pair:
            pair_context = {
                **pair,
                "partners": [
                    {
                        "index": index,
                        "offset": relocations[index]["offset"],
                        "type": relocations[index]["type"],
                    }
                    for index in pair["partner_indices"]
                    if index in relocations
                ],
            }
        matches.append(
            {
                **row,
                "symbol": {
                    key: target.get(key)
                    for key in ("index", "name", "value", "size", "type", "binding")
                },
                "pair_context": pair_context,
            }
        )
    return {
        "ok": True,
        "query": {
            "at": at,
            "size": size if at is not None else None,
            "symbol": symbol,
            "type": relocation_type,
            "limit": limit,
        },
        "match_count": total_matches,
        "returned_count": len(matches),
        "omitted": max(0, total_matches - len(matches)),
        "relocations": matches,
    }
