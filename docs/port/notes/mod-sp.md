# mod-sp notes (2026-11-14, socom-port-mod-sp): the last single-player gaps

Scratch `build/port/boot-mod-sp/` (untracked: NOTES.md, mine.txt, asm listings, `camscan.py`, the test edit
files `edits/t_vis_diag.txt` / `edits/t_noSTS.txt`, run logs sp1..sp9 and screenshots). Changed files: `mine.txt`
(zCamera, zAI, zVisual and the HUD in place; the small outside edits below; the `sp` test hook, its README
row and this note). Shared-file edit: `edits/s_znet.txt` (znet.h, listed in `shared.txt`). Screenshots
(untracked): `build/port/screenshots/50-sp/`.

## Result
- CAMERA_PARAMS written (parse, begin, tick): the m8 briefing cameras see out to 3200 with the fog at
  200..2100 and give the mission view back at their end (runs sp1 / sp1b, sp7).
- Cross-map AI routes use the ELF's code: an m8 AI was routed and walked from BaseMap over Dredge1 up to
  Dredge2 (run sp3).
- The muzzle-flash GIF stall: cause found (the saved texture-select chain was not quadword aligned), fixed,
  the ELF's `SaveTextureSelect` call restored; 45 and 58 flashes clean (sp4, sp6).
- `CHUD::StatusLine`'s readouts written; the small status shown in m8 with its gopt flag set by the test
  hook (sp5).
- Final tree (HEAD 1bb69a4f + mine + `edits/s_znet.txt`): run sp6 (`port/test-hooks/sp`, `pad_fire.txt`,
  `-DSOCOM_HOOK_MISSIONS=1 -DSOCOM_HOOK_PLAY_AT=999999 -DSP_NOROUTE`): intro movie skipped with CROSS, m8bs and
  m8tut1 skipped with X (80.8 / 82.8 s), mission 77 -> 240 s (163 s), 58 flashes, no STOP, no GIF stall,
  heap in use 22,981,028..22,981,412 B over the last 60 s. Run sp7 (`-DSOCOM_HOOK_CAMS_PLAY`): m8bs 80.2 ->
  101.6 s, m8tut1 101.6 -> 117.8 s played in full, CAMERA_PARAMS SAVE / RESTORE at each, no STOP.
  Run sp8b (`port/test-hooks/state`, `-DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=4`): in use at the four
  returns to the menus 18,564,276 / 18,564,372 / 18,564,372 / 18,564,372 B (flat; HEAD's figure), no STOP.
  Default build (`default.sh`): main menu (dlgMenu) at 16.6 s (run sp9def). Every boot kept the focus (a first
  try, sp8, sat paused at its start while another worker's emulator started and was stopped).

## 1. CAMERA_PARAMS (zCamera/zcam_main.cpp)
- Written: `CCamera::CmdParseParams` 0x1e6300, `CmdBeginParams` 0x1e61c0, `CmdTickParams` 0x1e5570 (the
  command registers no end function). File-local helpers for the ELF's inlined pieces: the key-track
  parser, the track sampler and the altitude-fog setters (`SetFogBottom` / `SetFogTop` have no symbol).
- Record (no DWARF, names the port's): a timeless 36-byte header - flags byte +4 (1 SAVE_PARAMS, 2
  RESTORE_PARAMS, 4/8 set fog / FOG_ON, 0x10/0x20 set altitude fog / FOG_ALTITUDE_ON), the latest key time
  +8, then six {offset, count} track pairs: FOV {t, horizontal deg, vertical deg} +0xc, CLIP {t, near, mid}
  +0x10, CLIP_ALL {t, near, mid, far} +0x14, FOG_RANGE {t, near, far} +0x18, FOG_ALTITUDE {t, bottom, top}
  +0x1c, LOD_MULTIPLIER {t, range scale} +0x20; the keys follow the header (zAnimCmdAddData).
- Begin: SAVE copies the world camera's fog switches, fields of view, planes, fog range, fog altitude and
  range scale into `m_saveParams`; the fog switches change at once. Tick: the command time (the sequence's
  `cmd_timer` plus dT, the duration consumed as other timed commands do; no duration: dT alone), each
  track lerped between the keys around it (the last key past the end, nothing before the first), applied
  through `SetHalfHorizontalFOVRadians` (half the angle, in radians), `SetHalfVerticalFOVRadians`,
  `SetNearClip` / `SetMidClip` / `SetFarClip`, the fog range and the altitude-fog rows; at the end
  RESTORE puts the saved values back.
- m8's data are compiled into the disc's anim archive (the parser never runs on it): 36 records (the
  scratch `camscan.py` decodes them), keys at time 0 except m8tut3's CLIP / FOG_RANGE over 2 s. The
  briefing cameras m8bs / m8tut1: SAVE, FOV 70 x 52.5, CLIP_ALL 4 / 3000 / 3200, FOG_RANGE 200..2100; the
  RESTORE command at the camera's end (it also runs when X skips the camera).
- Runs sp1 (cameras played in full, `-DSOCOM_HOOK_CAMS_PLAY`) and sp1b (`-DSP_NOPARAMS`, the "before"):
  in play the camera has near 4, far / mid about 600 (they follow the view), fog 1..600; during m8bs /
  m8tut1 far 3200, fog 200..2100; back to 1..601 at each restore. Before: the briefing views stay inside
  the 600-unit fog (hills gone); after: the hills and the far slopes show
  (`camparams-before/after-m8tut1.png`, `-m8bs.png`).

## 2. Cross-map AI routes (zAI/ai_maps.cpp, ai_path.cpp)
- Written: `CAiMaps::RegisterPathPlan` 0x199870's other-map branch - temporary "start" / "end" nodes on the
  set graph, linked to every graph node on the start's / goal's map (edge length the cell delta),
  `CGraph::BuildRoute`, one `PathPlanAddLeg` per pair of route points on one map, the two nodes deleted;
  `CAiPath::plan_addleg` 0x195b90's flag-0x20 split: a leg between two type-4 regions follows the map
  graph's route, through each edge's stored cell path (`CAiMap::route`, walked from the end in the region
  left), then on to the goal. `CAiMap::ReRoute` and `CAiMaps::GetLocationDelta` were already the ELF's.
- m8 has four AI maps: BaseMap (265 x 414), Dredge1 (75 x 27, floor 1), Dredge2 (40 x 20, floor 2), Lodge
  (17 x 16, floor 1); the set graph has 8 nodes, 10 edges (links BaseMap-Lodge at the lodge door, two
  BaseMap-Dredge1, Dredge1-Dredge2). No m8 script routes across maps in these runs.
- Run sp3 (`-DSP_ROUTE_PLACE=4`): OutPatrol5, put 4 cells from the BaseMap-Dredge1 link (0:138,57), routed to
  (2:15,10) on Dredge2: 2 legs, 9 points on Dredge1 and 5 on Dredge2; it walked onto Dredge1 at frame 526,
  up to Dredge2 at 1594 and reached its goal cell about 25 s after the order (map changes traced).
- Run sp2 (no placing): OutPatrol2 at (0:213,211) given a goal in the Lodge: the plan holds only the Lodge
  leg (quirk below); it walked straight at the lodge, stopped against the terrain and re-planned
  (PathRecover) every second.

## 3. The muzzle-flash light-map stall (zVisual/vis_main.cpp)
- Cause: `m_savedTS`, the saved texture-select chain that `VuExecuteState0` DMAs into the scratchpad
  packet (`CSPR::Copy`, toSPR), was only 8-byte aligned in the GCC build (0x584e68). The DMA source address
  drops its low four bits, so the REF tag and its VIF codes arrived half a qword late (run sp3 with the
  scratch diagnostic `t_vis_diag.txt`: m_savedTS `30000001 0103c170 01000101 6c01801e`, scratchpad
  `00000000 00000000 30000001 0103c170`): the VIF stream lost step, VU1 kicked a select from a broken GIF
  tag ("GS packet size exceeded VU memory size") and the path stuck. The ELF has the array at 0x511340.
  The selects themselves were right (the queued TEX0 / ALPHA equal the copied ones, the unpack addresses
  hit the entry's qwords 1 and 3).
- Fix: `m_savedTS` declared `aligned(16)`; `VuLightMap` calls `SaveTextureSelect` again as the ELF does
  (the earlier deviation is gone). Run sp4 (fix + diagnostic): scratchpad copy equal to m_savedTS, 45
  flashes, no "exceeded" line, no path stuck, heap flat.
- Light on the ground: with `-DSP_SLOWMO=3` (1/50 speed after the third flash, test camera on the player)
  the flash's warm patch shows on the snow in front of the rifle (`lightmap-after-flash.png`, sp4). The
  "before" (sp4b: the call removed, as the deviation had it) shows the same patch
  (`lightmap-before-flash.png`): in m8 the saved select rewrites the values the copy already holds; the
  call matters when a texture moves in GS memory later in the frame.

## 4. CHUD::StatusLine's debug readouts (Apps/FTS/hud/hud_devtext.cpp)
- Written: `CHUD::StatusLine` 0x3d9820 in full: the frame intervals from the CBench stamps (1/100 frame);
  doStatusLine (position, frame rate, push-to-talk, network bandwidth once a second, DY / 3D / 2D / SW
  and the longest tick, node counts; SELECT+SQUARE / SELECT+TRIANGLE toggles), doStatusLineSmall (fps
  min / now / max / average, awake / snoozing / sleeping AIs and entities, the event range, target range
  and awareness counters, position, velocity, map cell and altitude, the true cell when it differs, with
  `ai::visinfo` a visibility bar and line per hostile AI that sees the player, `ai::plot_tick`),
  doAssetReport, doTaskReport (the scheduler's tasks grouped by priority with timing bars and peaks, then
  the core tick's own intervals), doRenderReport (node / visual counts, the render stages from
  `CBench::drawTimeX`, once a second), doFPS. File-local helpers for the ELF's inlined interval rounding
  and bar peak.
- Small edits outside the HUD (in place, files clean at HEAD): `zSystem/zsys.h` (`CSched_Task::m_startTime`
  +0x14 / `m_stopTime` +0x18 from DWARF, friend CHUD), `zSystem/zsys_sched.cpp` (the RCNT0 stamps of
  `CSched_Manager::Tick`, ELF 0x2f38b0 / 0x2f3988, which the port had left out), `zSystem/zsys_bench.h` +
  `zsystem_holding.cpp` (the four particle counters 0x47650c-0x476518), `port/compat/net_bandwidth_offline.c`
  (`NetGetBandwidthInfo`, SCE-RT 0x418e80: no traffic). Shared edit `edits/s_znet.txt`: znet.h
  `friend class CHUD` (theVoice's push-to-talk time).
- Run sp5 (`-DSP_GOPT=doStatusLineSmall -DSP_VISINFO`, the flag set by the test hook): the readout in the
  top left in m8 (`statusline-small-visinfo.png`): `fps:48 81 132 95 ent=9 0 20/41`, `e=0 t=431 a=0 u=0`,
  `pos=2250 36 4728`, `vel=0 0 0`, `0:184,381 @ 36.9`, then one line per awake hostile AI holding the player
  on its list (OutPatrol1-5, Shed1: `A`, range, visibility). No STOP in the run.

## ELF quirks kept
- CAMERA_PARAMS: the vertical field of view is stored, then replaced by the horizontal one scaled to 448/640
  (`SetHalfVerticalFOVRadians` ignores its argument); a command without duration applies its keys at dT.
- RegisterPathPlan: the route's "start" node has no location, so it stands for the goal like "end": the leg
  from the start to the first link is never added (an AI far from the link walks straight at it). Edge
  lengths are not NULL-tested; the map of a leg is not NULL-tested; legs' answers are not used.
- plan_addleg: the first route point is set only inside the loop (always reached: two route nodes at
  least); the final leg's answer is not used.
- StatusLine: the task walk reads tasks 0, 2, 3, ... (task 1 never reported); the frame number goes to a %d
  as a 64-bit value (port: its low word); the asset lines are not bounded by the 30; the toggles
  (showTimers / showTriCnt) are only flipped; GetTask(0) and the camera entity's event / unit are not
  NULL-tested.

## Port deviations
- CAMERA_PARAMS parser: an element past a short last key group reads as 0 (the ELF reads through NULL; not
  on the disc: the data are compiled).
- StatusLine: the small status skips its entity lines when the camera has no entity (the ELF reads through
  it); the visibility bars' points have z / w 0 (the ELF leaves them as the stack had them).
- `m_savedTS` alignment (above).

## Not written / next
- The other camera command parsers (DYNAMICS_*, CAMERA_INDOORS, SET/GET_CAMERA_REGION_TEST): loaders that
  never run on the disc's compiled anims.
- The particle counters are not incremented anywhere in the port yet (the render report prints 0).
- No m8 script sends an AI across maps in the runs seen; the cross-map plan was shown with the test hook.

## Test hook
`port/test-hooks/sp/` (`hook_sp.cpp` + `build.sh`, with `../state/hook_state.cpp`; `pad_fire.txt`): see its
header and the README row. `hook_state.cpp` got `-DSOCOM_HOOK_CAMS_PLAY` (the briefing cameras play in full).
