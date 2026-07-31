"""Pinned Metrowerks PS2 toolchain acquisition and validation."""

from __future__ import annotations

import io
import os
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from .constants import (
    TOOLCHAIN_ARCHIVE_SHA256,
    TOOLCHAIN_ARCHIVE_URL,
    TOOLCHAIN_BANNER,
    TOOLCHAIN_ID,
    TOOLCHAIN_INTERNAL_SIGNATURE,
    TOOLCHAIN_UPSTREAM_COMMIT,
)
from .util import SocomError, atomic_write_json, sha256_file

EXPECTED_FILES = {
    "asm_r5900_elf.exe": {
        "size": 534_632,
        "sha256": "6f215bcca5bc11028dd358b1b4c34d69020e35516de2c81a88cc627ede6683b3",
    },
    "LMGR326B.DLL": {
        "size": 306_688,
        "sha256": "bd9415ab11f4aef42c372e8547a8303b02464b59549745be597cf09e460737e8",
    },
    "mwccps2.exe": {
        "size": 1_379_328,
        "sha256": "98d3fb6fc362c6b28208e1cc05ff25e32b7c78ffca0c3114cde5392a67c06294",
    },
    "mwldps2.exe": {
        "size": 532_992,
        "sha256": "9d161412e67bb96d3b0c6f75b89eb9ebc2b7601215cbd2565c6cb814c40e2737",
    },
}


def toolchain_directory(root: Path) -> Path:
    return root / "compiler" / TOOLCHAIN_ID


def provenance(root: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "toolchain_id": TOOLCHAIN_ID,
        "platform": "PlayStation 2",
        "target": "MIPS/R5900",
        "source": {
            "repository": "https://github.com/decompme/compilers",
            "commit": TOOLCHAIN_UPSTREAM_COMMIT,
            "asset_url": TOOLCHAIN_ARCHIVE_URL,
            "archive_sha256": TOOLCHAIN_ARCHIVE_SHA256,
        },
        "identity": {
            "driver_banner_fragment": TOOLCHAIN_BANNER,
            "compiler_object_signature": TOOLCHAIN_INTERNAL_SIGNATURE,
            "linker_banner_fragment": TOOLCHAIN_BANNER,
            "assembler_banner": "Metrowerks Assembler Version 2.1.1 Build 0910",
            "reference_comment": "MW MIPS C Compiler (2.4.1.01)",
        },
        "files": [
            {
                "path": f"{TOOLCHAIN_ID}/{name}",
                "size": metadata["size"],
                "sha256": metadata["sha256"],
            }
            for name, metadata in EXPECTED_FILES.items()
        ],
        "licensing": {
            "status": "not-provided-by-upstream-archive",
            "note": (
                "The upstream compiler archive contains no license.dat. "
                "Compilation on native Windows requires a valid FLEXlm license; "
                "this workspace does not provide or bypass one."
            ),
        },
    }


def bootstrap_toolchain(root: Path, *, force: bool = False) -> dict[str, Any]:
    destination = toolchain_directory(root)
    if destination.exists() and not force:
        report = verify_toolchain(root, compile_probe=False)
        if not report["identity_ok"]:
            raise SocomError(
                "toolchain directory exists but fails identity checks; "
                "use --force only after reviewing its contents"
            )
        return report

    with urllib.request.urlopen(TOOLCHAIN_ARCHIVE_URL, timeout=60) as response:
        archive = response.read()
    import hashlib

    digest = hashlib.sha256(archive).hexdigest()
    if digest != TOOLCHAIN_ARCHIVE_SHA256:
        raise SocomError(
            f"toolchain archive SHA-256 {digest} != {TOOLCHAIN_ARCHIVE_SHA256}"
        )
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        members = bundle.getmembers()
        names = {Path(member.name).as_posix() for member in members if member.isfile()}
        if names != set(EXPECTED_FILES):
            raise SocomError(
                f"unexpected compiler archive inventory: {sorted(names)}"
            )
        extracted: dict[str, bytes] = {}
        for member in members:
            if not member.isfile():
                continue
            if Path(member.name).name != member.name:
                raise SocomError(f"unsafe compiler archive path: {member.name}")
            stream = bundle.extractfile(member)
            if stream is None:
                raise SocomError(f"cannot read compiler archive member {member.name}")
            extracted[member.name] = stream.read()

    destination.mkdir(parents=True, exist_ok=True)
    for name, payload in extracted.items():
        metadata = EXPECTED_FILES[name]
        import hashlib

        file_digest = hashlib.sha256(payload).hexdigest()
        if len(payload) != metadata["size"] or file_digest != metadata["sha256"]:
            raise SocomError(f"compiler member {name} failed pinned size/hash checks")
        (destination / name).write_bytes(payload)
    atomic_write_json(root / "compiler" / "PROVENANCE.json", provenance(root))
    return verify_toolchain(root, compile_probe=False)


def _run(executable: Path, arguments: list[str], cwd: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [str(executable), *arguments],
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"exit_code": None, "output": str(exc)}
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    return {"exit_code": completed.returncode, "output": output}


def verify_toolchain(root: Path, *, compile_probe: bool = True) -> dict[str, Any]:
    directory = toolchain_directory(root)
    errors = []
    files = []
    for name, expected in EXPECTED_FILES.items():
        path = directory / name
        if not path.is_file():
            errors.append(f"missing {path.relative_to(root).as_posix()}")
            continue
        actual = {"size": path.stat().st_size, "sha256": sha256_file(path)}
        files.append({"name": name, **actual})
        if actual["size"] != expected["size"]:
            errors.append(f"{name} size mismatch")
        if actual["sha256"] != expected["sha256"]:
            errors.append(f"{name} SHA-256 mismatch")
    if directory.is_dir():
        unexpected = sorted(
            path.name
            for path in directory.iterdir()
            if path.is_file()
            and path.name not in EXPECTED_FILES
            and path.name.casefold() != "license.dat"
        )
        if unexpected:
            errors.append(f"unexpected toolchain files: {unexpected}")

    compiler = directory / "mwccps2.exe"
    linker = directory / "mwldps2.exe"
    assembler = directory / "asm_r5900_elf.exe"
    version = (
        _run(compiler, ["-version"], directory)
        if compiler.is_file()
        else {"exit_code": None, "output": "compiler missing"}
    )
    if TOOLCHAIN_BANNER not in version["output"]:
        errors.append(f"compiler banner is missing {TOOLCHAIN_BANNER!r}")
    internal_signature = (
        TOOLCHAIN_INTERNAL_SIGNATURE.encode("ascii") in compiler.read_bytes()
        if compiler.is_file()
        else False
    )
    if not internal_signature:
        errors.append(
            f"compiler executable is missing internal signature "
            f"{TOOLCHAIN_INTERNAL_SIGNATURE!r}"
        )
    linker_version = (
        _run(linker, ["-version"], directory)
        if linker.is_file()
        else {"exit_code": None, "output": "linker missing"}
    )
    if TOOLCHAIN_BANNER not in linker_version["output"]:
        errors.append(f"linker banner is missing {TOOLCHAIN_BANNER!r}")
    assembler_version = (
        _run(assembler, [], directory)
        if assembler.is_file()
        else {"exit_code": None, "output": "assembler missing"}
    )
    if "Metrowerks Assembler Version 2.1.1 Build 0910" not in assembler_version["output"]:
        errors.append("assembler banner does not match Version 2.1.1 Build 0910")

    compile_result: dict[str, Any] = {
        "attempted": False,
        "ready": None,
        "deterministic": None,
        "blocked_by_license": None,
        "runs": [],
    }
    if compile_probe and compiler.is_file() and not errors:
        compile_result["attempted"] = True
        with tempfile.TemporaryDirectory(prefix="socom-mwcc-probe-") as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / "probe.cpp"
            source.write_text(
                'extern "C" int socom_probe(int x) { return x * 3 + 7; }\n',
                encoding="ascii",
                newline="\r\n",
            )
            digests = []
            for number in (1, 2):
                output = temporary / f"probe-{number}.o"
                run = _run(
                    compiler,
                    ["-c", "-nodefaults", "-o", str(output), str(source)],
                    directory,
                )
                run["object_created"] = output.is_file()
                if output.is_file():
                    run["object_sha256"] = sha256_file(output)
                    run["object_size"] = output.stat().st_size
                    digests.append(run["object_sha256"])
                compile_result["runs"].append(run)
            combined_output = "\n".join(
                str(run["output"]) for run in compile_result["runs"]
            )
            compile_result["blocked_by_license"] = "License check failed" in combined_output
            compile_result["ready"] = len(digests) == 2
            compile_result["deterministic"] = (
                len(digests) == 2 and len(set(digests)) == 1
            )

    identity_ok = not errors
    return {
        "toolchain_id": TOOLCHAIN_ID,
        "directory": directory.relative_to(root).as_posix(),
        "identity_ok": identity_ok,
        "compile_ready": compile_result["ready"],
        "errors": errors,
        "files": files,
        "version_probe": version,
        "linker_version_probe": linker_version,
        "assembler_version_probe": assembler_version,
        "internal_signature_found": internal_signature,
        "compile_probe": compile_result,
    }
