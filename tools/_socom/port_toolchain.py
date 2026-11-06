"""Pinned open-source ps2dev toolchain (GCC and ps2sdk) for the functional port lane.

The functional port builds the game with the ps2dev release pinned below.  It is
a separate lane: it never substitutes for the Metrowerks exact-compiler evidence
of the ``toolchain`` commands or for any matching stage.

The release is a glibc x86_64 Linux build, so every step runs in a Linux
environment: ``bash -s`` on Linux, or ``wsl.exe [-d <distro>] --cd ~ -- bash -s``
on Windows.  The script always travels on stdin, so no Windows path crosses into
Linux, and it sets its own ``PS2DEV``, ``PS2SDK`` and ``PATH``: a host ``PS2DEV``
or ``PS2SDK``, or another ps2dev installed elsewhere in the Linux environment, is
never read, used or changed.  The script reports through ``@@socom key=value``
lines on stdout; everything else it prints is diagnostic output.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .elf import PT_LOAD, Elf32File
from .util import SocomError

RELEASE: dict[str, Any] = {
    "repository": "https://github.com/ps2dev/ps2dev",
    "tag": "v2.0.0",
    "tag_object": "69d11750230d8ece4139104731394af7ec2169a2",
    "published": "2026-05-17",
    "asset": "ps2dev-ubuntu-latest.tar.gz",
    "url": "https://github.com/ps2dev/ps2dev/releases/download/v2.0.0/ps2dev-ubuntu-latest.tar.gz",
    "size": 266_096_645,
    "sha256": "c8e5dedccf62084d476894e88cd0451b57f1ed288e741eb3c1263010aaffc028",
}

INSTALL_VARIABLE = "SOCOM_PS2DEV"
DISTRO_VARIABLE = "SOCOM_WSL_DISTRO"
# Both relative to the Linux $HOME.
DEFAULT_INSTALL = ".local/share/socom/ps2dev-v2.0.0"
DOWNLOAD_CACHE = ".cache/socom/downloads/ps2dev-v2.0.0"
ARCHIVE_NAME = "ps2dev.tar.gz"

# The release's top level under ps2dev/ (test.tmp ships in the archive itself).
INSTALL_TOP_LEVEL = ("bin", "dvp", "ee", "gsKit", "iop", "ps2sdk", "share", "test.tmp")

# Read from the pinned archive's members; relative to the install directory.
EXPECTED_FILES: dict[str, tuple[int, str]] = {
    "share/ps2dev.cmake": (2_060, "dd8b3d817d56d465f6205710ca03581cfb8e5ab5ae217b6e3bbd276543b65a10"),
    "ee/bin/mips64r5900el-ps2-elf-gcc": (2_030_344, "5c0edc1bad39523295932a42c024849c6143fbde200b0f602ed6b2db77d5b3fa"),
    "ee/bin/mips64r5900el-ps2-elf-g++": (2_034_440, "04212da9b41c83d31f478060b3af9619fcadb8d0381187006ee0df388e118f6d"),
    "iop/bin/mipsel-none-elf-gcc": (2_030_312, "f5e342cd120803ee2a0b5d112ee382314c733532d01d4723d5be9ab0558c1683"),
    "dvp/bin/dvp-as": (2_195_224, "e3953d8a6cec9db1abc07c50cf42d72fda5ed09bca3b1f431623adce2e7408da"),
    "ps2sdk/ee/startup/linkfile": (1_936, "89698a0ffdc030dd647a3f98827ecac0933b1ef31c8a11397b1883abb796e28d"),
    "ps2sdk/ee/lib/libkernel.a": (1_403_532, "fb31fbe66c3772ef76ffac2aaafe1f90b68ed423cb8ba0b5e536d01b21320061"),
    "ps2sdk/ee/lib/libdebug.a": (102_096, "acc5a8d69b8327531ccebd4c504a0bbd5d630c4dc76401b6d73da9fc51c945d8"),
    "ps2sdk/ee/include/kernel.h": (20_577, "fe34ea02834f0b74199e8832e4d85641ce0f231c9d0c4e6d7f6b67b7d499814a"),
    "ps2sdk/ee/include/debug.h": (1_350, "d2c0300d748bb9edfd0761ec6687e4be6fc5b955b3bee399ac5a23eef22b442e"),
    "ee/mips64r5900el-ps2-elf/lib/libstdc++.a": (5_690_280, "b49e2d3d925ca7e9e8dd67e82d108eb59863471476ffc4e5d2da5d6b7e954128"),
    "ee/mips64r5900el-ps2-elf/lib/crt0.o": (16_320, "e4031ab9e07464b06dd13613e7c7ad4b29dfa1400d3ab74eb1e446a86452f7b0"),
}

# First line of `<tool> --version`.
BANNERS: dict[str, str] = {
    "ee/bin/mips64r5900el-ps2-elf-gcc": "mips64r5900el-ps2-elf-gcc (GCC) 15.2.0",
    "ee/bin/mips64r5900el-ps2-elf-g++": "mips64r5900el-ps2-elf-g++ (GCC) 15.2.0",
    "iop/bin/mipsel-none-elf-gcc": "mipsel-none-elf-gcc (GCC) 15.2.0",
}

# Inherited variables the scripts clear before setting their own toolchain environment.
CLEARED_LINUX_VARIABLES = (
    "PS2DEV", "PS2SDK", "GSKIT", "PS2SDKSRC", "CC", "CXX", "CFLAGS", "CXXFLAGS",
    "CPPFLAGS", "LDFLAGS", "MAKEFLAGS", "CMAKE_TOOLCHAIN_FILE", "CMAKE_GENERATOR",
)
# Host variables never handed to wsl.exe (WSLENV would forward them).
CLEARED_HOST_VARIABLES = ("PS2DEV", "PS2SDK", "GSKIT", "WSLENV")

EM_MIPS = 8
ET_EXEC = 2
EF_MIPS_ABI2 = 0x0000_0020
EF_MIPS_MACH = 0x00FF_0000
EF_MIPS_MACH_5900 = 0x0092_0000
LOAD_BASE = 0x0010_0000

IDENTITY_TIMEOUT = 300
PROBE_TIMEOUT = 900
BOOTSTRAP_TIMEOUT = 3_600

NOTE = (
    "Functional-port lane: the open-source ps2dev toolchain (GCC and ps2sdk). It never "
    "substitutes for the Metrowerks exact-compiler evidence or for any matching stage."
)

PROBE_CMAKELISTS = """\
cmake_minimum_required(VERSION 3.13)
project(socom_port_probe C CXX)
add_executable(probe probe.cpp)
set_target_properties(probe PROPERTIES SUFFIX ".elf")
# The ps2sdk EE libraries carry LTO bytecode, so the link writes its own
# directory into DWARF: map both trees to fixed names at compile and link time.
set(SOCOM_PROBE_PREFIX_MAPS
    "-ffile-prefix-map=${CMAKE_SOURCE_DIR}=/socom-port-probe/src"
    "-ffile-prefix-map=${CMAKE_BINARY_DIR}=/socom-port-probe/build")
target_compile_options(probe PRIVATE -fno-exceptions -fno-rtti ${SOCOM_PROBE_PREFIX_MAPS})
target_link_options(probe PRIVATE ${SOCOM_PROBE_PREFIX_MAPS})
# `debug` is a CMake keyword: name the ps2sdk library as a linker flag.
target_link_libraries(probe PRIVATE -ldebug)
"""

PROBE_SOURCE = """\
#include <debug.h>
#include <kernel.h>
#include <math.h>

static int g_constructed = 0;
volatile float g_radius = 2.0f;

struct CStaticProbe {
    CStaticProbe() { g_constructed = 0x5C0; }
};
static CStaticProbe s_static_probe;

class CShape {
public:
    virtual ~CShape() {}
    virtual float Area() const = 0;
};

class CCircle : public CShape {
public:
    explicit CCircle(float radius) : m_radius(radius) {}
    virtual ~CCircle() {}
    virtual float Area() const { return 3.14159265f * m_radius * m_radius; }

private:
    float m_radius;
};

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;
    CShape *shape = new CCircle(g_radius);
    float area = shape->Area();
    float wave = sinf(area);
    delete shape;
    init_scr();
    scr_printf("socom port probe: ctor=%d area=%d wave=%d\\n", g_constructed,
               (int)(area * 1000.0f), (int)(wave * 1000.0f));
    SleepThread();
    return 0;
}
"""

MARKER = "@@socom "
_HARMLESS_STDERR = re.compile(r"^wsl: Failed to translate ")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


# ---------------------------------------------------------------------------
# Script generation


def install_expression(value: str | None) -> str:
    """Bash words naming the Linux install directory (``SOCOM_PS2DEV`` or the default)."""

    if value is None or not value.strip():
        return '"$HOME"/' + shlex.quote(DEFAULT_INSTALL)
    text = value.strip()
    if "\\" in text or _WINDOWS_DRIVE.match(text) or any(ch in text for ch in "\0\r\n"):
        raise SocomError(
            f"{INSTALL_VARIABLE} must be a Linux path inside the Linux environment, "
            "not a Windows path"
        )
    home_relative = None
    for prefix in ("~/", "$HOME/", "${HOME}/"):
        if text.startswith(prefix):
            home_relative = text[len(prefix):]
            break
    if home_relative is None and not text.startswith("/"):
        raise SocomError(
            f"{INSTALL_VARIABLE} must be an absolute Linux path, ~/... or $HOME/..."
        )
    parts = [part for part in (home_relative if home_relative is not None else text).split("/") if part]
    if ".." in parts or "." in parts:
        raise SocomError(f"{INSTALL_VARIABLE} must not contain . or .. components")
    if home_relative is not None:
        if not parts:
            raise SocomError(f"{INSTALL_VARIABLE} must name a directory below $HOME")
        return '"$HOME"/' + shlex.quote("/".join(parts))
    if len(parts) < 2:
        raise SocomError(f"{INSTALL_VARIABLE} must name a directory at least two levels below /")
    return shlex.quote("/" + "/".join(parts))


def _prelude(install: str) -> str:
    cleared = " ".join(CLEARED_LINUX_VARIABLES)
    return f"""\
set -u
umask 022
export LC_ALL=C
export PATH=/usr/bin:/bin
unset {cleared}
socom_emit() {{ printf '@@socom %s=%s\\n' "$1" "$2"; }}
socom_fail() {{ socom_emit error "$1"; exit 1; }}
socom_emit protocol 1
[ -n "${{HOME:-}}" ] || {{ socom_emit blocked "HOME is not set in the Linux environment"; exit 0; }}
socom_show() {{ case "$1" in "$HOME"/*) printf '$HOME/%s' "${{1#"$HOME"/}}" ;; *) printf '%s' "$1" ;; esac; }}
cd "$HOME" 2>/dev/null || cd /
socom_arch=$(uname -m)
socom_emit arch "$socom_arch"
case "$socom_arch" in
  x86_64) ;;
  *) socom_emit blocked "the pinned ps2dev release is an x86_64 Linux build; this environment is $socom_arch"; exit 0 ;;
esac
PS2DEV={install}
export PS2DEV
export PS2SDK="$PS2DEV/ps2sdk"
export PATH="$PS2DEV/bin:$PS2DEV/ee/bin:$PS2DEV/iop/bin:$PS2DEV/dvp/bin:$PS2SDK/bin:/usr/bin:/bin"
socom_emit install_dir "$(socom_show "$PS2DEV")"
"""


def _identity_section() -> str:
    files = "\n".join(EXPECTED_FILES)
    tools = " ".join(BANNERS)
    return f"""\
if [ -d "$PS2DEV" ]; then
  socom_emit installed 1
  ls -A1 "$PS2DEV" | while IFS= read -r socom_name; do socom_emit top_level "$socom_name"; done
  while IFS= read -r socom_rel; do
    if [ -f "$PS2DEV/$socom_rel" ]; then
      socom_emit file "$socom_rel $(stat -c %s "$PS2DEV/$socom_rel") $(sha256sum "$PS2DEV/$socom_rel" | cut -d ' ' -f 1)"
    else
      socom_emit file "$socom_rel missing"
    fi
  done <<'SOCOM_FILES_EOF'
{files}
SOCOM_FILES_EOF
  for socom_tool in {tools}; do
    if [ -x "$PS2DEV/$socom_tool" ]; then
      socom_emit banner "$socom_tool $("$PS2DEV/$socom_tool" --version 2>&1 | head -n 1)"
    else
      socom_emit banner "$socom_tool"
    fi
  done
else
  socom_emit installed 0
fi
"""


def _install_section(*, force: bool) -> str:
    return f"""\
SOCOM_FORCE={1 if force else 0}
SOCOM_URL={shlex.quote(RELEASE["url"])}
SOCOM_SHA256={shlex.quote(RELEASE["sha256"])}
SOCOM_SIZE={int(RELEASE["size"])}
SOCOM_CACHE="$HOME"/{shlex.quote(DOWNLOAD_CACHE)}
SOCOM_ARCHIVE="$SOCOM_CACHE"/{shlex.quote(ARCHIVE_NAME)}
for socom_tool in curl tar gzip sha256sum stat mktemp; do
  command -v "$socom_tool" >/dev/null 2>&1 || {{ socom_emit blocked "$socom_tool is not installed in the Linux environment"; exit 0; }}
done
socom_archive_ok() {{
  [ -f "$1" ] || return 1
  [ "$(stat -c %s "$1")" = "$SOCOM_SIZE" ] || return 1
  [ "$(sha256sum "$1" | cut -d ' ' -f 1)" = "$SOCOM_SHA256" ]
}}
mkdir -p -- "$SOCOM_CACHE" || socom_fail "cannot create the download cache $(socom_show "$SOCOM_CACHE")"
if socom_archive_ok "$SOCOM_ARCHIVE"; then
  socom_emit archive cached
else
  rm -f -- "$SOCOM_ARCHIVE" "$SOCOM_ARCHIVE.part"
  curl --fail --location --silent --show-error --retry 3 --retry-delay 5 --connect-timeout 30 \\
    --output "$SOCOM_ARCHIVE.part" "$SOCOM_URL" || socom_fail "downloading the pinned release asset failed"
  if ! socom_archive_ok "$SOCOM_ARCHIVE.part"; then
    socom_emit archive_actual "$(stat -c %s "$SOCOM_ARCHIVE.part") $(sha256sum "$SOCOM_ARCHIVE.part" | cut -d ' ' -f 1)"
    rm -f -- "$SOCOM_ARCHIVE.part"
    socom_fail "the downloaded archive does not match the pinned size and SHA-256"
  fi
  mv -f -- "$SOCOM_ARCHIVE.part" "$SOCOM_ARCHIVE" || socom_fail "cannot store the verified archive"
  socom_emit archive downloaded
fi
socom_parent=$(dirname -- "$PS2DEV")
mkdir -p -- "$socom_parent" || socom_fail "cannot create $(socom_show "$socom_parent")"
socom_stage=$(mktemp -d "$socom_parent/.socom-ps2dev-stage.XXXXXX") || socom_fail "cannot create a staging directory"
trap 'rm -rf -- "$socom_stage"' EXIT
tar -xzf "$SOCOM_ARCHIVE" -C "$socom_stage" --no-same-owner || socom_fail "extracting the verified archive failed"
[ "$(ls -A "$socom_stage")" = "ps2dev" ] || socom_fail "the archive's top level is not a single ps2dev directory"
[ -x "$socom_stage/ps2dev/ee/bin/mips64r5900el-ps2-elf-gcc" ] || socom_fail "the extracted tree has no EE compiler"
if [ -e "$PS2DEV" ] || [ -L "$PS2DEV" ]; then
  [ "$SOCOM_FORCE" = 1 ] || socom_fail "the install directory already exists"
  if [ -d "$PS2DEV/ee" ] || [ -d "$PS2DEV/ps2sdk" ] || [ -z "$(ls -A "$PS2DEV" 2>/dev/null)" ]; then
    mv -- "$PS2DEV" "$socom_stage/previous" || socom_fail "cannot move the previous install aside"
  else
    socom_fail "refusing to replace $(socom_show "$PS2DEV"): it does not look like a ps2dev install"
  fi
fi
if ! mv -- "$socom_stage/ps2dev" "$PS2DEV"; then
  [ -e "$socom_stage/previous" ] && mv -- "$socom_stage/previous" "$PS2DEV"
  socom_fail "cannot move the extracted tree into place"
fi
rm -rf -- "$socom_stage"
trap - EXIT
socom_emit installed_now 1
"""


def _probe_section() -> str:
    return f"""\
if [ -d "$PS2DEV" ]; then
  for socom_tool in cmake make; do
    command -v "$socom_tool" >/dev/null 2>&1 || {{ socom_emit blocked "$socom_tool is not installed in the Linux environment (install cmake and make)"; exit 0; }}
  done
  socom_emit cmake_version "$(cmake --version | head -n 1)"
  socom_probe=$(mktemp -d "${{TMPDIR:-/tmp}}/socom-port-probe.XXXXXX") || socom_fail "cannot create the probe directory"
  trap 'rm -rf -- "$socom_probe"' EXIT
  mkdir -- "$socom_probe/src" || socom_fail "cannot create the probe source directory"
  cat > "$socom_probe/src/CMakeLists.txt" <<'SOCOM_CMAKELISTS_EOF'
{PROBE_CMAKELISTS}SOCOM_CMAKELISTS_EOF
  cat > "$socom_probe/src/probe.cpp" <<'SOCOM_PROBE_EOF'
{PROBE_SOURCE}SOCOM_PROBE_EOF
  for socom_run in 1 2; do
    socom_build="$socom_probe/build$socom_run"
    socom_log="$socom_probe/build$socom_run.log"
    if cmake -S "$socom_probe/src" -B "$socom_build" -G "Unix Makefiles" \\
         -DCMAKE_TOOLCHAIN_FILE="$PS2DEV/share/ps2dev.cmake" > "$socom_log" 2>&1 \\
       && cmake --build "$socom_build" >> "$socom_log" 2>&1 \\
       && [ -f "$socom_build/probe.elf" ]; then
      socom_emit "run$socom_run" ok
      socom_emit "run${{socom_run}}_sha256" "$(sha256sum "$socom_build/probe.elf" | cut -d ' ' -f 1)"
      socom_emit "run${{socom_run}}_size" "$(stat -c %s "$socom_build/probe.elf")"
    else
      socom_emit "run$socom_run" failed
      tail -n 40 "$socom_log" | sed "s/^/build$socom_run: /"
    fi
  done
  if [ -f "$socom_probe/build1/probe.elf" ]; then
    printf '@@socom elf_base64='
    base64 -w 0 "$socom_probe/build1/probe.elf"
    printf '\\n'
  fi
  rm -rf -- "$socom_probe"
  trap - EXIT
fi
"""


def _script(install: str, *sections: str) -> str:
    return _prelude(install) + "".join(sections) + "socom_emit done 1\n"


def identity_script(install: str) -> str:
    return _script(install, _identity_section())


def verify_script(install: str, *, identity_only: bool = False) -> str:
    sections = [_identity_section()]
    if not identity_only:
        sections.append(_probe_section())
    return _script(install, *sections)


def bootstrap_script(install: str, *, force: bool) -> str:
    return _script(install, _install_section(force=force), _identity_section())


def probe_source_sha256() -> str:
    payload = PROBE_CMAKELISTS.encode("utf-8") + b"\0" + PROBE_SOURCE.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Execution


@dataclass
class LinuxRun:
    runner: dict[str, Any]
    markers: dict[str, list[str]] = field(default_factory=dict)
    exit_code: int | None = None
    output: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    blocked: str | None = None
    error: str | None = None

    def last(self, key: str) -> str | None:
        values = self.markers.get(key)
        return values[-1] if values else None


def decode_output(data: bytes) -> str:
    """Decode subprocess output; wsl.exe writes its own messages as UTF-16LE."""

    if not data:
        return ""
    if data.startswith(b"\xff\xfe") or data.count(0) * 4 >= len(data):
        text = data.decode("utf-16-le", errors="replace").lstrip("﻿")
    else:
        text = data.replace(b"\0", b"").decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n")


def parse_markers(text: str) -> tuple[dict[str, list[str]], list[str]]:
    markers: dict[str, list[str]] = {}
    other: list[str] = []
    for line in text.splitlines():
        if line.startswith(MARKER):
            key, separator, value = line[len(MARKER):].partition("=")
            if separator and key:
                markers.setdefault(key, []).append(value)
                continue
        other.append(line)
    return markers, other


def _runner(
    platform: str | None = None,
) -> tuple[list[str] | None, dict[str, str] | None, dict[str, Any], str | None]:
    """The argv and environment that run ``bash -s`` in the Linux environment."""

    platform = platform or sys.platform
    if platform == "win32":
        wsl = shutil.which("wsl.exe")
        if wsl is None:
            system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
            candidate = Path(system_root, "System32", "wsl.exe") if system_root else None
            wsl = str(candidate) if candidate is not None and candidate.is_file() else None
        distro = os.environ.get(DISTRO_VARIABLE, "").strip()
        runner = {"kind": "wsl", "distribution": distro or "default"}
        if wsl is None:
            return None, None, runner, (
                "wsl.exe was not found; install WSL 2 with a glibc x86_64 Linux distribution"
            )
        argv = [wsl, *(["-d", distro] if distro else []), "--cd", "~", "--", "bash", "-s"]
        environment = {
            name: value
            for name, value in os.environ.items()
            if name.upper() not in CLEARED_HOST_VARIABLES
        }
        return argv, environment, runner, None
    if platform.startswith("linux"):
        runner = {"kind": "bash"}
        bash = shutil.which("bash") or ("/bin/bash" if Path("/bin/bash").is_file() else None)
        if bash is None:
            return None, None, runner, "bash was not found in this Linux environment"
        environment = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
        for name in ("HOME", "USER", "LOGNAME", "TMPDIR"):
            if os.environ.get(name):
                environment[name] = os.environ[name]
        return [bash, "-s"], environment, runner, None
    return None, None, {"kind": "none"}, (
        f"unsupported host platform {platform}; the pinned ps2dev release needs "
        "a glibc x86_64 Linux environment (WSL 2 on Windows)"
    )


def run_linux_script(script: str, *, timeout: int) -> LinuxRun:
    argv, environment, runner, blocked = _runner()
    run = LinuxRun(runner=runner)
    if blocked is not None or argv is None:
        run.blocked = blocked or "no Linux environment is available"
        return run
    try:
        completed = subprocess.run(
            argv,
            input=script.encode("utf-8"),
            capture_output=True,
            env=environment,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        run.error = f"the Linux script did not finish within {timeout} s"
        return run
    except OSError as exc:
        run.blocked = f"cannot start the Linux environment: {exc}"
        return run
    run.exit_code = completed.returncode
    run.markers, other = parse_markers(decode_output(completed.stdout))
    run.output = [line for line in other if line.strip()][-60:]
    run.stderr = [
        line
        for line in decode_output(completed.stderr).splitlines()
        if line.strip() and not _HARMLESS_STDERR.match(line)
    ][-20:]
    if "protocol" not in run.markers:
        detail = "; ".join([*run.stderr[-4:], *run.output[-4:]]) or f"exit code {run.exit_code}"
        hint = ""
        if runner.get("kind") == "wsl" and runner.get("distribution") == "default":
            hint = (
                f" (the default WSL distribution may lack bash, as Docker Desktop's does; "
                f"set {DISTRO_VARIABLE} to a glibc Linux distribution listed by `wsl.exe -l -v`)"
            )
        run.blocked = f"the Linux environment did not run the script: {detail}{hint}"
    elif run.last("blocked"):
        run.blocked = run.last("blocked")
    elif "done" not in run.markers:
        reason = run.last("error") or f"exit code {run.exit_code}"
        run.error = f"the Linux script stopped early: {reason}"
    return run


# ---------------------------------------------------------------------------
# Evaluation


def evaluate_identity(markers: dict[str, list[str]]) -> dict[str, Any]:
    installed = (markers.get("installed") or [""])[-1] == "1"
    errors: list[str] = []
    warnings: list[str] = []
    files: list[dict[str, Any]] = []
    banners: dict[str, str | None] = {}
    top_level = sorted(markers.get("top_level", []))
    if not installed:
        errors.append("ps2dev is not installed; run `port toolchain bootstrap`")
    else:
        reported: dict[str, list[str]] = {}
        for value in markers.get("file", []):
            relative, _, rest = value.partition(" ")
            reported[relative] = rest.split()
        for relative, (size, digest) in EXPECTED_FILES.items():
            fields = reported.get(relative)
            if not fields or fields == ["missing"] or len(fields) != 2 or not fields[0].isdigit():
                errors.append(f"missing {relative}")
                files.append({"path": relative, "present": False})
                continue
            actual_size, actual_digest = int(fields[0]), fields[1]
            files.append({"path": relative, "present": True, "size": actual_size, "sha256": actual_digest})
            if actual_size != size:
                errors.append(f"{relative} size {actual_size} != pinned {size}")
            if actual_digest != digest:
                errors.append(f"{relative} SHA-256 differs from the pinned release")
        reported_banners: dict[str, str] = {}
        for value in markers.get("banner", []):
            tool, _, banner = value.partition(" ")
            reported_banners[tool] = banner.strip()
        for tool, expected in BANNERS.items():
            actual = reported_banners.get(tool) or None
            banners[tool] = actual
            if actual != expected:
                errors.append(f"{tool} --version is {actual!r}, expected {expected!r}")
        unexpected = sorted(set(top_level) - set(INSTALL_TOP_LEVEL))
        if unexpected:
            warnings.append(f"unexpected top-level entries in the install directory: {unexpected}")
        absent = sorted(set(INSTALL_TOP_LEVEL) - set(top_level))
        if absent:
            errors.append(f"install directory lacks release entries {absent}")
    return {
        "installed": installed,
        "identity_ok": installed and not errors,
        "banners": banners,
        "files": files,
        "top_level": top_level,
        "errors": errors,
        "warnings": warnings,
    }


def check_probe_elf(data: bytes) -> dict[str, Any]:
    """Check that a linked probe is an ELF32 little-endian R5900 executable at the EE base."""

    try:
        elf = Elf32File(Path("probe.elf"), data=data)
    except SocomError as exc:
        return {"ok": False, "errors": [f"probe ELF: {exc}"]}
    header = elf.header
    errors: list[str] = []
    if header.elf_type != ET_EXEC:
        errors.append(f"probe ELF type {header.elf_type} is not ET_EXEC")
    if header.machine != EM_MIPS:
        errors.append(f"probe ELF machine {header.machine} is not EM_MIPS ({EM_MIPS})")
    mach = header.flags & EF_MIPS_MACH
    if mach != EF_MIPS_MACH_5900:
        errors.append(f"probe ELF flags 0x{header.flags:08x} do not name the R5900 (mach 0x{mach:08x})")
    loads = [row for row in elf.program_headers if row.type == PT_LOAD]
    load_base = loads[0].virtual_address if loads else None
    if load_base is None:
        errors.append("probe ELF has no PT_LOAD segment")
    elif load_base != LOAD_BASE:
        errors.append(f"probe ELF loads at 0x{load_base:08x}, expected 0x{LOAD_BASE:08x}")
    static_init = sum(
        section.size for section in elf.sections if section.name in {".ctors", ".init_array"}
    )
    return {
        "ok": not errors,
        "class": "ELF32",
        "data": "little-endian",
        "machine": header.machine,
        "flags": f"0x{header.flags:08x}",
        "r5900": mach == EF_MIPS_MACH_5900,
        "abi2": bool(header.flags & EF_MIPS_ABI2),
        "entry": f"0x{header.entry:08x}",
        "load_base": f"0x{load_base:08x}" if load_base is not None else None,
        "load_segments": len(loads),
        "static_constructor_table_bytes": static_init,
        "errors": errors,
    }


def evaluate_probe(run: LinuxRun) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": True,
        "ready": False,
        "deterministic": None,
        "sha256": None,
        "source_sha256": probe_source_sha256(),
        "cmake": run.last("cmake_version"),
        "runs": [],
        "elf": None,
        "errors": [],
    }
    digests: list[str] = []
    for number in (1, 2):
        status = run.last(f"run{number}")
        row: dict[str, Any] = {"build": number, "status": status or "not-run"}
        digest = run.last(f"run{number}_sha256")
        size = run.last(f"run{number}_size")
        if status == "ok" and digest:
            row["sha256"] = digest
            row["size"] = int(size) if size and size.isdigit() else None
            digests.append(digest)
        else:
            result["errors"].append(f"probe build {number} failed")
        result["runs"].append(row)
    result["ready"] = len(digests) == 2
    if result["ready"]:
        result["deterministic"] = digests[0] == digests[1]
        if result["deterministic"]:
            result["sha256"] = digests[0]
        else:
            result["errors"].append(f"the two probe builds differ: {digests[0]} != {digests[1]}")
    encoded = run.last("elf_base64")
    if encoded:
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            result["errors"].append("the probe ELF transfer is not valid base64")
        else:
            if digests and hashlib.sha256(data).hexdigest() != digests[0]:
                result["errors"].append("the transferred probe ELF does not match its Linux SHA-256")
            else:
                result["elf"] = check_probe_elf(data)
                result["errors"].extend(result["elf"]["errors"])
    elif digests:
        result["errors"].append("the probe ELF was not transferred")
    return result


# ---------------------------------------------------------------------------
# Commands


def _base_report() -> dict[str, Any]:
    return {
        "ok": False,
        "status": "failed",
        "lane": "functional-port",
        "release": dict(RELEASE),
        "runner": None,
        "install_dir": None,
        "linux_arch": None,
        "installed": None,
        "identity_ok": False,
        "identity": None,
        "errors": [],
        "warnings": [],
        "blocked": None,
        "note": NOTE,
    }


def _absorb(report: dict[str, Any], run: LinuxRun) -> None:
    report["runner"] = run.runner
    report["install_dir"] = run.last("install_dir") or report["install_dir"]
    report["linux_arch"] = run.last("arch") or report["linux_arch"]


def _absorb_identity(report: dict[str, Any], identity: dict[str, Any]) -> None:
    report["installed"] = identity["installed"]
    report["identity_ok"] = identity["identity_ok"]
    report["identity"] = {key: identity[key] for key in ("banners", "files", "top_level")}
    report["errors"].extend(identity["errors"])
    report["warnings"].extend(identity["warnings"])


def _diagnostics(report: dict[str, Any], run: LinuxRun) -> None:
    if run.output:
        report["output"] = run.output
    if run.stderr:
        report["stderr"] = run.stderr


def _finish(report: dict[str, Any], *, ok: bool) -> dict[str, Any]:
    if report["blocked"]:
        report["ok"] = False
        report["status"] = "blocked"
    else:
        report["ok"] = ok and not report["errors"]
        report["status"] = "ok" if report["ok"] else "failed"
    return report


def verify_port_toolchain(*, identity_only: bool = False) -> dict[str, Any]:
    report = _base_report()
    report["compile_probe"] = {"attempted": False}
    try:
        install = install_expression(os.environ.get(INSTALL_VARIABLE))
    except SocomError as exc:
        report["blocked"] = str(exc)
        return _finish(report, ok=False)
    run = run_linux_script(
        verify_script(install, identity_only=identity_only),
        timeout=IDENTITY_TIMEOUT if identity_only else PROBE_TIMEOUT,
    )
    _absorb(report, run)
    if run.blocked:
        report["blocked"] = run.blocked
        _diagnostics(report, run)
        return _finish(report, ok=False)
    if run.error:
        report["errors"].append(run.error)
    identity = evaluate_identity(run.markers)
    _absorb_identity(report, identity)
    ok = identity["identity_ok"]
    if not identity_only and identity["installed"]:
        probe = evaluate_probe(run)
        report["compile_probe"] = probe
        report["errors"].extend(probe["errors"])
        ok = ok and probe["ready"] and probe["deterministic"] is True
    elif not identity_only:
        ok = False
    if not ok or report["errors"]:
        _diagnostics(report, run)
    return _finish(report, ok=ok)


def bootstrap_port_toolchain(*, force: bool = False) -> dict[str, Any]:
    report = _base_report()
    report["action"] = None
    report["archive"] = None
    try:
        install = install_expression(os.environ.get(INSTALL_VARIABLE))
    except SocomError as exc:
        report["blocked"] = str(exc)
        return _finish(report, ok=False)
    first = run_linux_script(identity_script(install), timeout=IDENTITY_TIMEOUT)
    _absorb(report, first)
    if first.blocked or first.error:
        report["blocked"] = first.blocked
        if first.error:
            report["errors"].append(first.error)
        _diagnostics(report, first)
        return _finish(report, ok=False)
    before = evaluate_identity(first.markers)
    if before["installed"] and not force:
        _absorb_identity(report, before)
        if before["identity_ok"]:
            report["action"] = "already-installed"
            return _finish(report, ok=True)
        report["action"] = "none"
        report["errors"].append(
            "the install directory exists but fails identity checks; review it, then rerun with --force"
        )
        return _finish(report, ok=False)
    run = run_linux_script(bootstrap_script(install, force=force), timeout=BOOTSTRAP_TIMEOUT)
    _absorb(report, run)
    report["archive"] = run.last("archive")
    if run.blocked:
        report["blocked"] = run.blocked
        _diagnostics(report, run)
        return _finish(report, ok=False)
    if run.error or run.last("installed_now") != "1":
        report["action"] = "none"
        report["errors"].append(run.error or "the install step did not complete")
        actual = run.last("archive_actual")
        if actual:
            report["archive_actual"] = actual
        _diagnostics(report, run)
        return _finish(report, ok=False)
    report["action"] = "reinstalled" if before["installed"] else "installed"
    after = evaluate_identity(run.markers)
    _absorb_identity(report, after)
    if not after["identity_ok"]:
        _diagnostics(report, run)
    return _finish(report, ok=after["identity_ok"])
