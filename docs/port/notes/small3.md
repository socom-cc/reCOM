# small3 notes (2026-11-15, socom-port-small3): camera command parsers, CPnt3D operators, particle counters

Scratch `build/port/boot-small3/` (untracked: NOTES.md, mine.txt, the ELF listing `parseparams.txt`, run logs
s3a / s3h, the camera traces `cam_s3a.txt` / `cam_s3h.txt`, screenshots under `milestone/`). Changed files:
`src/gamez/zCamera/zcam_main.cpp`, `src/gamez/zMath/zmath.h`, `src/gamez/zSeal/seal_control.cpp`,
`src/gamez/zSystem/zsystem_holding.cpp`, `src/gamez/zSystem/zsys_bench.h`, the new test hook
`port/test-hooks/camcmd/` (+ its README row) and this note. Built on HEAD feb9357b (the commit that stops
GCC from trapping NULL accesses: the parameter parser below relies on it).

## 1. The camera animation commands (zCamera/zcam_main.cpp)

`CCamera::RegisterAnimCommands` 0x1e75c0 registers six commands (parse / begin / tick / end):

| command | parse | begin | tick | before | now |
|---|---|---|---|---|---|
| DYNAMICS_RELEASE_CAMERA | CmdParseRelease 0x1e7530 | - | CmdTickControlSwitch 0x1e7470 | parser returned NULL | written |
| DYNAMICS_ACQUIRE_CAMERA | CmdParseAcquire 0x1e74b0 | - | CmdTickControlSwitch 0x1e7470 | parser returned NULL | written |
| CAMERA_INDOORS | CmdParseIndoorsTest 0x1e7400 | - | CmdTickIndoorsTest 0x1e73f0 | parser returned NULL | written |
| SET_CAMERA_REGION_TEST | CmdParseSetRegions 0x1e7320 | - | CmdTickSetRegions 0x1e72f0 | parser returned NULL | written |
| GET_CAMERA_REGION_TEST | CmdParseGetRegions 0x1e7280 | - | CmdTickGetRegions 0x1e7270 | parser returned NULL | written |
| CAMERA_PARAMS | CmdParseParams 0x1e6300 | CmdBeginParams 0x1e61c0 | CmdTickParams 0x1e5570 | written (mod-sp) | parser re-checked |

No command registers an end function. The four ticks and CmdBeginParams were compared with the ELF and
match.

- The five small parsers: NULL for a NULL reader; else a `_calloc` record (`zcam_main.cpp`, the ELF's line
  numbers 162 / 178 / 207 / 232 / 264), `data_size` set to the record's size and `timeless` set.
  DYNAMICS_RELEASE / ACQUIRE: the 8-byte `_camera_control_cmd` with `release` / `acquire` set.
  SET_CAMERA_REGION_TEST: the 8-byte `_camera_set_regions_cmd`, `set_on` set when the reader holds `ON`,
  cleared otherwise. CAMERA_INDOORS and GET_CAMERA_REGION_TEST: the 4-byte header alone. The readers'
  other contents are not read.
- CmdParseParams, compared with the ELF instruction by instruction (`parseparams.txt`): the flags, the
  36-byte header, the run time (`!(key time <= run_time)`), the six tracks in order (FOV, CLIP,
  CLIP_ALL, FOG_RANGE, FOG_ALTITUDE, LOD_MULTIPLIER) with their key widths, the reader access (the inline
  `_zrdr::Get` and real getter) and the `zAnimCmdAddData` growth all matched. Two differences, both fixed:
  - the ELF writes a track's offset (at its first key) and increments its key count in the record
    before each key is appended; the port kept them in locals and stored them after the loop (same
    result). Now written into the record in the loop (`ParamsSetTrackOffset` / `ParamsCountTrackKey`,
    the track a template constant).
  - the port read a missing element of a short last key group as 0; the ELF reads Get's NULL as a node
    (low memory). The guard is removed: with HEAD's flags GCC compiles the read as a read (the port
    build has no trap in the function).

Test (hook `port/test-hooks/camcmd`, run s3a, with `../sp/hook_sp.cpp` and `../state/hook_state.cpp`,
`-DSOCOM_HOOK_MISSIONS=1 -DSOCOM_HOOK_PLAY_AT=999999 -DSOCOM_HOOK_CAMS_PLAY -DSP_NOROUTE`, `pad_fire.txt`):
300 HUD ticks after the briefing cameras, a reader file served from memory went through
`CZAnimMain::AnimParseCmd` command by command:

- DYNAMICS_RELEASE_CAMERA: type 0x2e, size 8, timeless, word +4 = 1; its tick turned
  `m_dynamics_controlled` 1 -> 0. DYNAMICS_ACQUIRE_CAMERA: type 0x2f, word +4 = 2; tick 0 -> 1.
- CAMERA_INDOORS: type 0x30, size 4; tick returned 0 (outdoors).
- SET_CAMERA_REGION_TEST (ON): word +4 = 1, tick left `m_do_region_test` 1; (OFF): word +4 = 0, tick
  1 -> 0. GET_CAMERA_REGION_TEST: size 4, tick returned 0 (the value just set).
- CAMERA_PARAMS (SAVE_PARAMS FOG_ON FOG_ALTITUDE_OFF and six tracks, integers and reals mixed): size 144,
  flags 0x1d (save, fog set + on, altitude set + off), run time 3; FOV at 36 with 2 keys {0 70 52.5}
  {2 60 45}, CLIP at 60 {0 4 600}, CLIP_ALL at 72 {0 4 3000 3200} {1.5 5 2500 2800}, FOG_RANGE at 104
  {0 200 2100}, FOG_ALTITUDE at 116 {0 10 40}, LOD_MULTIPLIER at 128 {0 1.5} {3 2}: every field as the
  text says. Begin + tick with dT 1 (dT -> 0, not done): half field of view 0.5672 rad (32.5 degrees),
  vertical 0.3971 (the horizontal scaled to 448/640: the ELF quirk), near 4, mid 600 (CLIP after
  CLIP_ALL), far 2933.333 (CLIP_ALL two thirds of the way), fog on 200..2100, altitude fog off 10..40,
  range scale 1.6667.
- CAMERA_PARAMS (RESTORE_PARAMS FOG_OFF FOG_ALTITUDE_ON): size 36, flags 0x36, no tracks; begin + tick
  (done) put back exactly the values traced before the test (0.6101 / 0.4271, 4 / 752.002 / 754.833, fog
  1..742.5, altitude 10..50, range scale 1).
- A NULL reader gives NULL.

## 2. CPnt3D::operator+ / operator* (zMath/zmath.h)

- `__pl__6CPnt3DCFRC6CPnt3D` 0x287890 (76 B): `Add(&other, &tmp)`, the result returned by value (copy to
  the return slot). `__ml__6CPnt3DCFf` 0x2878e0 (72 B): `Scale(s, &tmp)`, returned by value. Both are
  inline header functions that Metrowerks emitted out of line in seal_control.cpp: now defined inline
  in `CPnt3D`, const, returning `CPnt3D` (they were non-const, returned a reference and had no body).
- Callers (`xref.py`): `CSealCtrl::PostTick` 0x287778 / 0x287788 and `ai::DrawFunc<CDynGrenade>` 0x288a5c /
  0x288a6c; DrawFunc's two other point evaluations have both operators inlined. All are the grenade arc's
  point at time t, `(m_pos + m_vel * t).Add(&g, &r)` with `g = (0, -49 t^2, 0)`. The port's
  `CDynGrenade::PosAt` (seal_control.cpp) wrote it out as Scale, Add, Add: the same float operations in
  the same order; it now uses the operators. No other caller: none left.
- The other declarations checked against the ELF's symbols: removed as declared, never defined and absent
  from the ELF: `CPnt3D::operator-`, `CPnt3D::operator/`, the non-const `void CPnt3D::Normalize(CPnt3D*)`
  (the ELF has the const one returning the length, already declared), the static reference forms
  `CQuat::Apply / Normalize / Div / Mul / ToMatrix / Exp`, and `CMatrix::SetRotation` (the ELF has
  `SetRotate`). `CPnt4D` declares no operator but `operator=` (inline; the ELF has no out-of-line copy).
  `CPnt3D::operator=` 0x1a9170 stays implicit (three floats, as audit-unmarked-a2 found).
  `CMatrix::operator const float (*)[4]() const` 0x223170 (`__opRA4_A4_Cf__7CMatrixCFv`, two callers:
  `CNode::ComputeFacadeMatrix`, `CLensFlareSaturate::Tick`) is not declared in the port, which uses
  `m_matrix` there: left, reported.
- Camera trace (`hook_sp.cpp` camera lines, briefing cameras played in full): run s3a (this tree) and run
  s3h (HEAD feb9357b, same hook and flags) give the same lines through both cameras (m8bs, m8tut1: begin,
  tick, the 3000 / 3200 planes, fog 200..2100, restore) and the mission updates up to 4800; at update
  5400 one fog far value differs in the last digit (1143.7 / 1143.8; the fog follows the view, a
  frame-timing value).

## 3. The particle counters (zSystem)

`CBench::countParticleSources` 0x47650c, `countParticleSourcesProcessed` 0x476510, `countParticlesProcessed`
0x476514 and `countParticlesDrawn` 0x476518 are `.sbss` words. Every `$gp` access in the ELF's code
(`zs.sh`) is a read in `CHUD::StatusLine`'s render report (0x3db42c-0x3db444); none is written, no code
takes their address (no `addiu ...,gp` in that range, no lui / addiu pair), and `CBench::Reset` 0x2f3730
clears only `dmaTime` and the node / visual counters. In the original game the report prints 0 for all
four, so there is nothing to write: the port's 0 is the ELF's behaviour. The comments in
`zsystem_holding.cpp` and `zsys_bench.h` now say so (they said the port did not count them "yet").
What each would count, from the names only: particle sources, sources processed, particles processed,
particles drawn.

## ELF quirks kept

- CAMERA_PARAMS: a missing element of a short last key group is read through NULL.
- SET_CAMERA_REGION_TEST: anything but `ON` (including no argument) clears the test.

## Port deviations

None added. The mod-sp deviation of the CAMERA_PARAMS parser (a short group's element read as 0) is gone.

## Runs (all kept the focus)

- s3a (this tree, camcmd + sp + state hooks, `pad_fire.txt`, briefing cameras played in full): cameras
  53.1 -> 87.3 s, parser test at 92.5 s, mission to 225 s (138 s after the cameras), 56 muzzle flashes, no
  STOP or exception, heap in use 23,094,572-23,094,812 B from 200 s to the end.
- s3h (HEAD, sp + state hooks, same flags, 140 s): the camera trace reference.
- `default.sh`: the normal build links (no hooks, no fake pad).
