"""Source guards adapted from the mature workspace for the PS2 target."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable

from .source import GENERIC_LOCAL_IDENTITIES
from .util import load_json

SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".inl"}

SOURCE_LOCAL_PATH_RE = re.compile(
    r"""(?:
        (?<![A-Za-z0-9])[A-Za-z]:\\
        |(?<![A-Za-z0-9])[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9._-]+
        |(?<![A-Za-z0-9])/(?:Users|home)/[A-Za-z0-9._-]+
    )""",
    re.IGNORECASE | re.VERBOSE,
)
ORIGINAL_SOURCE_PATH_RE = re.compile(
    "Z" + r""":[\\/]+dev(?:[\\/]+[^\s`'"<>|)]*)?""", re.IGNORECASE
)


def _source_files(root: Path) -> Iterable[Path]:
    for base in ("src", "include"):
        directory = root / base
        if directory.is_dir():
            yield from (
                path
                for path in sorted(directory.rglob("*"))
                if path.is_file() and path.suffix.casefold() in SOURCE_SUFFIXES
            )


def _scan(
    root: Path,
    patterns: tuple[tuple[str, re.Pattern[str]], ...],
    *,
    allowlist_kind: str | None = None,
) -> dict[str, Any]:
    allowed: set[tuple[str, int, str]] = set()
    allowlist_path = root / ".agent" / "RECONSTRUCTION_ALLOWLIST.json"
    if allowlist_kind and allowlist_path.is_file():
        payload = load_json(allowlist_path)
        for row in payload.get("entries", []):
            if row.get("kind") == allowlist_kind:
                allowed.add(
                    (
                        str(row.get("path", "")).replace("\\", "/"),
                        int(row.get("line", 0)),
                        str(row.get("rule", "")),
                    )
                )
    findings = []
    for path in _source_files(root):
        relative = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for number, line in enumerate(lines, 1):
            for rule, pattern in patterns:
                if pattern.search(line) and (relative, number, rule) not in allowed:
                    findings.append(
                        {
                            "rule": rule,
                            "path": relative,
                            "line": number,
                            "text": line.strip()[:240],
                        }
                    )
    return {"ok": not findings, "count": len(findings), "findings": findings}


GUARDS: dict[str, tuple[str, tuple[tuple[str, re.Pattern[str]], ...], str | None]] = {
    "modern-cpp": (
        "Reject constructs unavailable to the pinned 2000-era Metrowerks compiler.",
        (
            (
                "post-c++98-keyword",
                re.compile(
                    r"\b(?:nullptr|constexpr|decltype|noexcept|override|"
                    r"thread_local|static_assert|concept|consteval|constinit)\b"
                ),
            ),
            ("range-for", re.compile(r"\bfor\s*\([^;()]+:[^:][^;()]*\)")),
        ),
        "modern-cpp",
    ),
    "raw-assembly": (
        "Reject unreviewed inline/raw assembly in provisional source.",
        (
            ("inline-assembly", re.compile(r"\b(?:__asm__?|asm)\b")),
            ("raw-instruction", re.compile(r"^\s*\.(?:word|half|byte)\s+0x")),
        ),
        "raw-assembly",
    ),
    "raw-image": (
        "Reject hard-coded addresses in the original PS2 image range.",
        (
            (
                "raw-image-address",
                re.compile(
                    r"\b0x(?:[1-3][0-9a-f]{5}|4[0-6][0-9a-f]{4}|"
                    r"47[0-4][0-9a-f]{3}|475[0-5][0-9a-f]{2}|5e7f00)\b",
                    re.I,
                ),
            ),
        ),
        "raw-image",
    ),
    "reinterpret-cast": (
        "Reject C++ reinterpret_cast as a substitute for recovered types.",
        (("reinterpret-cast", re.compile(r"\breinterpret_cast\s*<")),),
        "reinterpret-cast",
    ),
    "raw-offset": (
        "Reject numeric byte/void pointer offsets used as recovered fields.",
        (
            (
                "numeric-byte-pointer-offset",
                re.compile(
                    r"(?:\(\s*(?:void|char|unsigned\s+char|u?int8_t|std::byte)\s*\*\s*\)"
                    r"|(?:reinterpret|static)_cast\s*<\s*(?:void|char|unsigned\s+char|u?int8_t|std::byte)\s*\*\s*>)"
                    r"\s*(?![A-Za-z_]\w*\s*\()[A-Za-z_]\w*"
                    r"(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*\s*"
                    r"(?:\+|-)\s*(?:0x[0-9a-f]+|[1-9][0-9]*)\b",
                    re.I,
                ),
            ),
            (
                "numeric-member-dereference",
                re.compile(
                    r"\*\s*\(\s*[^;\n]+?\*\s*\)\s*\([^;\n]+?"
                    r"(?:\+|-)\s*(?:0x[0-9a-f]+|[1-9][0-9]*)\s*\)",
                    re.I,
                ),
            ),
        ),
        "raw-offset",
    ),
    "provider": (
        "Reject explicit reconstruction shims, stubs, fakes, and dummy providers.",
        (
            (
                "placeholder-provider-identity",
                re.compile(
                    r"\b(?=[A-Za-z0-9_]*(?:provider|runtime|middleware|sdk))"
                    r"(?=[A-Za-z0-9_]*(?:shim|stub|fake|dummy))"
                    r"[A-Za-z_][A-Za-z0-9_]*\b",
                    re.I,
                ),
            ),
            (
                "placeholder-provider-annotation",
                re.compile(
                    r"@socom-(?:provider|artifact)[^\n]*\b(?:shim|stub|fake|dummy)\b",
                    re.I,
                ),
            ),
        ),
        "provider",
    ),
    "original-symbol": (
        "Reject Ghidra autogenerated identities as authored source dependencies.",
        (
            (
                "ghidra-autogenerated-symbol",
                re.compile(r"\b(?:FUN|DAT|LAB|PTR|UNK)_[0-9a-f]{4,}\b", re.I),
            ),
        ),
        "original-symbol",
    ),
    "source-fragments": (
        "Reject production .inl files and quoted inclusion of source files.",
        (
            ("quoted-source-include", re.compile(r'#\s*include\s+"[^"]+\.(?:c|cc|cpp|cxx)"')),
            ("inl-include", re.compile(r'#\s*include\s+"[^"]+\.inl"')),
        ),
        "source-fragments",
    ),
    "source-shape": (
        "Reject common source-shape scaffolds which hide unrecovered semantics.",
        (
            ("placeholder-todo", re.compile(r"\b(?:TODO|FIXME)\b.*\b(?:reconstruct|decomp|unknown)\b", re.I)),
            ("unimplemented-stub", re.compile(r"\b(?:UNIMPLEMENTED|NOT_IMPLEMENTED)\b")),
        ),
        "source-shape",
    ),
}


def run_guard(root: Path, name: str) -> dict[str, Any]:
    if name not in GUARDS:
        return {
            "ok": False,
            "guard": name,
            "error": f"unknown guard: {name}",
            "available": sorted(GUARDS),
        }
    summary, patterns, allowlist = GUARDS[name]
    result = _scan(root, patterns, allowlist_kind=allowlist)
    return {"guard": name, "summary": summary, **result}


def source_placement(root: Path) -> dict[str, Any]:
    findings = []
    dynamic_patterns: list[re.Pattern[str]] = []
    path_values = {
        str(root.resolve()),
        os.environ.get("USERPROFILE"),
        os.environ.get("HOME"),
        str(Path.home()),
    }
    seen_values: set[str] = set()
    for value in path_values:
        if not value:
            continue
        for variant in {value, value.replace("\\", "/"), value.replace("/", "\\")}:
            folded = variant.casefold()
            if len(variant) < 3 or folded in seen_values:
                continue
            seen_values.add(folded)
            dynamic_patterns.append(re.compile(re.escape(variant), re.IGNORECASE))
    for value in (os.environ.get("USERNAME") or os.environ.get("USER"), os.environ.get("COMPUTERNAME")):
        if (
            not value
            or len(value) < 4
            or value.casefold() in GENERIC_LOCAL_IDENTITIES
        ):
            continue
        dynamic_patterns.append(
            re.compile(
                rf"(?<![A-Za-z0-9_-]){re.escape(value)}(?![A-Za-z0-9_-])",
                re.IGNORECASE,
            )
        )
    for path in _source_files(root):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            scrubbed = ORIGINAL_SOURCE_PATH_RE.sub("", line)
            if not SOURCE_LOCAL_PATH_RE.search(scrubbed) and not any(
                pattern.search(scrubbed) for pattern in dynamic_patterns
            ):
                continue
            findings.append(
                {
                    "path": relative,
                    "line": number,
                    "text": line.strip()[:240],
                }
            )
    return {
        "ok": not findings,
        "guard": "source-placement",
        "count": len(findings),
        "findings": findings,
    }
