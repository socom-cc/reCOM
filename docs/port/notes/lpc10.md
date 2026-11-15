# LPC-10 voice codec (push-to-talk client library)

Functional port lane. Written 2026-11-15 by socom-port-lpc10 from the reference ELF. The codec is
**provider** code, not game source: it lives in `port/compat/lpc10/` (one file per original compile
unit, plus `lpc10.h`), never in `src/`, and nothing here is evidence for the matching stages.

## What the ELF holds

- 42 functions in 34 DWARF compile units of the push-to-talk client library (`dev\libpttclient\*.c`
  on the original build machine's drive; `libpttclient.cpp` itself is the PTT layer). Two blocks:
  `0x3eb3a0..0x3efed4` (`analys_` .. `ivfilt_`, with the f2c helpers `pow_ii`, `r_sign`, `i_nint`)
  and `0x3f1380..0x3f6918` (`lpc10_decode` .. `vparms_`); the PTT functions sit between and after
  them. Static tables `0x43c3f0..0x43d318`, `c__N` / `c_b2` argument constants `0x47557c..0x4755cb`,
  guarded scalar statics `0x476c54..0x476cb0`, common `/contrl/` at `0x5754d0` (12 bytes, .bss).
- The units are the f2c translation of the FS-1015 reference coder with the Fortran SAVE variables
  moved into two state records: DWARF `lpc10_encoder_state` (9,540 bytes) and `lpc10_decoder_state`
  (3,072 bytes), declared member for member in `lpc10.h` (sizes asserted at compile time).
- The library was not built with the game's Metrowerks compiler: the code calls Sony ee-gcc's
  soft-float helpers (`fptosi`, `fptodp`, `dpadd`, `dpsub`, `dptoli`), saves registers with `sq`,
  passes arguments 9+ as 8-byte stack slots (EABI), has a 64-bit `long` (`pow_ii`'s `unsigned long`)
  and cfront-style mangled names (`lpc10_encode__FPfPiP19lpc10_encoder_state`): ee-gcc 2.9x
  compiling the `.c` files as C++. The code is close to unoptimised (parameters and most locals live
  on the stack, every branch delay slot is a `nop`).
- Callers outside the library: `PTT_Init` (`create_lpc10_encoder_state`,
  `create_lpc10_decoder_state`) and `PTT_Heartbeat` (`lpc10_encode`, `lpc10_decode`,
  `init_lpc10_encoder_state`, `init_lpc10_decoder_state`). Nothing in the game calls the codec.
  The port's PTT functions stay offline stand-ins (`port/compat/ptt_offline.cpp`), so in a normal
  build the codec is linked but never called. Linkage: plain C names (the mangled names are needed
  by nobody); all 42 prototypes were checked against the mangled parameter lists.

## Function table

Port files are under `port/compat/lpc10/`. "Re-read": each body was written against its listing
line by line, then the finished bodies were cross-checked mechanically against the ELF: the port
units compiled at `-O0` and disassembled, per function the ordered callee list (identical for all 42)
and the counts of FP add / sub / mul / div / neg / convert / compare and integer divide (identical,
or different only for the reason given).

| address | bytes | symbol (ELF) | CU | port file | callers | callees | written | re-read (2026-11-15) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0x3eb3a0 | 2768 | `analys___FPfPiPiPfPfP19lpc10_encoder_state` | analys.c | `analys.c` | lpc10_encode | preemp_, onset_, placev_, lpfilt_, ivfilt_, tbdm_, voicin_, dyptrk_, placea_, dcbias_, energy_, mload_, invert_, rcchk_ | 2026-11-15 | OK; calls equal, FP op counts differ only by x + -1 as x - 1 |
| 0x3ebe70 | 2524 | `bsynz___FPfPiPiPfPfPfPfP19lpc10_decoder_state` | bsynz.c | `bsynz.c` | synths_ | random_, sqrtf | 2026-11-15 | OK; calls equal, FP op counts differ only by register moves, index multiply |
| 0x3ec850 | 888 | `chanwr_0___FiPiPiPiPiPiP19lpc10_encoder_state` | chanwr.c | `chanwr.c` | chanrd_, chanwr_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3ecbd0 | 88 | `chanwr___FPiPiPiPiPiP19lpc10_encoder_state` | chanwr.c | `chanwr.c` | lpc10_encode | chanwr_0_ | 2026-11-15 | OK; calls and FP ops equal |
| 0x3ecc30 | 84 | `chanrd___FPiPiPiPiPi` | chanwr.c | `chanwr.c` | lpc10_decode | chanwr_0_ | 2026-11-15 | OK; calls and FP ops equal |
| 0x3ecc90 | 260 | `dcbias___FPiPfPf` | dcbias.c | `dcbias.c` | analys_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3ecda0 | 4060 | `decode___FPiPiPiPiPiPfPfP19lpc10_decoder_state` | decode.c | `decode.c` | lpc10_decode | ham84_, fptosi, median_, pow_ii | 2026-11-15 | OK; calls equal, FP op counts differ only by int-to-float conversions placed per branch |
| 0x3edd80 | 400 | `deemp___FPfPiP19lpc10_decoder_state` | deemp.c | `deemp.c` | synths_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3edf10 | 612 | `difmag___FPfPiPiPiPiPfPiPi` | difmag.c | `difmag.c` | tbdm_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3ee180 | 1544 | `dyptrk___FPfPiPiPiPiPiP19lpc10_encoder_state` | dyptrk.c | `dyptrk.c` | analys_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3ee790 | 1836 | `encode___FPiPiPfPfPiPiPi` | encode.c | `encode.c` | lpc10_encode | fptosi, pow_ii | 2026-11-15 | OK; calls and FP ops equal |
| 0x3eeec0 | 236 | `energy___FPiPfPf` | energy.c | `energy.c` | analys_ | sqrtf | 2026-11-15 | OK; calls equal, FP op counts differ only by register moves |
| 0x3eefb0 | 252 | `pow_ii__FPiPi` | f2clib.c | `f2clib.c` | decode_, encode_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3ef0b0 | 164 | `r_sign__FPfPf` | f2clib.c | `f2clib.c` | onset_, vparms_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3ef160 | 204 | `i_nint__FPf` | f2clib.c | `f2clib.c` | placea_, voicin_, vparms_ | fptodp, dpadd, floor, dpsub, dptoli | 2026-11-15 | OK; calls equal, FP op counts differ only by register moves |
| 0x3ef230 | 308 | `ham84___FPiPiPi` | ham84.c | `ham84.c` | decode_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3ef370 | 484 | `hp100___FPfPiPiP19lpc10_encoder_state` | hp100.c | `hp100.c` | prepro_ | - | 2026-11-15 | OK; calls equal, FP op counts differ only by x * 2 as x + x |
| 0x3ef560 | 1212 | `invert___FPiPfPfPf` | invert.c | `invert.c` | analys_ | - | 2026-11-15 | OK; calls equal, FP op counts differ only by the abs(x) test folded into x > c / x < -c compares |
| 0x3efa20 | 536 | `irc2pc___FPfPfPiPfPf` | irc2pc.c | `irc2pc.c` | synths_ | sqrtf | 2026-11-15 | OK; calls equal, FP op counts differ only by register moves |
| 0x3efc40 | 660 | `ivfilt___FPfPfPiPiPf` | ivfilt.c | `ivfilt.c` | analys_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f1380 | 200 | `lpc10_decode__FPiPfP19lpc10_decoder_state` | lpcdec.c | `lpcdec.c` | PTT_Heartbeat | chanrd_, decode_, synths_ | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f1450 | 220 | `lpc10_encode__FPfPiP19lpc10_encoder_state` | lpcenc.c | `lpcenc.c` | PTT_Heartbeat | prepro_, analys_, encode_, chanwr_ | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f1530 | 48 | `lpcini___Fv` | lpcini.c | `lpcini.c` | init_lpc10_decoder_state, init_lpc10_encoder_state | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f1560 | 76 | `create_lpc10_encoder_state__Fv` | lpcini.c | `lpcini.c` | PTT_Init | malloc, init_lpc10_encoder_state | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f15b0 | 1012 | `init_lpc10_encoder_state__FP19lpc10_encoder_state` | lpcini.c | `lpcini.c` | PTT_Heartbeat, create_lpc10_encoder_state | lpcini_ | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f19b0 | 76 | `create_lpc10_decoder_state__Fv` | lpcini.c | `lpcini.c` | PTT_Init | malloc, init_lpc10_decoder_state | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f1a00 | 612 | `init_lpc10_decoder_state__FP19lpc10_decoder_state` | lpcini.c | `lpcini.c` | PTT_Heartbeat, create_lpc10_decoder_state | lpcini_ | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f1c70 | 1332 | `lpfilt___FPfPfPiPi` | lpfilt.c | `lpfilt.c` | analys_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f21b0 | 260 | `median___FPiPiPi` | median.c | `median.c` | decode_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f22c0 | 940 | `mload___FPiPiPiPfPfPf` | mload.c | `mload.c` | analys_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f2670 | 1168 | `onset___FPfPiPiPiPiPiPiP19lpc10_encoder_state` | onset.c | `onset.c` | analys_ | r_sign | 2026-11-15 | OK; calls equal, FP op counts differ only by one abs(x) test folded into x > c / x < -c compares |
| 0x3f2b00 | 3292 | `pitsyn___FPiPiPiPfPfPiPiPiPfPfPiPfP19lpc10_decoder_state` | pitsyn.c | `pitsyn.c` | synths_ | fptosi, logf, expf | 2026-11-15 | OK; calls equal, FP op counts differ only by register moves |
| 0x3f37e0 | 2576 | `placea___FPiPiPiPiPiPiPiPiPi` | placea.c | `placea.c` | analys_ | i_nint | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f41f0 | 1476 | `placev___FPiPiPiPiPiPiPiPiPiPiPi` | placev.c | `placev.c` | analys_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f47c0 | 204 | `preemp___FPfPfPiPfPf` | preemp.c | `preemp.c` | analys_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f4890 | 92 | `prepro___FPfPiP19lpc10_encoder_state` | prepro.c | `prepro.c` | lpc10_encode | hp100_ | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f48f0 | 220 | `random___FP19lpc10_decoder_state` | random.c | `random.c` | bsynz_ | - | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f49d0 | 316 | `rcchk___FPiPfPf` | rcchk.c | `rcchk.c` | analys_ | - | 2026-11-15 | OK; calls equal, FP op counts differ only by the abs(x) test folded into x > c / x < -c compares |
| 0x3f4b10 | 1040 | `synths___FPiPiPfPfPfPiP19lpc10_decoder_state` | synths.c | `synths.c` | lpc10_decode | pitsyn_, irc2pc_, bsynz_, deemp_ | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f4f20 | 1292 | `tbdm___FPfPiPiPiPfPiPiPi` | tbdm.c | `tbdm.c` | analys_ | difmag_, fptosi | 2026-11-15 | OK; calls and FP ops equal |
| 0x3f5430 | 3164 | `voicin___FPiPfPfPiPiPfPfPiPfPiPiPiP19lpc10_encoder_state` | voicin.c | `voicin.c` | analys_ | vparms_, i_nint, sqrtf | 2026-11-15 | OK; calls equal, FP op counts differ only by register moves |
| 0x3f6090 | 2184 | `vparms___FPiPfPfPiPiPfPiPiPiPiPfPfPfPf` | vparms.c | `vparms.c` | voicin_ | r_sign, i_nint | 2026-11-15 | OK; calls equal, FP op counts differ only by x * 2 as x + x |

## Tables

All 52 static data objects of the units equal the ELF's words (checked from the port objects compiled
at `-O0`, where none is folded away): `tau` (60), `buflim` (4), `precoef`; `kexc` (25); `bit` (10),
`iblist` (53); `ivtab` (32), `corth` (32 floats), `detau` (128), `rmst` (64), `detab7` (32), `descl`
(8 floats), `deadd` (8), `qb` (8), `nbit` (10), `zrc` (10), `bit` (5), `ethrs`, `ethrs1`, `ethrs2`,
`ethrs3`; `enctab` (16), `entau` (60), `enadd` (8), `enscl` (8 floats), `enbits` (8), `entab6` (64),
`rmst` (64); `dactab` (128); `vdc` (100 floats), `vdcl` (10 floats), `nvdcl`; and the 20 `c__N` /
`c_b2` argument constants. Every float constant in the code matches an ELF immediate (signs and
integer constants used as floats accounted for).

## Differences from the public coder (the ELF wins)

As far as I remember the public f2c translation; each point is what the ELF has:
- `sqrt`, `log` and `exp` are the single-precision `sqrtf` / `logf` / `expf` (energy, irc2pc, bsynz,
  voicin, pitsyn); `r_sign` returns a float. `i_nint` stays in double (`fptodp`, `dpadd`, `floor`).
- bsynz has no third tap in its excitation filters (no `+ lpi3 * 0` / `+ hpi3 * 0`) and no `* 1.f`
  in the noise and doublet scaling.
- `precoef` (analys), `ethrs`, `ethrs1`, `ethrs2`, `ethrs3` (decode) and `nvdcl` (voicin) are .sbss
  words set to their constant on the first call under an `init$N` byte guard (a compiler artefact;
  same values). The port has plain initialised statics.
- voicin_ takes a 13th parameter (`af`, `&c__3` from analys_) that it never reads; the DWARF leaves
  it unnamed. placev_'s `oslen` and `dvwinh` are not read either.
- voicin's smoothing dispatch is the ELF's jump table (`0x4679c0`): decision histories 12 and 15 make
  no change, 13 and 14 take the two "C1 / C2 alone" rules.
- The integer types are 32-bit `int` (f2c's default `integer` is `long`).

## Port notes

- **Float literals.** The ps2dev GCC for the R5900 converts decimal float literals toward zero, so a
  nine-digit decimal that rounds to the nearest float is one ulp low whenever the decimal lies below
  the exact value (`.699999988f` gave `0x3f333332`, the ELF has `0x3f333333`; first seen in four of
  the decode / encode / synths tables). Every float literal that is not exactly representable is a
  C99 hex float (decimal in a comment). The same trap applies to any float constant in `src/`.
- Float to integer: the ELF calls `fptosi` (truncating, saturating); the port compiles `cvt.w.s`
  (also truncating on the EE). Same values in range; the codec never converts out-of-range values.
- No fused multiply-add: `lpc10.h` sets `#pragma GCC optimize("fp-contract=off")`; the port objects
  have no `madd.s` / `msub.s`. The port compiles with `-O2` (the ELF's code is unoptimised); GCC's
  exact rewrites (`x * 2` as `x + x`, `x + -1` as `x - 1`, `x / 2^n` as a multiply) give the same
  values.
- `create_lpc10_*_state` use the C library `malloc` (the ELF calls the game's `malloc`).
- The R5900 FPU has no NaN or infinity and its rounding differs from IEEE: the port's results on the
  EE (or in PCSX2) come from the same FPU rules as the original's; on an x86 host they would differ.
- No guarded statics: the units are plain C, so the port's `-fno-threadsafe-statics` does not touch
  them; `port/CMakeLists.txt` needed no change (its `GLOB_RECURSE` over `compat/*.c` picks up the
  subfolder).

## Self-test (`port/test-hooks/lpc10/`)

Built with `port/test-hooks/lpc10/build.sh <build>` (idle pad); the test runs once at pad read 200 (title
screen) and takes about 0.25 s per run of 120 frames on the emulated EE. Final run `lpc3` (tree = HEAD
28b71e61 + this work), identical to the earlier runs `lpc1` / `lpc2` on older trees:

| segment (30 frames) | input RMS | analysis: voiced half frames | mean pitch lag (fully voiced frames) | decoded voiced halves | output RMS |
| --- | --- | --- | --- | --- | --- |
| S silence | 0.0000 | 0 / 60 | - | 0 | 0.0003 |
| V pulse train, period 80, formants 700 / 1220 / 2600 Hz | 0.3009 | 58 / 60 | 80.0 (29) | 58 | 0.3525 |
| N white noise | 0.1725 | 4 / 60 (the two frames of V carried over by the delay) | 80.0 (2) | 4 | 0.2177 |
| X period-57 voicing / noise every 8 frames | 0.2577 | 26 / 60 | 57.8 (13) | 24 | 0.2491 |

Per frame: the vowel is called voiced with pitch index 41 (lag 80, the exact period) from frame 33,
two frames after it starts (the analysis delay), and decodes with pitch 80 one frame later; noise is
unvoiced with negative RC1 (a high-pass spectrum, as expected for white noise after pre-emphasis);
the period-57 voicing is coded as lag 58 (the nearest entries of the lag table are 56 and 58) and
the decisions follow every switch with the 2-3 frame delay; silence codes as unvoiced RMS 0 and
decodes to a residual of 0.0003 RMS. Non-finite values (in RMS, the RCs or the output): 0. Bits of
`lpc10_encode` (state A) equal the step-by-step encoder (state B) for all 120 frames; a second run on
fresh states gives the same checksums (bits `287b3491`, output `dd8c9701`), the same in all three
boots.

What this proves: the port's encoder and decoder run end to end on the EE, are deterministic, keep
their state only in the two records, and behave like an LPC-10 coder on these inputs (silence stays
silent, a steady pulse train is voiced at its period, noise is unvoiced, decoded energy follows the
input, no overflow). It does not prove bit equality with the original library: no reference output
exists and no MIPS user-mode emulator (qemu-user, unicorn) is installed, so the ELF's own functions
could not be run on the same input. Equality rests on the instruction-level re-read, the structural
comparison, and the table and constant checks above.

## Image and heap

Default build (no hooks), HEAD 28b71e61 without and with the codec (`mips64r5900el-ps2-elf-size -A`):
`.text` 3,219,304 -> 3,248,328 (+29,024), `.rodata` 170,833 -> 174,409 (+3,576), `.data` 17,060 ->
17,380 (+320): **+32,920 bytes of image**, all of it the codec (code at `-O2` is about 29 KB against
the ELF's 41 KB of unoptimised code; the tables are 3.3 KB, half of them now read-only). The start of
`.bss` moves up by 32,896 bytes, but `_end` stays at `0x60f21c`: a `.bss` object at `0x580000`
(`CVU::m_VifHandlerID` and its unit) is placed on a large alignment boundary, and the padding before
it (now 0x54cbc8..0x580000, about 210 KB) absorbs the growth. The heap starts where it did, so the
codec costs the heap nothing; the next ~210 KB of image growth would not either, after that `_end`
moves by the alignment step.

Round trip (`port/test-hooks/state` from the tree, `-DSOCOM_HOOK_MISSIONS=8 -DSOCOM_HOOK_MALLOC`), eight
missions and eight returns each, no STOP:

| run | tree | in use at return 1 / 2-8 | break and largest free block at the returns |
| --- | --- | --- | --- |
| rt2 | HEAD 28b71e61 + codec | 18,655,788 / 18,655,884 B | `0x1c17000`, 3,960,832 B at returns 1, 4-8; `0x1e92000`, 2,584,576 / 1,601,536 B at returns 2 / 3 |
| rt3 | HEAD 28b71e61 + codec | 18,655,788 / 18,655,884 B | `0x1c17000`, 3,960,832 B at returns 1, 3-8; `0x1e92000`, 2,584,576 B at return 2 |
| rtb | HEAD 28b71e61 (baseline) | 18,655,788 / 18,655,884 B | `0x1c17000`, 3,960,832 B at returns 1, 4, 6-8; `0x1e92000`, 2,584,576 / 1,601,536 / 2,584,576 B at returns 2 / 3 / 5 |
| rt1 | HEAD 3eb5375d + codec | 18,666,948 / 18,667,044 B | `0x1c17000`, 3,960,832 B at every return |

In use is flat and byte-identical with and without the codec, and the largest free block is the same
3,960,832 B whenever the break is at `0x1c17000`. The returns whose break stayed at `0x1e92000` (a
mission-time block left above the menus' heap, smaller largest block) happen at HEAD as well, on
different returns from run to run: run-to-run variation of the heap layout, not the codec.

## Runs

All on the final tree (HEAD 28b71e61 + this work), booted through `port/tools/dev/run.ps1` (second
monitor; focus kept: True in every run):
- `def3` (default build, no hooks, no fake pad): intro, then `dlgMenu.rdr` (the main menu) at 15.7 s;
  the attract loop (`dlgHype.rdr`) at 44 s. Screenshot `57-lpc10/..._default_main_menu.png`.
- `lpc3` (self-test hook): the results above; the game goes on to the attract loop.
- `m8b` (fake pad `60:CROSS ... 400:CROSS` into m8, then CROSS every 60 reads from 700 to 1480 for the
  briefing cameras): player in the mission at 57.9 s, run to 270.7 s (213 s in the mission), no STOP,
  heap in use 23.02 MB at 90 s, 23.153 MB from 120 s to the end (+-300 B): steady. (An earlier run on
  HEAD 3eb5375d: 142 s in the mission, 22.94 -> 23.09 MB, flat from 160 s.)
- `rt2`, `rt3`, `rtb`, `rt1`: the round trips above.

The mid-mission screenshots of these runs came out empty (the boot script fell back to a screen
copy of the minimised window); the logs carry the results.