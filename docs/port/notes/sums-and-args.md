# Float sums, stack arguments and startup trig constants against the reference ELF

Worker `socom-port-sums`, on HEAD 1659a6d6 (no `src/` change since 7a469667). Three scan-driven
passes over all of `src/`; every changed line is justified by the instructions at the address
given. The scanners are in the worker's scratch folder (`build/port/boot-sums/`, untracked):
`fexpr.py` (symbolic FPU / ACC sums and VU0 ACC chains of an ELF function from a full objdump),
`ssums.py` (additive chains in the source), `cmp.py` / `rev.py` (source against ELF, both ways,
association only), `stk.py`, `mang.py`, `callargs.py`, `vacalls.py`, `fmtattr.sh` (stack and
variadic arguments), `mipsemu.py` (runs the ELF's libm float routines instruction by instruction
with R5900 rounding toward zero).

## Pass 1: float sums in the ELF's order

Method. `a + b == b + a` exactly, so only the association counts. Each source chain of three or
more terms with at least two products was reduced to its association shape (`(x+y)+z`,
`w+((x+y)+z)`, ...) and compared with the shapes of every FPU sum (`mul` / `mula` / `madda` /
`adda` / `madd` chains, loads resolved to base + offset, letters by member offset) and VU0 ACC
chain (`vmula<b>` / `vmadda<b>` / `vmadd<b>`) of the same fenced function; the reverse check
listed ELF sums no source chain of that function has (sums the port wrote with other names or
spread over statements).

Counts. 382 chains on 380 lines (182 fences, plus header inlines and unfenced helpers);
92 ELF sums from the reverse check, each read. Changed: 9 sums on 9 lines (and, on the same
lines, one product grouping and one missing `sqrtf`). Left:
- the ELF's order already (FPU or VU0), 294 chains (110 of them in audited functions);
- exact in either order: a zero term (`d.y = 0` / `unit_nz`: `MapCompass::Tick` x3,
  `AlignForClimb`, `CqbFacingDot` / `CqbFacesAway`, `GetClosestNode` x2, and the audited
  `CheckDIFwd1` / `ImpactFront` / `PostCheckDIDown`), `+ 0.0f` sums, subtraction chains that equal
  the ELF's `(-b) + a` forms (`CQuat::Div` x, y, z);
- through `sceVu0InnerProduct` in the ELF, same association (`CQuat::Normalize`, `Mul`, `Slerp`,
  `SlerpFaster`, `clip3DLine`);
- not ELF code: port traces (`ClipCameraChord`), integer sums, `zmath_holding.cpp` (`#if 0`).

| File | Function | ELF | Change |
|---|---|---|---|
| zCamera/zcam_main.cpp | `CCamera::TestLandmarkFOG` | 0x1e4578..0x1e4594 | the length is of `out` (pos - camPos), `(x x + y y) + z z`; the port summed camPos z first |
| zCamera/camera.cpp | `CAppCamera::CAppCamera` | 0x1eb81c..0x1eb840 | `(x x + y y) + z z`, and `m_goal_t_len` is its `sqrtf` (0x1eb834, stored 0x1eb840); the port stored the square |
| zMath/zmath_main.cpp | `CQuat::Div` | 0x220ecc..0x220ee0 | w = `((w w' + x x') + y y') + z z'` (port w, y, x, z) |
| zParticle/zparticle_instance.cpp | `Particle::Instance::Render` | 0x236b00..0x236b1c | depth = `m32 + ((x m02 + y m12) + z m22)` (port m32 + z + x + y) |
| zParticle/zparticle_source.cpp | `Particle::Source::Tick` | 0x239798, 0x2397a8, 0x2397c4..0x2397e4 | `(f r) (f r) <= (dx dx + dy dy) + dz dz` (port `((f r) f) r` and z first) |
| zNode/node_main.cpp | `CNode::GetRadiusSq` | 0x226fc8..0x226fe4 | both corners `(x x + y y) + z z` (port z first) |
| zNode/node_main.cpp | `CNode::GetRadius` | 0x226f68..0x226f84 | the same |

Found, not changed (outside the sums, and visible in rendering; for the coordinator):
- `CNode::GetRadius` 0x226f88..0x226fa4 returns `sqrtf(max(min, max))`; the port returns
  `sqrtf(min)`. `GetRadiusSq` 0x226fe8..0x227000 returns `max(min, max)`; the port returns 0 when
  min > max. Callers: `CPipe::RenderWorld` / `RenderAtom` (fog), `CCamera::InsideMidPlane`,
  `GetLandmarkFarPlane`.
- `CCamera::TestLandmarkFOG` 0x1e44c0: the ELF's first flag is `pos.y - radius <
  m_landmark_fog_top` (the `li v0,1` in the delay slot at 0x1e4528), the second the fog flag
  cleared when `radius + dist < m_fog_near`; it returns `first | (second & byte gp-32324)`. The
  port never sets its flag and ignores the distance.
- Products of three factors are grouped by the ELF too (`Source::Tick` above); a scan of them was
  not made (the shapes alone cannot tell `(a b) c` from `a (b c)` without the operands' names).

## Pass 2: arguments passed on the stack

Method. Callee side: functions that read their caller's argument area (loads at or above their
own frame, `stk.py`: 51). Mangled names with more than eight GPR or FPR words or `...`
(`mang.py`: 25). For each, the port's declaration, definition and calls against every ELF call's
argument registers and outgoing words (`callargs.py`). Variadic calls: 548 ELF calls from written
functions and 444 port calls with a literal format, matched by format text (`vacalls.py`); the
whole tree compiled with `-Wformat` and printf attributes added (in a test copy only) to
`CSealCtrlAi::Debug` / `Output`, `CConsole::Debug`, `C2DString::Format`: no warning.

| Function | Verdict |
|---|---|
| `OrdersMenu::SetupTuple` (16 words, 12 calls) | match (objectID, snum, vnum, onum, send, unit, command, data per call) |
| `CMissionObjectiveCam::Set` (12) | match |
| `CCircleClip::CircleSegmentClip` (13) | match (m_po, m_pi, m_rgbo, m_rgbi, m_uvo, m_uvi at 0x560540..) |
| `CMatrix::CMatrix` (16 floats) | match: `identity`; vis_main's `_StartingMatrix` is filled at startup in the ELF but has no reader |
| `Particle::Create3Sided`, `CreateVisuals` (5 calls, by-value copies) | match |
| `collideCylinders` (13 floats) | match |
| `CZProjectile::SetProjectile` (3 callers) | match |
| `CZWeapon::Fire`, static (`CTurret::Fire`) and virtual (`CZKit::Fire`, fixed by audit-large-a) | match |
| `CZNetwork::zNetCreateObject` (6 calls) | match |
| `sceVu0ViewScreenMatrix`, `sceSifCallRpc` (keyboard x3), `snd_PlayVAGStreamByLoc_CB`, `snd_DoExternCall_CB` x2 | match |
| variadic: every ELF call that passes fewer words than its format needs, and every count / word difference | match, but one below |
| `CSealCtrlAi::ActivateEx` "Task %d NULL" `Debug` | changed: the ELF sets only a0 / a1 (0x2608fc..0x260908), so `%d` reads a2, which still holds `push`; the port passed the task |

Not in `src/`: the lpc10 routines (`pitsyn_`, `placea_`, ...) and the MSL / SDK / middleware
internals. Lead: `zseal.h` declares an undefined `CSealCtrl::CreateAiEvent(EVENT, f32, f32, bool,
CPnt3D*, s32)` beside the ELF's overload; GCC warns that the call at `seal_ai.cpp`
`OnWeaponEvent` is ambiguous and takes the ELF's (it links).

## Pass 3: constants the ELF computes at startup

The ELF's `__sinit_*` functions call only `cosf` (eight calls); the one other startup-style
computation is the first-call static `max_y` (`sinf`, 0x25e99c). All inputs here are below
3 pi / 4, so `__ieee754_rem_pio2f` (0x167b38) takes its n = 1 path (`x - pio2_1 - pio2_1t`) and
`cosf` returns `-__kernel_sinf(y0, y1, 1)`, `sinf` `__kernel_cosf(y0, y1)`. `mipsemu.py` runs the
ELF's own instructions (R5900: every operation rounded toward zero) and reproduces KNIFE_DOT's
0x3f6803c8. The port's words were read from the compiled units.

| Constant | ELF input | ELF word | Port word (before) | Result |
|---|---|---|---|---|
| seal_control.cpp `FLASHBANG_DOT` | 0x3f5f66f3 | 0x3f248dba | 0x3f248dbb (input 0x3f5f66f2) | literal `0.642787576f /* 0x3f248dba */`, read back |
| seal_ai.cpp `max_y` | 0x3f5f66f3 | 0x3f441b7c | 0x3f441b7d | literal `0.766044379f /* 0x3f441b7c */`, read back |
| seal_env.cpp `RESTRAINT_DOT` | 0x3fbde44e | 0x3db27ebd | 0x3db27ebd | same, left |
| seal_env.cpp `CQB_DOT` | 0x3f91361e | 0x3ed8616b | 0x3ed8616b | same, left |
| node_util.cpp `DEFAULT_CLOSESTNODE_DOT` | 0x3f91361e | 0x3ed8616b | 0x3ed8616b | same, left |
| seal_env.cpp `KNIFE_DOT` | 0x3edf66f3 | 0x3f6803c8 | 0x3f6803c8 (audit-large-a) | left |

The other three `__sinit_seal_env.cpp` calls (cos of 0x3f32b8c2, 0x461cab0b, 0x469ee800:
`FLASHBANG_DOT` and `FALLBACK_DOT_MIN` / `MAX` of that unit) have no reader in the ELF.

## Runs

Isolated tree (HEAD plus the eight files), second monitor, focus kept, no memory card.
- def1: the default build boots to the main menu (dlgMenu at 24 s, the attract screen and back
  at 63 s); no STOP, no exception.
- m8a: `state/hook_state.cpp` and `render/pad_fire.txt` from HEAD, `-DSOCOM_HOOK_MISSIONS=1
  -DSOCOM_HOOK_PLAY_AT=999999`, 210 s: mission start at 101 s, briefing camera skipped with X at
  105.3 s, 106 s in m8 after it; no STOP, no exception; the patrols' and Shed1's scripts run,
  heap in use 23.03..23.08 MB to the end.

The scripted playthrough is not expected to be sensitive to these changes: they move words by
an ulp at most in particle depth / spawn range, quaternion division, node radii (squares only),
the landmark-fog distance (unused by the port's flags) and two facing thresholds
(`FLASHBANG_DOT` in `OnStunDamage`, `max_y` in `ComputeProjectileFireParams` for arced throws).
