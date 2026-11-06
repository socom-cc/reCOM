from __future__ import annotations

import base64
import hashlib
import re
import struct
import subprocess

import pytest

from tools._socom import port_toolchain as port
from tools._socom.cli import COMMAND_SPECS
from tools._socom.util import SocomError

WINDOWS_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
# Built in pieces so this file carries no literal drive path.
STALE_PS2DEV = "C" + ":/Libraries/PS2DEV"
DEFAULT_INSTALL = 'PS2DEV="$HOME"/.local/share/socom/ps2dev-v2.0.0'


def _elf(
    *,
    machine: int = 8,
    flags: int = 0x20920025,
    vaddr: int = 0x00100000,
    encoding: int = 1,
    entry: int = 0x001004A8,
) -> bytes:
    """A minimal ELF32 executable: one PT_LOAD and a section-name table."""

    names = b"\0.shstrtab\0"
    program_offset = 52
    names_offset = program_offset + 32
    section_offset = (names_offset + len(names) + 3) & ~3
    ident = b"\x7fELF" + bytes([1, encoding, 1, 0]) + bytes(8)
    header = ident + struct.pack(
        "<HHIIIIIHHHHHH", 2, machine, 1, entry, program_offset, section_offset, flags, 52, 32, 1, 40, 2, 1
    )
    program = struct.pack("<IIIIIIII", 1, 0, vaddr, vaddr, 0, 0, 7, 0x80)
    body = header + program + names
    body += bytes(section_offset - len(body))
    sections = bytes(40) + struct.pack("<IIIIIIIIII", 1, 3, 0, 0, names_offset, len(names), 0, 0, 1, 0)
    return body + sections


def _identity(*, installed: bool = True, banner: str | None = None, missing: str | None = None) -> list[str]:
    lines = ["protocol=1", "arch=x86_64", "install_dir=$HOME/.local/share/socom/ps2dev-v2.0.0"]
    if not installed:
        return [*lines, "installed=0"]
    lines.append("installed=1")
    lines += [f"top_level={name}" for name in port.INSTALL_TOP_LEVEL]
    for relative, (size, digest) in port.EXPECTED_FILES.items():
        lines.append(f"file={relative} missing" if relative == missing else f"file={relative} {size} {digest}")
    for tool, expected in port.BANNERS.items():
        lines.append(f"banner={tool} {banner or expected}")
    return lines


def _probe(data: bytes, *, second: str | None = None) -> list[str]:
    digest = hashlib.sha256(data).hexdigest()
    return [
        "cmake_version=cmake version 3.28.3",
        "run1=ok",
        f"run1_sha256={digest}",
        f"run1_size={len(data)}",
        "run2=ok",
        f"run2_sha256={second or digest}",
        f"run2_size={len(data)}",
        "elf_base64=" + base64.b64encode(data).decode("ascii"),
    ]


def _stdout(lines: list[str], *, done: bool = True) -> bytes:
    text = "".join(f"@@socom {line}\n" for line in lines)
    if done:
        text += "@@socom done=1\n"
    return text.encode("utf-8")


class FakeLinux:
    def __init__(self, responses: list[tuple[bytes, bytes, int]]) -> None:
        self.responses = list(responses)
        self.scripts: list[str] = []

    def __call__(self, argv, *, input, capture_output, env, timeout, check):  # noqa: A002 - subprocess.run keyword
        self.scripts.append(input.decode("utf-8"))
        stdout, stderr, code = self.responses.pop(0)
        return subprocess.CompletedProcess(argv, code, stdout, stderr)


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.delenv(port.INSTALL_VARIABLE, raising=False)

    def install(responses, *, runner=None):
        fake = FakeLinux(responses)
        info = runner or {"kind": "bash"}
        monkeypatch.setattr(port, "_runner", lambda platform=None: (["bash", "-s"], {}, info, None))
        monkeypatch.setattr(port.subprocess, "run", fake)
        return fake

    return install


def test_scripts_pin_the_release_and_carry_no_windows_paths(monkeypatch) -> None:
    monkeypatch.setenv("PS2DEV", STALE_PS2DEV)
    monkeypatch.setenv("PS2SDK", "$PS2DEV/ps2sdk")
    install = port.install_expression(None)
    scripts = {
        "identity": port.identity_script(install),
        "verify": port.verify_script(install),
        "verify-identity": port.verify_script(install, identity_only=True),
        "bootstrap": port.bootstrap_script(install, force=False),
        "bootstrap-force": port.bootstrap_script(install, force=True),
    }
    for name, script in scripts.items():
        assert not WINDOWS_PATH.search(script), name
        assert "\r" not in script and "\\\\" not in script, name
        assert STALE_PS2DEV not in script and "/usr/local/ps2dev" not in script, name
        assert "unset PS2DEV PS2SDK GSKIT" in script, name
        assert DEFAULT_INSTALL in script, name
        assert 'export PS2SDK="$PS2DEV/ps2sdk"' in script, name
        assert "$PS2DEV/ee/bin:$PS2DEV/iop/bin:$PS2DEV/dvp/bin:$PS2SDK/bin:/usr/bin:/bin" in script, name
        assert script.rstrip().endswith("socom_emit done 1"), name
    bootstrap = scripts["bootstrap-force"]
    assert port.RELEASE["url"] in bootstrap and port.RELEASE["sha256"] in bootstrap
    assert f"SOCOM_SIZE={port.RELEASE['size']}" in bootstrap and "SOCOM_FORCE=1" in bootstrap
    assert "SOCOM_FORCE=0" in scripts["bootstrap"]
    assert "curl --fail --location" in bootstrap and "--retry 3" in bootstrap
    # The archive is verified before anything is extracted, and extraction is staged.
    assert bootstrap.index('socom_archive_ok "$SOCOM_ARCHIVE.part"') < bootstrap.index("tar -xzf")
    assert bootstrap.index("mktemp -d") < bootstrap.index("tar -xzf")
    assert port.RELEASE["url"] not in scripts["verify"]
    verify = scripts["verify"]
    assert port.PROBE_SOURCE in verify and port.PROBE_CMAKELISTS in verify
    assert "-ldebug" in verify and "-ffile-prefix-map" in verify
    assert '-DCMAKE_TOOLCHAIN_FILE="$PS2DEV/share/ps2dev.cmake"' in verify
    assert "for socom_run in 1 2" in verify and "mktemp -d" in verify
    assert "SOCOM_PROBE_EOF" not in scripts["verify-identity"]


def test_install_expression_accepts_only_linux_paths() -> None:
    assert port.install_expression("") == '"$HOME"/.local/share/socom/ps2dev-v2.0.0'
    assert port.install_expression("~/tools/ps2dev") == '"$HOME"/tools/ps2dev'
    assert port.install_expression("$HOME/tools/ps2dev/") == '"$HOME"/tools/ps2dev'
    assert port.install_expression("/opt/socom/ps2dev/") == "/opt/socom/ps2dev"
    assert port.install_expression("/opt/socom/ps 2") == "'/opt/socom/ps 2'"
    for bad in ("D" + ":/ps2dev", "opt\\ps2dev", "ps2dev", "/opt", "/opt/../ps2dev", "~/", "/opt/x\ny"):
        with pytest.raises(SocomError):
            port.install_expression(bad)


def test_an_invalid_install_override_blocks_without_running(linux, monkeypatch) -> None:
    fake = linux([])
    monkeypatch.setenv(port.INSTALL_VARIABLE, STALE_PS2DEV)
    report = port.verify_port_toolchain()
    assert report["status"] == "blocked" and report["ok"] is False
    assert port.INSTALL_VARIABLE in report["blocked"]
    assert fake.scripts == []


def test_wsl_runner_drops_host_toolchain_variables(monkeypatch) -> None:
    monkeypatch.setenv("PS2DEV", STALE_PS2DEV)
    monkeypatch.setenv("PS2SDK", "$PS2DEV/ps2sdk")
    monkeypatch.setenv("WSLENV", "PS2DEV/p")
    monkeypatch.setenv(port.DISTRO_VARIABLE, "ExampleLinux")
    monkeypatch.setattr(port.shutil, "which", lambda name: "wsl.exe" if name == "wsl.exe" else None)
    argv, environment, runner, blocked = port._runner("win32")
    assert blocked is None
    assert argv == ["wsl.exe", "-d", "ExampleLinux", "--cd", "~", "--", "bash", "-s"]
    assert runner == {"kind": "wsl", "distribution": "ExampleLinux"}
    assert not {"PS2DEV", "PS2SDK", "WSLENV"} & {name.upper() for name in environment}
    monkeypatch.delenv(port.DISTRO_VARIABLE)
    argv, _, runner, _ = port._runner("win32")
    assert argv == ["wsl.exe", "--cd", "~", "--", "bash", "-s"] and runner["distribution"] == "default"
    monkeypatch.setattr(port.shutil, "which", lambda name: "/usr/bin/bash" if name == "bash" else None)
    argv, environment, runner, _ = port._runner("linux")
    assert argv == ["/usr/bin/bash", "-s"] and runner == {"kind": "bash"}
    assert "PS2DEV" not in environment and environment["PATH"] == "/usr/bin:/bin"
    _, _, _, blocked = port._runner("darwin")
    assert blocked and "unsupported host platform" in blocked


def test_bootstrap_is_a_no_op_when_the_pinned_install_is_present(linux) -> None:
    fake = linux([(_stdout(_identity()), b"", 0)])
    report = port.bootstrap_port_toolchain()
    assert report["ok"] is True and report["status"] == "ok"
    assert report["action"] == "already-installed" and report["identity_ok"] is True
    assert report["install_dir"] == "$HOME/.local/share/socom/ps2dev-v2.0.0"
    assert len(fake.scripts) == 1 and port.RELEASE["url"] not in fake.scripts[0]


def test_bootstrap_refuses_a_mismatched_install_without_force(linux) -> None:
    fake = linux([(_stdout(_identity(missing="ps2sdk/ee/lib/libkernel.a")), b"", 0)])
    report = port.bootstrap_port_toolchain()
    assert report["ok"] is False and report["action"] == "none"
    assert "missing ps2sdk/ee/lib/libkernel.a" in report["errors"]
    assert any("--force" in error for error in report["errors"])
    assert len(fake.scripts) == 1


def test_bootstrap_force_reinstalls_from_a_verified_cache(linux) -> None:
    second = ["protocol=1", "arch=x86_64", "archive=cached", "installed_now=1", *_identity()[2:]]
    fake = linux([(_stdout(_identity()), b"", 0), (_stdout(second), b"", 0)])
    report = port.bootstrap_port_toolchain(force=True)
    assert report["ok"] is True and report["action"] == "reinstalled" and report["archive"] == "cached"
    assert len(fake.scripts) == 2 and "SOCOM_FORCE=1" in fake.scripts[1]


def test_bootstrap_installs_when_absent(linux) -> None:
    second = ["protocol=1", "arch=x86_64", "archive=downloaded", "installed_now=1", *_identity()[2:]]
    linux([(_stdout(_identity(installed=False)), b"", 0), (_stdout(second), b"", 0)])
    report = port.bootstrap_port_toolchain()
    assert report["ok"] is True and report["action"] == "installed" and report["archive"] == "downloaded"


def test_bootstrap_reports_an_archive_mismatch(linux) -> None:
    second = [
        "protocol=1",
        "arch=x86_64",
        "archive_actual=123 " + "ab" * 32,
        "error=the downloaded archive does not match the pinned size and SHA-256",
    ]
    linux([(_stdout(_identity(installed=False)), b"", 0), (_stdout(second, done=False), b"", 1)])
    report = port.bootstrap_port_toolchain()
    assert report["ok"] is False and report["status"] == "failed" and report["action"] == "none"
    assert any("does not match the pinned size and SHA-256" in error for error in report["errors"])
    assert report["archive_actual"].startswith("123 ")


def test_verify_parses_identity_and_a_deterministic_probe(linux) -> None:
    data = _elf()
    linux([(_stdout([*_identity(), *_probe(data)]), b"", 0)])
    report = port.verify_port_toolchain()
    assert report["ok"] is True, report["errors"]
    assert report["identity"]["banners"]["ee/bin/mips64r5900el-ps2-elf-gcc"] == (
        "mips64r5900el-ps2-elf-gcc (GCC) 15.2.0"
    )
    probe = report["compile_probe"]
    assert probe["ready"] is True and probe["deterministic"] is True
    assert probe["sha256"] == hashlib.sha256(data).hexdigest()
    assert probe["source_sha256"] == port.probe_source_sha256()
    assert probe["elf"]["flags"] == "0x20920025" and probe["elf"]["entry"] == "0x001004a8"
    assert probe["elf"]["r5900"] is True and probe["elf"]["load_base"] == "0x00100000"


def test_verify_fails_a_non_deterministic_probe(linux) -> None:
    linux([(_stdout([*_identity(), *_probe(_elf(), second="0" * 64)]), b"", 0)])
    report = port.verify_port_toolchain()
    assert report["ok"] is False and report["status"] == "failed"
    assert report["compile_probe"]["deterministic"] is False
    assert report["compile_probe"]["sha256"] is None
    assert any("differ" in error for error in report["errors"])


def test_verify_fails_a_probe_whose_transfer_does_not_match(linux) -> None:
    lines = _probe(_elf())
    lines[-1] = "elf_base64=" + base64.b64encode(_elf(machine=3)).decode("ascii")
    linux([(_stdout([*_identity(), *lines]), b"", 0)])
    report = port.verify_port_toolchain()
    assert report["ok"] is False
    assert any("does not match its Linux SHA-256" in error for error in report["errors"])


def test_verify_reports_a_failed_build_with_its_log(linux) -> None:
    stdout = _stdout([*_identity(), "run1=failed", "run2=failed"]) + b"build1: undefined reference to `sinf'\n"
    linux([(stdout, b"", 0)])
    report = port.verify_port_toolchain()
    assert report["ok"] is False and report["compile_probe"]["ready"] is False
    assert "probe build 1 failed" in report["errors"]
    assert any("undefined reference" in line for line in report["output"])


def test_verify_identity_only_skips_the_probe(linux) -> None:
    fake = linux([(_stdout(_identity()), b"", 0)])
    report = port.verify_port_toolchain(identity_only=True)
    assert report["ok"] is True and report["compile_probe"] == {"attempted": False}
    assert "SOCOM_PROBE_EOF" not in fake.scripts[0]


def test_verify_rejects_a_wrong_compiler_banner(linux) -> None:
    linux([(_stdout(_identity(banner="mips64r5900el-ps2-elf-gcc (GCC) 14.2.0")), b"", 0)])
    report = port.verify_port_toolchain(identity_only=True)
    assert report["ok"] is False and report["identity_ok"] is False
    assert any("14.2.0" in error for error in report["errors"])


def test_verify_requires_an_install(linux) -> None:
    linux([(_stdout(_identity(installed=False)), b"", 0)])
    report = port.verify_port_toolchain()
    assert report["ok"] is False and report["installed"] is False
    assert any("port toolchain bootstrap" in error for error in report["errors"])


def test_a_default_distribution_without_bash_is_blocked(linux) -> None:
    stderr = b"wsl: Failed to translate 'X'\n/bin/sh: bash: not found\n"
    linux([(b"", stderr, 127)], runner={"kind": "wsl", "distribution": "default"})
    report = port.verify_port_toolchain()
    assert report["status"] == "blocked" and report["ok"] is False
    assert "bash: not found" in report["blocked"] and port.DISTRO_VARIABLE in report["blocked"]
    assert report["stderr"] == ["/bin/sh: bash: not found"]


def test_a_missing_build_tool_is_blocked(linux) -> None:
    linux([(_stdout([*_identity(), "blocked=cmake is not installed in the Linux environment"], done=False), b"", 0)])
    report = port.verify_port_toolchain()
    assert report["status"] == "blocked" and "cmake" in report["blocked"]


def test_decode_output_handles_wsl_utf16() -> None:
    message = "There is no distribution with the supplied name.\r\n"
    assert port.decode_output(message.encode("utf-16-le")) == "There is no distribution with the supplied name.\n"
    assert port.decode_output(b"@@socom done=1\n") == "@@socom done=1\n"
    markers, other = port.parse_markers("@@socom a=1=2\nnoise\n@@socom a=3\n")
    assert markers == {"a": ["1=2", "3"]} and other == ["noise"]


def test_probe_elf_header_checks() -> None:
    good = port.check_probe_elf(_elf())
    assert good["ok"] is True and good["r5900"] is True and good["abi2"] is True
    assert good["machine"] == 8 and good["load_segments"] == 1
    wrong_machine = port.check_probe_elf(_elf(machine=3))
    assert wrong_machine["ok"] is False and any("EM_MIPS" in error for error in wrong_machine["errors"])
    not_r5900 = port.check_probe_elf(_elf(flags=0x20000025))
    assert not_r5900["ok"] is False and not_r5900["r5900"] is False
    assert any("R5900" in error for error in not_r5900["errors"])
    wrong_base = port.check_probe_elf(_elf(vaddr=0x00200000))
    assert wrong_base["ok"] is False and any("0x00100000" in error for error in wrong_base["errors"])
    big_endian = port.check_probe_elf(_elf(encoding=2))
    assert big_endian["ok"] is False and any("little-endian" in error for error in big_endian["errors"])
    assert port.check_probe_elf(b"not an elf")["ok"] is False


def test_port_commands_are_registered() -> None:
    specs = {row.path: row for row in COMMAND_SPECS}
    assert specs["port toolchain bootstrap"].mutates is True
    assert specs["port toolchain verify"].mutates is False
    for path in ("port toolchain bootstrap", "port toolchain verify"):
        assert specs[path].ghidra_requirement == "none" and specs[path].mutates_ghidra is False
