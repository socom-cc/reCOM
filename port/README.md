# Functional port lane

Builds a working, non-matching PS2 ELF from `src/` with the pinned ps2dev toolchain
(see `docs/reconstruction/PORT_TOOLCHAIN.md` and AGENTS.md "Functional port lane").
Nothing here is evidence for the matching stages.

- `CMakeLists.txt` - the build (`socom_game` library from every src/ unit except
  `*_holding.cpp`; `socom_port.elf`).
- `include/socom_port_prefix.h` - forced-include prefix supplying what Metrowerks builds got from
  their prefix file.
- `compat/` - SDK compatibility layer and offline stubs (online, voice, sound); `compat/include/`
  holds re-created SDK header names (`eekernel.h`, `libgraph.h`, ...) with declarations backed by
  call-site evidence.
- `tools/sweep.sh` - per-file compile sweep (`units` or standalone `headers`) for diagnosis.

Run builds on the Linux side (WSL): Windows paths, emulator paths, BIOS and disc data stay
user-local and are never committed.
