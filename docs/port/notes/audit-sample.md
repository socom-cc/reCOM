# Sample audit of the marked functions (2026-11-15, socom-port-sample-audit)

Question: of the 4,314 marked, written functions (`@socom-skeleton` fence, at least 24 bytes in the
reference ELF), how many differ from the ELF, how badly and where. List: a uniform random sample of
120 (seed 20261115, 58,644 bytes), audited strictly in list order. Each row was disassembled from
`support/socom.elf` (`z.sh`, raw `dis.sh` where the compaction elided words, `sym.py` for tables,
strings and vtables, `dw.py` / `off.py` for layouts) and compared with the port's body instruction by
instruction: branches and their sense, stores (offset, width, bitfield masks), calls and argument
order, loop bounds, constants (every float bit for bit against the ELF word), signedness and width
of comparisons, return values (and whether a caller reads them), the vtable slot of every virtual
call, inlined helpers (checked against the helper the port calls instead). The standard is the
ELF's behaviour; ELF quirks are kept. HEAD d035c977; no marker was added, moved or changed and no
function moved file.

Verdicts: MATCH; DEFECT-FIXED (graded A: can change what the player sees or crash; B: wrong but
masked on the demo disc; C: cosmetic); DEVIATION-KEPT (differs for a reason recorded in a comment
or note); UNJUDGED (none).

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 103 |
| DEFECT-FIXED | 10 (A 0, B 6, C 4) |
| DEVIATION-KEPT | 7 |
| UNJUDGED | 0 |
| total | 120 |

2026-11-20 (audit-closeout): kept guards removed, now DEFECT-FIXED C: #42, #52, #111 (the user's rule:
the prototype's behaviour is kept; see [audit-closeout.md](audit-closeout.md)). The rates below are the
sample as first judged (7 defects).

## Rates (n = 120 judged rows; 95% intervals are exact Clopper-Pearson)

- All defects: k = 7, 7 / 120 = 5.8% (95%: 2.4% .. 11.6%). Over the 4,314 marked functions that is
  about 250 (100 .. 500) functions that differ from the ELF somewhere.
- Grade A: k = 0, 0 / 120 = 0% (95%: 0 .. 3.0%): at most about 130 functions with a visible or
  crashing difference, probably far fewer.
- Grade A or B: 6 / 120 = 5.0% (95%: 1.9% .. 10.6%).
- By bytes: the seven defective functions are 7,816 of the 58,644 sampled bytes (13%).

By function size (bytes in the ELF):

| Size | Rows | Defects | Rate |
|---|---|---|---|
| < 100 | 12 | 0 | 0% |
| 100 .. 299 | 49 | 1 | 2% |
| 300 .. 699 | 34 | 1 | 3% |
| >= 700 | 25 | 5 | 20% (95%: 7% .. 41%) |

Large functions carry the defects: one in five of the functions of 700 bytes or more differs, against
one in 47 below that.

By module (rows / defects): zSeal 30 / 4, zAnim 16 / 0, zNode 9 / 0, Apps/FTS/hud 9 / 0, zGrid 6 / 0,
zNetwork 6 / 0, zAI 5 / 2, zUI 5 / 0, zFTS 4 / 0, zUtil 3 / 0, zBody 3 / 0, zTexture 3 / 0,
zArchive 2 / 1, zParticle, zSoftImage, zValve, zReader 2 / 0 each, and one row each (no defect) in
zRender, zWeapon, zTwoD, zMath, zVehicle, zSystem, zInput, zVisual, zIntersect, Apps/FTS/game,
Apps/FTS/state. The module counts are too small to rank modules; zSeal + zAI hold six of the seven.

By kind: two float constants one ulp off (rows 14, 58) and one double constant built from the wrong
literal (row 100); one comparison wider than the ELF's (row 17); one call left out (row 46); one
error path that skips a store (row 21); one rounding order (row 56). No wrong vtable slot, no wrong
branch sense, no wrong offset, no wrong argument order in the sample.

## Fixes (ELF addresses)

- Row 14, `CSealCtrlAi::SelectFireParams` 0x263a30 (zSeal/seal_ai.cpp), B: the out-of-range burst's
  trigger-down range is the word 0x3dcccccc (0x263cf0); the port literal `0.09999999f` parses to
  0x3dcccccb. Now `0.099999994f`. One ulp of a random burst time.
- Row 17, `CAiMaps::SetRegionType` 0x1971c0 (zAI/ai_maps.cpp), B: the old type's corner list is
  compacted with `std::find` / `remove_copy` (0x1972d0), whose `CAiMapLoc ==` compares x and y only.
  The port compared the whole word, map id included, so a corner of the same x / y on another map
  would stay listed. No m8 script repaints a region onto another map's corner (masked).
- Row 21, `zar::CZAR::WriteDirectory` 0x1d81a0 (zArchive/zar_main.cpp), B: one seek to the end; when
  it fails the archive's modified flag is cleared (0x1d843c) and false returned. The port sought
  twice and returned without clearing the flag. Archives are never written on the demo path.
- Row 46, `CAiState::Signal` 0x2dbdc0 (zSeal/seal_aistate.cpp), B: after `ClearGoal` the ELF writes
  an AI log record (0x2dbe3c: `PutAiLog(5, 8, {AI state, signal})`). The port left it out with the
  note "no AI log", but `PutAiLog` and the log exist in the port; the log is enabled only from
  `process_arguments` (0x174248), so nothing is written in play.
- Row 56, `CZSealBody::InStateStand` 0x27ab70 (zSeal/seal_body.cpp), C: the turning thresholds are
  `lr * (lr * (0.3 - sV))` and `1.5 sV + lr * (lr * (0.5 - 1.5 sV))` (0x27adec, 0x27ae20); the port
  multiplied `lr * lr` first. Rounding order only (at most an ulp at the threshold).
- Row 58, `CAiMaps::GetInterpolatedShadow` 0x19b290 (zAI/ai_maps.cpp), B: the final scale is
  0x3eaaaaab (0x19ba28); the port literal `0.3333333f` parses to 0x3eaaaaaa. Now `0.33333334f`. The
  node light of every character is off by one ulp of a 0..1 shade.
- Row 100, `CSealUnit::GetMyPointOutAnimStart` 0x2ced80 (zSeal/seal_unit.cpp), B: the dot threshold
  static is the double 0xbfe99999a0000000, i.e. `(double)-0.8f` (0x2cef7c). The port's comment named
  that word but the initialiser was the double `-0.8` (0xbfe999999999999a), so a dot of exactly
  -0.8f started the point-out signal where the ELF does not.

No fix is grade A, so no fix is visible to the player; none changes a code path the demo runs other
than by a float ulp (rows 14, 56, 58) or not at all (17, 21, 46, 100). What the runs show is that
the tree still plays as before (below).

## Kept deviations (recorded; not counted as defects)

- Unread return values, the port's `void` recorded in the comment, every caller checked to drop the
  ELF's value: rows 5 (`CZKit::InitItemModel`, callers 0x289f70, 0x28a01c, 0x2a63ec, 0x2a6a04),
  9 (`CFlyoutMachine::Tick`, 0x31ada8), 82 (`CTexture::SetupSpecialTextures`, constant 0, 0x2f9590),
  88 (`CSealCtrlAi::PostMortemPreTick`, constant 1, as the base in audit-unmarked-a), 120
  (`CZAnimMain::AnimLoadZRDFile`, 0x1c1ec4 / 0x1c2250).
- NULL or past-the-end reads the ELF makes and the port guards, recorded: rows 42
  (`CTSetMode::Parse`, an empty list), 52 (`CSealCtrlAi::AnimSignal`, the SUSPENDED setup bit written
  through NULL when the push did not land on top), 111 (`CLightMap::CLightMap`, the light-map
  texture outside a mission), 64 (`CreateNewGameStateHandler`, strncpy where the ELF memcpy's 64 / 32
  bytes from a string: only the bytes after the terminator differ; online only).
- Row 48, `CValvePool::Release` 0x2f6c10: the port drops a pooled valve's callbacks before it goes
  back to the pool; the ELF keeps them, so a reused temporary valve would call `_rethrow_grenade` with
  the pickup of an earlier use (freed by then). Recorded in the function's comment. This is the only
  kept deviation that changes behaviour on a path the game can take; it is a guard against a
  use-after-free the ELF has, not a port necessity. Left for the coordinator's decision.

## Leads for targeted audits

1. Float literals copied from the disassembly annotation (rows 14 and 58). `cz.py` prints a float
   constant with `'%.7g'`, which does not round-trip: 0x3dcccccc prints `0.09999999`, 0x3eaaaaab
   prints `0.3333333`, 0x3f860a92 prints `1.047198`, and each of those parses to another word.
   `flt7.py` (scratch) lists every 7-significant-digit literal in `src/` that more than one float
   word prints as: 161 sites, 33 distinct values. Confirmed against the ELF outside the sample:
   - `zMath/zmath.h` `RAD_TO_DEG = 0.01745329f` (0x3c8efa34; the name is backwards, it is degrees to
     radians): `CharacterDynamics::Load` 0x28a560 uses 0x3c8efa35 at all 23 sites, so every aim and
     slope limit it converts is one ulp off; `zFTS/fts_mission.cpp` has the same literal twice.
   - `zMath/zmath.h` `PI = 3.141593f` (0x40490fdc): `CAppCamera::TickCameraWiggle` 0x1ea710, its
     only user in a `.cpp`, loads 0x40490fdb.
   - `CAiSPursue::Tick` 0x259930 (zSeal/seal_ai.cpp): `SetScanAngle(1.047198f)` and `(1.570796f)`
     are 0x3f860a96 and 0x3fc90fd8; the ELF loads 0x3f860a92 and 0x3fc90fdb (four and three ulps).
   - Still to check, by value: 0.7853982 (9 sites), 0.2617994 (6), 0.2702703 / 0.7297298 (hud
     score popup, 6), 0.3490658 (3), 57.29578 (3), 1.134464, 0.8726646, 0.5235988, 1.569051 (2 each),
     0.006666667, 4.712389, 3.926991, 0.03333334, 0.01640625, 1.047198, 1.570796, 107.3296,
     0.4363323, 10430.06, 100000.6. (The 94 sites of 4.656613e-10 parse to 0x30000000, the ELF's
     rand scale, as checked in row 14.) Recommended alongside: `cz.py` printing `'%.9g'`.
2. Constants built from a decimal where the ELF widens a float (row 100): `static double x = -0.8`
   for a `(double)-0.8f`. Grep `static double` and double literals next to `_dpflt` / `fptodp` calls.
3. Whole-word compares of bitfield records (row 17): the ELF's `CAiMapLoc ==` ignores the map id.
   The region lookups of the same file (`CAiMaps` 0x1978a0, 0x1976d0) and any `std::find` over
   `CAiMapLocVec` should be checked for the same.
4. "port: ... left out" comments (row 46): the omission was justified by a subsystem the port in
   fact has. Grep the comments that say a call is left out or skipped and check the callee exists.
5. Rounding order of products (row 56): `a * a * b` written where the ELF computes `a * (a * b)`.
   Only worth a pass where a threshold compares the result.
6. `CFileIO` layout: the DWARF has `m_cd` at +4, a union with `m_file`; the port keeps `m_cd` as a
   separate member (row 70 matches, but any reader of the shared word in the CD paths may not).
7. Size: 5 of the 7 defects are in functions of 700 bytes or more (20% of them). A targeted audit of
   the large marked functions would find most of what is left.

## Runs

All on HEAD d035c977 plus the six fixed files (isolated tree; the other workers' uncommitted files
kept out; the state hook built from HEAD's copy, not the working tree's). Focus kept in every run.
Screenshots (untracked) in `build/port/screenshots/55-sample/`.

- sast2 (zseal4's stability hook `hook_zseal1.cpp` + `pad_fire.txt`, 275 s): intro movie skipped
  with CROSS (57.2 s), briefing cameras with X (57.3, 58.3 s), in the mission for 218 s; no STOP,
  no exception. Combat: 70 "fires at" lines (Shed1 and OutPatrol1 at the player, Hutchins and
  OutPatrol1 at each other, OutPatrol4 at Bailey); kills, recycle timers and respawns (OutPatrol1
  alive 0 at 83 s, recycle 4.4, alive 1 at 95 s; OutPatrol3 respawn 1); the team following (follow
  modes FOLLOW / HIDE FOLLOW). Heap in use 22.84 .. 23.29 MB from 100 s to the end with combat,
  23.213 .. 23.214 MB from 200 s to the end (steady).
- saw3 (`port/test-hooks/win`, -DSOCOM_HOOK_WIN, 262 s): Snow3 rescued in Extract (201.0 s),
  mission_complete 0 -> 1, "EXIT: debrief open (objectives 3/7)" at 206.9 s, MISSION SUCCESSFUL on
  screen at 220 s (3 of 5 primary, 7 of 8 secondary). (saw2 ended the same way at 215.8 s; saw, a
  slower start, was cut off by its 240 s limit before the end.)
- sasr (HEAD's `hook_state.cpp`, -DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=8): eight missions and
  returns; in use 18,666,948 B at return 1 and 18,667,044 B at returns 2-8, largest free block
  3,960,832 B at every return (the HEAD figures of `zreader-preprocessor.md`); mission starts with
  2.99-3.00 MB largest free. Stopped after the eighth return (idle at dlgMenu).
- safe (front end, `boot-mod-zui2/pad_fe.txt`, 130 s): dlgMenu -> Options -> Audio, Video,
  Controller Selection, Controller Presets -> dlgMenu -> dlgHype -> dlgMenu, the same sequence as
  the zreader run; no STOP.
- sadef (default build: no hooks, no fake pad): dlgMenu at 16.7 s, the main menu on screen.

Environment note: between about 11:40 and 11:55 every worker's screenshots came out as 160 x 28
images (the PCSX2 window minimized at shot time; `pcsx2-boot.ps1` falls back to a screen copy of
the minimized window). The later runs above were not affected.

`python tools/socom.py audit independence --strict` passes.

## Result table

| # | Address | Function | File | Verdict | Grade | Evidence |
|---|---|---|---|---|---|---|
| 1 | 0x1c06b0 | CZAnimMain::AnimLoadSeq | zAnim/zanim_load.cpp | MATCH | | NAME / ACTIVATION ON_CALL (activation bits 1-7 = 2), inlined AnimParseCmd, data_size%4 append, free; size 28 -> state 0; offset stack |
| 2 | 0x2a74d0 | CZKit::GetTotalEnc | zSeal/seal_kit.cpp | MATCH | | m_item[i] (+0xd0) over m_num_items (+0x810), byte class 0..3 -> 1..4 |
| 3 | 0x243730 | CPipe::RenderNode | zRender/zrndr_pipe.cpp | MATCH | | active / visuals / region clip, 8 bbox corners in the ELF order, ALL_OUT pop, character mark, vid push, opacity stack realloc, facade, LOD-filter path, mesh / node children (fov 0 for meshes) |
| 4 | 0x1b0db0 | CZAnimMain::AnimParseExpression | zAnim/zanim_cmd_parse.cpp | MATCH | | operator / command (+2) / nested list between "(" ")" (0x44a0b8/c0), add-data inline, free lines 2590/2609, other types not stepped (quirk kept) |
| 5 | 0x2ae340 | CZKit::InitItemModel | zSeal/seal_kit.cpp | DEVIATION-KEPT | | void, ELF returns 1/0 unread (comment); cache / world model, instance, SetDynamicLight on the model, "grenade": SetActive slot 0x34, m_body->m_grenade->m_node; NULL inserted without model |
| 6 | 0x2902d0 | CZSealBody::SetRLegDamage | zSeal/seal_env.cpp | MATCH | | current level 0.3/0.7/0.9 (GetLegDamage), 4,3 -> 0.3, 2 -> 0.7, 1 -> 0.9, else 1.0; -0.01; UpdateHealth(4, 0) |
| 7 | 0x2b49f0 | CTTeam::Tick | zSeal/seal_tasks.cpp | MATCH | | select seal (ai_cmdid+8), GetSealCtrlAi slot 0x38, op 0 or / 1 and-not of +0xc4, UpdateEventMask, *dT = 0, 1 |
| 8 | 0x224b30 | zdb::CNode::Create | zNode/node_main.cpp | MATCH | | new 192, old name freed unless UNNAMED_NODE, strdup(name or "Node") lines 963/964 |
| 9 | 0x316550 | CFlyoutMachine::Tick | zWeapon/zwep_projectile.cpp | DEVIATION-KEPT | | void, ELF 0/1 unread by PreTick 0x31ada8 (comment); release loop (ReleaseFlyout returns 1 whenever count > 0), dist += dT*speed, past max -> done, step length^2 <= left length^2 advance, else end |
| 10 | 0x3d2780 | CWeaponSel::AfterClose | Apps/FTS/hud/hud_weaponsel.cpp | MATCH | | SetMenuState 0, pad (unchecked) buttons 9/7/6 up, Off (slot 0x18) on +0x2b0 x4, +0x20 x4, +0x4b0, +0x6a0, +0x9a0..+0xbc0, m_openstate 0 |
| 11 | 0x307550 | CMemCard::Uninit | zUtil/util_memcard.cpp | MATCH | | --count, at 0 unload mcserv then mcman, clamp < 0 to 0 |
| 12 | 0x218ec0 | zdb::CClutter::Read | zGrid/grid_clutter.cpp | MATCH | | node SetDynamic(1,1), no multipass, no decals; params 96 at +0, scale_inverse 4 at +0x60, the second Fetch's bool |
| 13 | 0x2d72c0 | can_run_anim | zSeal/seal_unit.cpp | MATCH | | ZAnim.GetAnim(name, NULL); state 1, or 5 when run_once clear (never) |
| 14 | 0x263a30 | CSealCtrlAi::SelectFireParams | zSeal/seal_ai.cpp | DEFECT-FIXED | B | 0x263cf0: out-of-range dn-time range is 0x3dcccccc; the port literal 0.09999999f gave 0x3dcccccb (1 ulp). Rest matches: ids 120-125 (table 0x451cb0 all 1), up 0x5a0 / dn 0x5a8, rand order up then dn, double add, navyseal bit, rand <= 0.5 |
| 15 | 0x225690 | zdb::CNode::SetApplyClutterFlag | zNode/node_main.cpp | MATCH | | own bits (0x5f b4, 0x5c b2), children and grandchildren SetDynamicLight(f, 0), recursion below |
| 16 | 0x1aff50 | zAnimLoadRandomWeight | zAnim/zanim_cmd_parse.cpp | MATCH | | 8-byte timeless record, first element real / int, else 0.5 |
| 17 | 0x1971c0 | CAiMaps::SetRegionType | zAI/ai_maps.cpp | DEFECT-FIXED | B | find / remove_copy (0x1972d0) compare CAiMapLoc x and y only; the port compared the whole word (map id too), so a same-corner region of another map was kept. Type bits, append, return as the ELF |
| 18 | 0x38f090 | C2DButton::LoadSpec | zUI/zui_2d.cpp | MATCH | | anims (g_hasAnims, count +0x400, 16-byte items), size floats, scale, offset, own font, states +0x74/+0x48/+0x1c/+0xa0 -> normal/active/pressed/disabled, centring both bytes |
| 19 | 0x234c90 | Particle::BufferElement::DrawRotated | zParticle/zparticle_buf.cpp | MATCH | | RotTransPers, z >> 4, size 256 m_size / w x cam +0x380, a / b from cos / sin, max(a, b) clip (signed), corners, texture REF on change, GIF tag, vertices c0 c2 c3 c0 c1 c2 with ST, CNT / FLUSH / DIRECT tag, Kick |
| 20 | 0x404380 | CZHudMissionCams::CZHudMissionCams | Apps/FTS/hud/hud_missioncams.cpp | MATCH | | C2D base, strings +0x24, 3 x +0xac, bitmap +0x250, string +0x2d0; +0x1c, +0x20, +0x35c zero |
| 21 | 0x1d81a0 | zar::CZAR::WriteDirectory | zArchive/zar_main.cpp | DEFECT-FIXED | B | 0x1d81fc: one fseek to the end; on failure m_modified is cleared (0x1d843c) and false returned. The port sought twice and returned without clearing m_modified. Key count, pack, secure copy, tail as the ELF (no archive is written on the demo path) |
| 22 | 0x1ce430 | CZAnimArgCmd::Copy | zAnim/zanim_anim.cpp | MATCH | | new 16, type 1 then this type, +8 0, m_cmd |
| 23 | 0x1dd080 | QFromRot | zAnim/zanim_sequence.cpp | MATCH | | (Z * Y) * X |
| 24 | 0x227040 | zdb::CNode::GetScale | zNode/node_main.cpp | MATCH | | diagonal [0][0] [1][1] [2][2] |
| 25 | 0x305ae0 | CFileIO::PS2FileName | zUtil/util_sonyio.cpp | MATCH | | strtok "/\\" rejoined with "\\", TOC copy or "%s%s" root + path, upper-case past the root, ";1" on a cdrom root |
| 26 | 0x2858b0 | CSealCtrl::CanPlaceBomb | zSeal/seal_control.cpp | MATCH | | team bit 0x100 picks the shack (theMission +0x658 / +0x65c) before the seal NULL test, item 154 held and loaded |
| 27 | 0x2a05f0 | CZSealBody::AlignForClimb | zSeal/seal_env.cpp | MATCH | | down: refpt goal, Rotate180 blend, conj quat Apply, acos with 2 pi (0x40c90fdb) wrap, drot y = -angle / loop; else anims 35 / ClimbMedium (weight blend) / ClimbOver / 44 / StepUp / 46 (GetPosW slot 0xc, 15.6), homing fields +0x44..+0x80 |
| 28 | 0x3022e0 | C2DString::Load(msg, font, x, y, w, h) | zTwoD/c2dstring.cpp | MATCH | | pos << 4, SetString slot 0x5c, font, SetTrans slot 0x20 when alpha 128, char size floats |
| 29 | 0x220940 | CQuat::Exp | zMath/zmath_main.cpp | MATCH | | length^2 == 0: identity; else cos, p sin / len |
| 30 | 0x1dee40 | CZSIScript::CZSIScript | zSoftImage/si_script.cpp | MATCH | | looped bit 1 set, loaded bit 0 clear, 1.0 / 1.0 at +0xc / +0x10, +0x8 +0x14 zero, numSiScript++ |
| 31 | 0x2680d0 | CRemoteCtrl::SetAiNetState | zSeal/seal_ai.cpp | MATCH | | state kept, opacity 1 - t / 15, SetActive(t != 15), ESCORTEE anchor type 4 / delete, rescued (17) change calls ftsGetPlayer (quirk), restrained bit copied when different |
| 32 | 0x1e1030 | CBlendOverlay::IsTriggerTime | zBody/body.cpp | MATCH | | loop fraction (frames - 1) / frames unless looped, step dT / (tf loop), backwards (state -1) and forward with wrap bounds |
| 33 | 0x1a2e80 | CVehicleRdr::Load | zVehicle/vehicle_main.cpp | MATCH | | entries of 268 bytes: name / display / character, team mask (out-of-range value ends it and is the mask), six flag bits +0x104, call signs (Bailey outside the chain), start (len >= 2, dir) or setup (count saturated 0..4, loop not), returns list != NULL |
| 34 | 0x39df70 | CUIVarManager::Reset | zUI/zui_var.cpp | MATCH | | TEMPORARY (1) vars: DetachAll, children freed unless packed, name NULL, type 1, clone / packed bits clear, DORMANT; CollectGarbage |
| 35 | 0x384670 | IsStickNearCenter | zUI/zui.cpp | MATCH | | abs(x) <= r and abs(y) <= r (0/1; bool recorded) |
| 36 | 0x2084a0 | CZPersonaState::FindNextTerrIndex | zFTS/fts_net_persona.cpp | MATCH | | counts cleared, 'P' objects with team bit 0x100 and slot < 8 counted, first empty slot or -1 |
| 37 | 0x1deb80 | CZSIScript::Load | zSoftImage/si_script.cpp | MATCH | | boneArchive.Fetch(name, this, unique) -> m_isLoaded, returned |
| 38 | 0x294b60 | CZSealBody::DamageBody | zSeal/seal_env.cpp | MATCH | | spent or 0 damage: 0; ResolveDamage(+0xf00, +0xf34), levels 0.1 / 0.3 / 0.7 / 0.9, +3 retmods at 3 and 2, flinch location 3, GetStance(0), 1 |
| 39 | 0x2f5900 | zSysFifoKick | zSystem/zsys_spr.cpp | MATCH | | CNT tag appended below 0x70003e60 when the last tag is not an end tag, D9 / D8 waits, SADR / QWC, ring room loop (0x40000 when equal), STR bit |
| 40 | 0x4034f0 | CFader::SetBrightness | Apps/FTS/hud/hud_fader.cpp | MATCH | | clamp to 1 then minimum (+0x94), SetTrans slot 0x20 with 128 (1 - b) |
| 41 | 0x218a10 | zdb::CClutter::Render | zGrid/grid_clutter.cpp | MATCH | | anim node (ClutterTick), region bits 7-11, far / near fade bands with 0.008 cut (translate +0x20 animated, +0x30 static), opacity saved / restored, matrix, add colour, light scale, mesh / node, pop |
| 42 | 0x2b73a0 | CTSetMode::Parse | zSeal/seal_tasks.cpp | DEFECT-FIXED | C | kept earlier; guard removed 2026-11-20: get_mode of the type read through NULL (0x2b7438). Earlier: port guard recorded in the comment: an empty list gives get_mode(NULL), the ELF reads element type through NULL (0x2b7438); else 12-byte record, mode byte, "ai" index |
| 43 | 0x231dd0 | zdb::CRipple::Tick | zNode/node_wave.cpp | MATCH | | age += dT, at life: erase (iterator from erase), free pool, reset the visual's vertices (+6 0, +0xc 32768, +0xe 0) unless another running ripple has the visual, inactive |
| 44 | 0x2fc760 | zdb::CDynTexList::Add | zTexture/ztex_manager.cpp | MATCH | | handles not listed (GetHandle) appended with grow-by-one, their palette unless found, then the list's palettes not found |
| 45 | 0x392420 | CListItemArrayTypeImpl::CListItemArrayTypeImpl | zUI/zui_2d.cpp | MATCH | | min(row count, columns), enabled, ListItem per cell, image (type 0: pushed, no font) / timed text (2), VALUE Format slot 0x60, COLOR slot 0x28 (x, y, z), DISABLED clears both, else CUIVariable::Format 768; SetFont 0x1c, SetScale 0x24 |
| 46 | 0x2dbdc0 | CAiState::Signal | zSeal/seal_aistate.cpp | DEFECT-FIXED | B | 0x2dbe3c: PutAiLog(5, 8, {AI state, signal}) after ClearGoal was left out ("no AI log"), but the port has PutAiLog and the AI log (enabled only from process_arguments, so off in play). Enter (Reset inline, OnSignal 4, mode 1, speed, peek 2, setup), exit, push (+0x1c bits, speed, map loc word), resume, SetTrigger x2, OnSignal as the ELF |
| 47 | 0x322b80 | cbDisbandClan | zNetwork/zNetMedius.cpp | MATCH | | status +0x18: 0 -> "Unaffiliated" / " ", members deleted and size 0, member list, clan ids -1, "" copied (nothing), SUCCESS (NULL); else "Clan Disband Error: %s", FAILURE |
| 48 | 0x2f6c10 | CValvePool::Release | zValve/valve_list.cpp | DEVIATION-KEPT | | port DeleteCallbacks before FreeName, recorded in the comment (the ELF keeps a pooled valve's callbacks, so a reused temporary valve would call _rethrow_grenade with a freed pickup); behaviour-changing deviation, see report. Pooled: back to the pool's end, else deleted, as the ELF |
| 49 | 0x2b4c50 | CTRegion::Tick | zSeal/seal_tasks.cpp | MATCH | | region cached by AiMaps cookie (the ELF stores the cookie only with a cached region: same result), pickup mode types 4-7 / +0xc object +0x60 id, select seal / named (unknownId -3, "player" index 0) / id, missing entity clears name, team walk with alive + team bit, map id + x / y bounds |
| 50 | 0x219a50 | CPad::GetSingleClick | zInput/zin_main.cpp | MATCH | | m_click[b] == -1 -> -3, true |
| 51 | 0x217100 | zdb::CCell::~CCell | zGrid/grid_cell.cpp | MATCH | | light list erased (refs only), clutter Free, member dtors, ~CNode |
| 52 | 0x2609a0 | CSealCtrlAi::AnimSignal | zSeal/seal_ai.cpp | DEFECT-FIXED | C | kept earlier; guard removed 2026-11-20: the SUSPENDED check-cast is written through as is (0x260d58). Earlier: port NULL test before the SUSPENDED setup bit, recorded (the ELF writes +0xc through NULL when the push is not on top, 0x260d58). Table 0x451b60: 1 forget anim, 2 / 3 critical bit + flags 1 (ELF walks from the end: only the Debug line order differs), 4 push 18, 5 pop; UpdateStackFlags(1) |
| 53 | 0x276530 | CZSealBody::Crouch | zSeal/seal_body.cpp | MATCH | | CanCrouch inline (anims 18 / 87, water <= 8.5), stand path (desired 0, changed bit, ClearStack + Stand_0 unless standing), already crouched -> top, ClearStack(1, true) inline (ctrl 0, peek 2), Crouch_0(state, tfrac) |
| 54 | 0x229360 | zdb::CNode::CreateInstance(model, pos, rot) | zNode/node_model.cpp | MATCH | | Copy, position, rotation, model list append, m_parent only while single, m_model, model name, type 2 |
| 55 | 0x2ac1f0 | CZKit::GetCurMaxAmmoCount | zSeal/seal_kit.cpp | MATCH | | three unwraps, launcher with fire mode >= 4: grenade slot m_firemode[index] - 3 capacity, else the item's, 0 without |
| 56 | 0x27ab70 | CZSealBody::InStateStand | zSeal/seal_body.cpp | DEFECT-FIXED | C | 0x27adec / 0x27ae20: the turning thresholds are lr * (lr * (0.3 - sV)) and 1.5 sV + lr * (lr * (0.5 - 1.5 sV)); the port multiplied (lr * lr) first (rounding order, at most an ulp at the threshold). Rest matches: quadrant, close_enough x / z / turn, smoothing, pre-throttles, moving / turning / still branches, sneak push unless sneak / skitter / run, turnip clear, flags, MoveControl(fb, strafe) |
| 57 | 0x261460 | CSealCtrlAi::GetDefaultRouteType | zSeal/seal_ai.cpp | MATCH | | navyseal, aware counter 0, GOTO -> STEALTH (2), else DEFAULT (the ELF's second GetAiState is unread) |
| 58 | 0x19b290 | CAiMaps::GetInterpolatedShadow | zAI/ai_maps.cpp | DEFECT-FIXED | B | 0x19ba28: the final scale is 0x3eaaaaab; the port literal 0.3333333f gave 0x3eaaaaaa (1 ulp, same cz.py '%.7g' origin as row 14). Cells, span tests, weights, 0.98 renormalisation as the ELF |
| 59 | 0x1d22b0 | UIQuitClan | zAnim/zanim_menu.cpp | MATCH | | theLobby.QuitClan, 1 |
| 60 | 0x2392d0 | Particle::Source::CheckExtents | zParticle/zparticle_source.cpp | MATCH | | box flag +0x11c, min by !(min < p), max by max <= p, filled volume size^2 |
| 61 | 0x2234c0 | zdb::CNode::CreateInstance(CSaveLoad &) | zNode/node_io.cpp | MATCH | | unit params, facade bits 8-9 clear, world test, model_name / nparams 96 / regionmask, name freed (980), instance, matrix, bbox, type, flags word +0x5c, region mask +0xb8, type 2, ReadDataBegin |
| 62 | 0x3092b0 | zdb::CVisual::DereferenceDecals | zVisual/vis_main.cpp | MATCH | | vtype 0, slots, chain to temp (kind 1) / perm pools, next read after the put, slot cleared |
| 63 | 0x1d0900 | UITransferLeadership | zAnim/zanim_menu.cpp | MATCH | | argument name (INPUT_STRING -> first arg), TransferLeadership, 1 |
| 64 | 0x32bbf0 | CreateNewGameStateHandler | zNetwork/zNetMedius.cpp | DEVIATION-KEPT | | game name / password copied with strncpy where the ELF memcpy's 64 / 32 bytes from the string (0x32bdf0, 0x32be0c; recorded in the comments: only the bytes after the terminator differ). Entry only, valves, PlayerGamePassword (PERMANENT), clan side, request fields (10020, 2, 65000, world, clan), cbCreateGame |
| 65 | 0x18a2d0 | CAiMap::read_routes | zAI/ai_mapio.cpp | MATCH | | count (fread slot 0x24), resize, per 36-byte route: 8 bytes at +4, flags at +0, two cell tables, 1 |
| 66 | 0x21f2c0 | CMaterialExArray::ResolveMaterialIndex | zIntersect/int_material.cpp | MATCH | | NULL -> 0, map find, second or 0 |
| 67 | 0x2244a0 | zdb::CModelVector::GetModel | zNode/node_vector.cpp | MATCH | | NULL name -> NULL, first strcmp(name, m_name) == 0 |
| 68 | 0x187330 | CAiMap::GetClosestDir(loc, pos) | zAI/ai_map.cpp | MATCH | | GetCellPos inline (bounds -> 8, centre, 10-bit altitude, action offset), x/z direction normalised, N dot < 0 -> dirs 2..6 else 6..10 |
| 69 | 0x2a1850 | CZSealBody::CanTraverse | zSeal/seal_env.cpp | MATCH | | fwd hit node, states 2 / 8 / 5 / 9 / 10, stunned, poly app flags bits 4-6 == type, climb anims, facing 0.65 (0 * norm.y), edges, material offset, flags 1/2/3/5 true, 4: <= 5 true, <= 10 ImpactFront + false, <= 32 true |
| 70 | 0x305d00 | CFileIO::CFileIO | zUtil/util_sonyio.cpp | MATCH | | +4 -1, +8 / +0xc 0 (the port also clears its separate m_cd; in the ELF m_cd is a union with m_file at +4, see leads) |
| 71 | 0x2d5fb0 | CSealUnit::GetSealByIndex | zSeal/seal_unit.cpp | MATCH | | index < size, walk next, the element |
| 72 | 0x27d2a0 | CZSealBody::GetStance | zSeal/seal_body.cpp | MATCH | | flag and top not cycling (0x40): Stand2Crouch 0/1, Crouch2Prone 1/2, Stand2Prone 0/2 by the reversed bit 0x20; else m_state |
| 73 | 0x29b340 | GetCharacterHit | zSeal/seal_env.cpp | MATCH | | scope -> NULL, bbox-hit seals alive / no common team / not bit 17, GetTargetPosW slot 0x2c, world-to-screen, w > 1e-5, centre distance^2 < AutoAimDistSqd, depth > AutoAimMinDist, not behind the hit (GetZ of the hit, m_pos at +0), nearest |
| 74 | 0x207660 | CZBombState::CreateLocalBomb | zFTS/fts_net_bomb.cpp | MATCH | | zNetCreateObject(&i, 1, 2, 0, 0, 0, 0, NULL, "BombObject", struct index), -1 on failure / no object, 16 bytes cleared, index +0x1c, base_explosion1 +0x10 |
| 75 | 0x19c120 | CAiMaps::GetBoundary | zAI/ai_maps.cpp | MATCH | | map 0: cell bits 3-4 of byte 2 (NULL off the grid -> 0); else TransformTo the first map, map 0 cell or recursion after a second TransformTo |
| 76 | 0x321940 | CZNetwork::AddToFixList | zNetwork/zNetDme.cpp | MATCH | | new 28-byte copy pushed at the end of +4696 |
| 77 | 0x1c2950 | CZAnimNameIndexTable::Unload | zAnim/anim_main.cpp | MATCH | | free (line 1623), both words zero |
| 78 | 0x2f77e0 | CValve::CValve(name, value, type) | zValve/valve_main.cpp | MATCH | | name 0, value low 16, type bits 16-23, flag bits 24 / 25 clear, list, FreeName, strdup (438), the debug valve-watch walk has no effect |
| 79 | 0x3f8000 | CInGameWeaponSel::UpdateCharacter | Apps/FTS/hud/hud_ingame_weaponsel.cpp | MATCH | | owner's character weapons (+592): existing entries set up while i < size and < 6, the rest added, signed item bytes +0x114c |
| 80 | 0x2d6040 | CSealUnit::IsMemberOfUnit | zSeal/seal_unit.cpp | MATCH | | seals (+64), escortees (+76), deep: sub-units (+88) recursively |
| 81 | 0x3ff820 | CNetCnf::GetDev | zNetwork/zNetCnf.cpp | MATCH | | handle +0x8144 list + i * 576 |
| 82 | 0x2f92a0 | zdb::CTexture::SetupSpecialTextures | zTexture/ztex_read.cpp | DEVIATION-KEPT | | void, the ELF's constant 0 is unread by LoadGS (0x2f9590 overwrites v0; recorded "The ELF returns 0"). ShadowX_ / ReflectionX_, tbw, 6-qword select block, GIF tag, TEX0 / TEX1 0x61 / TEXA / CLAMP 5 / ALPHA 70, 100 + FIX 20, 68 as the ELF |
| 83 | 0x2f2ea0 | Headset::DisconnectedTick | Apps/FTS/game/headset.cpp | MATCH | | state 4 -> 3, 3: next line; 1: stop request (Stop + release) or stream ended (release); DeQueue, Acquire(-1), StreamSoundVolPan(vol, 0) or handle 0 + release |
| 84 | 0x2949f0 | CZSealBody::GetArmDamage | zSeal/seal_env.cpp | MATCH | | 0.3 / 0.7 / 0.9 of max -> 3 / 2 / 1, else 0 |
| 85 | 0x266320 | CSealCtrlAi::LadderClimbTick | zSeal/seal_ai.cpp | MATCH | | empty path: state 0, 0 (before the statics: no visible difference); next / after (CAiPath::next's zero dummy = CAiMapLoc::invalid {0}), climb blends 46-48, state 0 ladder test (type bits 7-11 == 4, PassesThrough, GetLadderByIndex), mid at the nearer end, ClearGoal + SetGoalPos(3, 0.01) inline, state 1 creep at mmt_move (CreepTick 0x8c, SetThrottle 0x20), 2 / 3 climb throttles, end: ClearGoal(3), creeping, pop, state 0; Output on a change |
| 86 | 0x3bfe60 | CZObjectiveList::Draw | Apps/FTS/hud/hud_objectives.cpp | MATCH | | on and no mission camera playing: each item's Draw (C2D slot 0xc); the dropped dynamic_cast has no effect |
| 87 | 0x2054c0 | CZSealState::RemoteSealUpdateCallback | zFTS/fts_net_seal.cpp | MATCH | | waiting list: nothing until the characters are loaded (theMission +0x588), then created, deleted, erased; then IncrementalUpdateRemoteSeal |
| 88 | 0x267b30 | CSealCtrlAi::PostMortemPreTick | zSeal/seal_ai.cpp | DEVIATION-KEPT | | void, the ELF's constant 1 unread (recorded, as the base in audit-a). nofade, respawn path (needs_respawn, fade 0.75 dT with _saturate 0..1 / 0..0, SetActive), recycle path (view cone at control +0x70, range, timer up / down, recycle_time, SetActive(0), event type bits, RecycleEntity) |
| 89 | 0x1d0990 | UIDeclineInvitation | zAnim/zanim_menu.cpp | MATCH | | argument (INPUT_STRING), atoi, DeclineClanInvitation, 1 |
| 90 | 0x2163a0 | zdb::CGrid::buildOrderedCellAtomList | zGrid/grid_main.cpp | MATCH | | view cell from (p - origin + 0.0001) * inv dim clamped, rings expanded by four neighbours until no add or 1600 |
| 91 | 0x23de80 | zrdr_flat_findtag_startidx | zReader/zrdr_main.cpp | MATCH | | array test, i from startidx while i < array[0].integer, string match -> the next element |
| 92 | 0x3d8070 | CActionTxtrMachine::Add | Apps/FTS/hud/hud_actionbitmap.cpp | MATCH | | cancel entry selection bit, entries 13 / 7 / 17: MP bomb icon (pool +0x620) or the performable action's icon and text (descriptor tested twice, UI string, default), SetTrans(0) slot 0x20, appended, 0 |
| 93 | 0x1b1b90 | zAnimLoadObjectMotionFromTo | zAnim/zanim_cmd_parse.cpp | MATCH | | 128-byte record (2002), NAME, RUN_TIME / TRANSLATE_VELOCITY (0x80, 0.001), ACCELERATE (>= 3) / DECELERATE (index walk), RELATIVE, FROM / TO (AT_NODE, INPUT_TRANSLATION, values, VALVES x3), velocity, ComputeRunTime + 56-byte acc appended, rotations (0x3c8efa35), scale from / to (1, [x y z], [s]), rates with the first run time |
| 94 | 0x2be520 | CTAction::Parse | zSeal/seal_tasks.cpp | MATCH | | action / state (0xffff) / auto_return, no action: NULL, 16-byte record, AddValve +8, state +0xc, bit 0 +0xe |
| 95 | 0x328b60 | NetInitThreadEntry | zNetwork/zNetMedius.cpp | MATCH | | AuxInitNetwork, ThreadId 0, ExitDeleteThread |
| 96 | 0x224420 | zdb::CDIVector::Exists | zNode/node_vector.cpp | MATCH | | found != end |
| 97 | 0x1b8840 | zAnimHealthTestTick | zAnim/zanim_cmd_tick.cpp | MATCH | | flag 1: min <= h <= max, else h <= min |
| 98 | 0x393280 | CListItemImageTypeImpl::~CListItemImageTypeImpl | zUI/zui_2d.cpp | MATCH | | member CPlainBmp: UIVarMixin DetachUIVar(NULL), ~C2D (implicit in the port), base vtable, delete |
| 99 | 0x1c53b0 | CZAnimMain::Open | zAnim/anim_main.cpp | MATCH | | open: Close inline (Unload, wildcard 1898, input ptr / digits, packet 159, size, flags); version 30, gravity 0xc11ccccd, LOD 2, six fields, 41 exp / inv_exp, InitCommands, NewAnimSet(2), three sets available, counters, open |
| 100 | 0x2ced80 | CSealUnit::GetMyPointOutAnimStart | zSeal/seal_unit.cpp | DEFECT-FIXED | B | 0x2cef7c: the dot threshold is the double 0xbfe99999a0000000 ((double)-0.8f); the port initialised the static with the double -0.8 (0xbfe999999999999a), so a dot of exactly -0.8f started the signal where the ELF does not. Navyseal, front / second member data, 40000 range, x/z directions, start flag cleared as the ELF |
| 101 | 0x3c0a80 | CZObjectiveList::ResolveIndex | Apps/FTS/hud/hud_objectives.cpp | MATCH | | 0 <= i < count (+0x20) -> *out = i, 1 |
| 102 | 0x27a250 | CZSealBody::UpdateQuadrant | zSeal/seal_body.cpp | MATCH | | still -1, prev copy, forward test fabsf((x/z < 0.325)) quirk, side test z/x < 0.325, hysteresis bounds (table 0x43a3b0 and the four overrides, all words equal), atan2f(z, x) bands, snaps |
| 103 | 0x329410 | cbGetLadderRanking | zNetwork/zNetMedius.cpp | MATCH | | status 0: LadderRanking TEMPORARY int var = +0x18, dependents updated |
| 104 | 0x403440 | CFlashFX::Reset | Apps/FTS/hud/hud_fader.cpp | MATCH | | times / dirs / timer 0, brightness = minimum, rate (1 - min) / 0 kept |
| 105 | 0x1e0620 | CZBodyAnimBlend::IsDone | zBody/body.cpp | MATCH | | first anim: loop fraction, t = dT tScale / (tf loop) + tfrac; backwards flag 0x20: t <= 0, else quitT <= t |
| 106 | 0x1e3160 | CBody::FindAuxNode | zBody/body.cpp | MATCH | | aux parts: own name (not nested), else FindChild(name, 1) (CNode slot 0x24) |
| 107 | 0x1d8f00 | zar::CZAR::CloseKey | zArchive/zar_main.cpp | MATCH | | the front open key erased when any; the argument unused |
| 108 | 0x1aba30 | zAnimLoadObjectDeleteChild | zAnim/zanim_cmd_parse.cpp | MATCH | | 8-byte record (4465), PARENT / CHILD (NAME inside or the tag) node refs, 0 when missing |
| 109 | 0x216f40 | zdb::CGrid::CGrid | zGrid/grid_main.cpp | MATCH | | CFRect, atoms / buffer / free (+0x30..+0x38), ordered cells counts and view (+0x10c..+0x118), cell count, posts, world, ring, anim manager, created byte |
| 110 | 0x1f3860 | CZNetGame::TenSecondLaunch | zFTS/fts_mission.cpp | MATCH | | start (not yet, master): start = net time + valve value * 1000, not set; stop (was, master): 0; flag stored and returned |
| 111 | 0x2268e0 | zdb::CLightMap::CLightMap | zNode/node_main.cpp | DEFECT-FIXED | C | kept earlier; guard removed 2026-11-20: m_lightMapTexture's texture is read as is (0x226990). Earlier: port NULL guard on CVisual::m_lightMapTexture recorded in InitLightMap (the ELF reads +0xc through it, 0x226990). CLight part (type 8, ranges, diffuse 128, opacity 64), unit matrix +0x110, alpha 68 (u64), shadow / reflection bits, dir and fade 1.0, motion and light bits as the ELF |
| 112 | 0x214620 | zdb::DiIntersect::GetNearestIntersect | zGrid/grid_di.cpp | MATCH | | no hits -> NULL, nearest to the tail (+4) by d^2 <= best (later wins ties), 32-byte records |
| 113 | 0x3fbcb0 | CInGameWeaponSel::OnOpen | Apps/FTS/hud/hud_ingame_weaponsel.cpp | MATCH | | loadout bytes 255 then up to 6 of the character's (0 read twice), heights, goal 10 / 219, state 1, next / prev / next inline (= GetNextItem(-1), GetPrevItem, GetNextItem), icons +0x94, selection flags, positions, background Off, slot 1 back (x + 171 quirk) / icon, texts off, icon clip SetPos, fades 40 / 128, SetMenuState(1) |
| 114 | 0x23e3c0 | zrdr_freearray | zReader/zrdr_main.cpp | MATCH | | string forgotten, array walk over [0, array[0].integer) (count element included), free (151), NULL; one level unrolled in the ELF |
| 115 | 0x320a60 | CEntityItr::GetSeal | Apps/FTS/state/st_exit.cpp | MATCH | | the entity when its +0x10 type is 2 (seal), else NULL, no end test |
| 116 | 0x1b8de0 | zAnimWhileTick | zAnim/zanim_cmd_tick.cpp | MATCH | | no skip: CmdNext(8), a false ProcExpr jumps (CmdSet +6), 1 |
| 117 | 0x2f8d30 | zdb::CTexture::SetName | zTexture/ztex_main.cpp | MATCH | | old name freed unless UNNAMED_TEX (305), strdup (306) or UNNAMED_TEX |
| 118 | 0x261400 | CSealCtrlAi::GetDefaultRouteBias | zSeal/seal_ai.cpp | MATCH | | navyseal: two statics 0.5 set once (two guards in the ELF, one in the port: same), always 1.0 |
| 119 | 0x1b3fd0 | CZAnimBlendMode::GetBlendSequenceValue | zAnim/zanim_cmd_parse.cpp | MATCH | | before the first key unchanged, linear between keys, last key after, FIX = 128 v clamped 0..255 |
| 120 | 0x1c1f30 | CZAnimMain::AnimLoadZRDFile | zAnim/zanim_load.cpp | DEVIATION-KEPT | | void, the ELF's 0 / -1 unread by both callers (0x1c1ec4, 0x1c2250; recorded). findfile(file, path), read, ANIMATION_DEFINITIONS (not freed on the early exits, quirk), lists, GRAVITY into ZAnim, USER_ACTION_ANIMATION, free |
