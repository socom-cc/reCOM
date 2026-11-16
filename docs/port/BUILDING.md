# Building the functional port

The functional port is the playable, non-matching build of the game: `src/` compiled with the
open-source ps2dev toolchain (GCC 15.2 and ps2sdk, release v2.0.0, pinned in
[PORT_TOOLCHAIN.md](../reconstruction/PORT_TOOLCHAIN.md)). Everything needed to compile it is
free. Two ways to build give the same result; pick one.

## With Docker (any system)

Needs Docker only. The image holds the pinned toolchain and nothing of the game; the checkout is
mounted when it runs.

```
docker build -t socom-port port/docker
docker run --rm -v "<checkout>:/src" -v socom-port-build:/build socom-port
```

`<checkout>` is the absolute path of your clone: from the clone's folder, `${PWD}` in PowerShell
or `$PWD` in a Unix shell. The first command downloads the toolchain once
(about 270 MB) and checks its SHA-256. The second compiles and links, and writes

```
build/port/docker/socom_port.elf
```

inside the checkout (`build/` is ignored by git). The named volume `socom-port-build` keeps the
objects and a compiler cache, so later builds only recompile what changed.

- Build options go after the image name and reach CMake, for example
  `... socom-port --fresh -DSOCOM_PORT_HEAP_SHRINK_TEXLIST=ON`. `--fresh` configures again;
  without it a new option is ignored by an existing build directory.
- To start over: `docker volume rm socom-port-build`.

## Without Docker (Linux, or WSL 2 on Windows)

Needs Python 3, `curl`, `cmake` and `make` in the Linux environment.

```
python tools/socom.py port toolchain bootstrap     # installs the pinned release once
bash port/tools/link.sh                            # run on the Linux side
```

`bootstrap` puts the toolchain under `$HOME/.local/share/socom/ps2dev-v2.0.0` (override with
`SOCOM_PS2DEV`); `link.sh` builds in `$HOME/.cache/socom/port-build` (override with
`SOCOM_PORT_BUILD`) and prints where the ELF is. On Windows the first command can be run from
PowerShell: it works inside the default WSL distribution (`SOCOM_WSL_DISTRO` selects another).

## Running it

The ELF runs in the PCSX2 emulator from the game's own disc:

```
pcsx2-qt -elf <path to socom_port.elf> -- <path to your disc image>
```

You supply these yourself; none of them is in the repository and none may be committed to it:

- a disc image of the game this project reconstructs (SCUS-972.05), from a disc you own;
- a PlayStation 2 BIOS for the emulator, from a console you own;
- the emulator.

## What compiling does not need

- The reference executable `support/socom.elf`. The comparison tools under `port/tools/dev/` and
  all reconstruction work read it, so contributors to those supply their own copy (its SHA-256
  is in `AGENTS.md`); a plain build does not.
- The Metrowerks compiler. It belongs to the byte-matching stages, which are blocked on its
  licence; the port never uses it.

## Checking a change

A change to `src/` should at least build. Beyond that, `port/tools/dev/gate.ps1` runs the full
behaviour check in the emulator (default boot, options screens, a scripted winning playthrough,
mission round trips); it needs the disc image and is described in
[WORKER_BRIEF.md](WORKER_BRIEF.md) and `port/tools/dev/README.md`.
