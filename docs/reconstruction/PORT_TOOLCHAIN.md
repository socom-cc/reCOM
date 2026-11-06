# Functional-port toolchain (ps2dev)

The exact Metrowerks compiler ([TOOLCHAIN.md](TOOLCHAIN.md)) is blocked on its
FLEXlm license. In the meantime the functional port builds the game with the
open-source ps2dev toolchain (GCC and ps2sdk). This is a separate lane. A port
build never substitutes for exact-compiler evidence, ABI probes, or any
order, call-contract, byte, or linked-ELF matching stage, and its objects are
never matching candidates.

## Pinned release

| Field | Value |
| --- | --- |
| Repository | `https://github.com/ps2dev/ps2dev` |
| Tag | `v2.0.0` (tag object `69d11750230d8ece4139104731394af7ec2169a2`, published 2026-05-17) |
| Asset | `ps2dev-ubuntu-latest.tar.gz`, 266,096,645 bytes |
| SHA-256 | `c8e5dedccf62084d476894e88cd0451b57f1ed288e741eb3c1263010aaffc028` |
| EE compiler | `mips64r5900el-ps2-elf-gcc (GCC) 15.2.0` (and `g++`) |
| IOP compiler | `mipsel-none-elf-gcc (GCC) 15.2.0` |

The asset is built in an Ubuntu 20.04 container. It runs on any newer glibc
x86_64 Linux and needs about 687 MB once installed. Its top level is `ps2dev/`
(`bin`, `dvp`, `ee`, `gsKit`, `iop`, `ps2sdk`, `share`, and a stray
`test.tmp`). `port toolchain verify` also checks the sizes and SHA-256s of
twelve key installed files, pinned from the archive's own members: the CMake
toolchain file, the compiler drivers, the linkfile, `libkernel.a`,
`libdebug.a`, `libstdc++.a`, `crt0.o`, and the headers the probe uses.

## Commands

```powershell
python tools/socom.py port toolchain bootstrap [--force]
python tools/socom.py port toolchain verify [--identity-only]
```

`bootstrap` does nothing when the pinned install is already present and
passes the identity checks. Otherwise it downloads the asset with `curl`
(failing on HTTP errors, with retries) into
`$HOME/.cache/socom/downloads/ps2dev-v2.0.0/ps2dev.tar.gz`. It checks the
size and SHA-256 before it extracts anything, extracts into a staging
directory beside the install, and then moves the tree into place. A cached
archive that verifies is reused. `--force` reinstalls, but it replaces an
existing directory only if that directory looks like a ps2dev tree.

`verify` checks identity first. Unless `--identity-only` is given, it then
builds a C++ probe twice with CMake (`Unix Makefiles`, toolchain file
`$PS2DEV/share/ps2dev.cmake`), in two separate build directories under
`mktemp -d`, and deletes them afterwards. The probe has a virtual hierarchy, a
static constructor, `new`/`delete`, `sinf`, `scr_printf`, and `SleepThread`.
The two ELFs must be byte-identical. The first must be an ELF32
little-endian `EM_MIPS` executable whose flags name the R5900
(`(e_flags & 0x00ff0000) == 0x00920000`) and whose first `PT_LOAD` sits at
`0x00100000`. The report includes the probe SHA-256, the entry point, and the
flags.

Both commands print a JSON report and exit 0 only when `ok` is true. A missing
Linux environment, `bash`, `curl`, `cmake`, or `make` gives
`status: blocked` with the reason.

## Reproducible port builds

The ps2sdk EE libraries contain LTO bytecode. At link time, LTO writes the
link directory into DWARF `comp_dir`, so the same probe linked in two
different directories differs in `.debug_str`. The probe therefore passes
`-ffile-prefix-map=<dir>=<fixed name>` for its source and build trees at both
compile and link time. Port builds that need to reproduce across checkouts
should do the same. CMake treats `debug` as a keyword, so the probe links that
ps2sdk library as `-ldebug`.

## Environment

| Variable | Meaning |
| --- | --- |
| `SOCOM_PS2DEV` | Install directory, as a Linux path inside the Linux environment (absolute, `~/...`, or `$HOME/...`). Default `$HOME/.local/share/socom/ps2dev-v2.0.0`. |
| `SOCOM_WSL_DISTRO` | WSL distribution to use on Windows. Default: the default distribution. |

Each script sets its own `PS2DEV`, `PS2SDK=$PS2DEV/ps2sdk`, and
`PATH=$PS2DEV/bin:$PS2DEV/ee/bin:$PS2DEV/iop/bin:$PS2DEV/dvp/bin:$PS2SDK/bin:/usr/bin:/bin`.
It clears inherited compiler variables. A host-wide `PS2DEV` or `PS2SDK`, or
another ps2dev installed elsewhere in the Linux environment, is never read,
used, or modified.

## Windows and WSL

On Windows the commands run `wsl.exe [-d <distro>] --cd ~ -- bash -s` and pass
the script on stdin, so no Windows path is translated into Linux. The
`wsl: Failed to translate ...` warnings that WSL prints for the Windows `PATH`
are harmless and are filtered out. wsl.exe's own error messages arrive as
UTF-16LE and are decoded. Docker Desktop's internal distribution has no
`bash`; if it is the default, set `SOCOM_WSL_DISTRO` to a glibc distribution
listed by `wsl.exe -l -v`. On Linux the commands run `bash -s` directly.
