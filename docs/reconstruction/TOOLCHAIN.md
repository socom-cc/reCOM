# Metrowerks toolchain

The pinned toolchain ID is `mwcps2-2.4-001213`. It is fetched from the
decomp.me compiler archive at upstream commit
`804c712453592c7ca15732c432fee2efa13d1825`.

The compiler files are proprietary, so `compiler/` is not tracked. Acquire and
verify them per machine with:

```powershell
python tools/socom.py toolchain bootstrap
```

The expected file sizes and SHA-256s are pinned in `tools/_socom/toolchain.py`.
Until the toolchain is installed, `doctor` reports the four files as missing
and the toolchain tests skip.

`compiler/PROVENANCE.json`, written by the bootstrap, records:

- the immutable archive URL and SHA-256;
- every extracted filename, size, and SHA-256;
- compiler/linker banners, assembler build, and internal compiler signature;
- target/compiler relationship to the ELF comment;
- the absence of a license file in the upstream payload.

Verify identity without compiling:

```powershell
python tools/socom.py toolchain verify --identity-only
```

Verify full readiness:

```powershell
python tools/socom.py toolchain verify
```

Full verification compiles the same probe twice and requires identical objects.
On this Windows setup the original driver checks FLEXlm feature
`Win32_Plugins_MIPS_PS2`. Until a valid license is supplied, the command reports
`blocked_by_license: true`; later matching stages remain blocked.

Once compilation is available, ABI probes must record scalar widths and
signedness, enum and bitfield behavior, alignment/packing, receiver/parameter
and return placement, structure returns, vtable/RTTI shape, floating-point
register use, and 64/128-bit values. These results belong in tracker evidence
and supersede host assumptions.

The workspace does not claim a license for the payload, distribute a
`license.dat`, or bypass licensing. Users control lawful access and
redistribution of the compiler and any required SDK/provider inputs.

The functional port's separate open-source GCC/ps2sdk toolchain is described in [PORT_TOOLCHAIN.md](PORT_TOOLCHAIN.md).
