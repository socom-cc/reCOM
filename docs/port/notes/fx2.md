# boot-fx2 notes (2026-11-12, socom-port-fx2)

Scratch for the smaller effects left over by earlier workers. Untracked. Changed files: `mine.txt`;
shared-file edits in `edits/` (srep.py format, listed in `shared.txt`, applied to HEAD copies in my
test tree only).

## State / next step
- DONE (HEAD 7c6dffd + mine.txt + edits/): a, b (flashbang), c, d all verified; default build boots
  to the main menu (dflt.log/png). Final fake-pad run fin.log (pickups hook, pad_fin.txt with the
  movie-skip CROSS at read 400): enemy wounded (blood drip) then killed, drop_item rifle falls
  48.9 -> 42.1 and rests, ammo boxes put on the ground, TAKE 552 swap; mission 56 s -> 166 s, no
  STOP / exception.
- Shared files are edit files (shared.txt, srep format): edits/zai01_zai.txt (zai.h),
  edits/amd01_mapdata.txt (ai_mapdata.cpp), edits/sa01_stuntype.txt (seal_ai.cpp), edits/zh01_zseal.txt
  (zseal.h: aievents edited it after me, so my hunks were taken back out). The repo's seal_env /
  seal_control / seal_squirm need zh01 + sa01 (STUN_TYPE enum) to compile; fts_main.cpp needs zai01 +
  amd01 (GetLocation(CPnt3D), GetMapEx returning char*).
- Build: `tb.sh <build> <pad> "<-D hook defines>|-" [test edits]` (HOOKSH=hookg.sh: grenade hook
  hook_shapes.cpp; HOOKSH=hooka.sh + HOOKDEF: node-action hook hook_actions.cpp, 3rd arg = targets;
  default hook.sh = hook_pickups.cpp); `tree.sh --fresh` after HEAD moves; build_default.sh <build>.
- Test camera: build/port/tools/hook_freecam.h (new, reusable): wrap CZSealBody::CheckDIShoot and call
  freecam_apply(); used in hook_pickups.cpp (-DSOCOM_HOOK_DROPCAM: the dropped weapon) and
  hook_actions.cpp (-DSOCOM_HOOK_MARKCAM=<dist>: wraps CZMarkList::AddNewMark, looks at the last mark
  along its normal 20..240 frames after it).

## Tools
Copied from boot-grenades (paths -> boot-fx2 / tree-fx2) + pickups' pb.sh / hook_pickups.cpp /
default.sh / pad_f1/f2.

## Survey
### a. OBJECT_MOTION (zanim_cmd_tick.cpp)
- zAnimObjectMotionBegin 0x1bc540 (3108, S), zAnimObjectMotionTick 0x1bb330 (4452, S). Loaders
  are stubs everywhere (anims come compiled from the disc), so the record layout is from the
  handlers only (no DWARF). Record (port names): +4 u32 flags, +8 node, +9 relative node, +10 impact
  sequence, +11 impact sound, +12 sound reference speed, +16 gravity scale, +20 drag, +24 input
  velocity scale, +29 s8 material entry count, +30 s16 offset of the entries (12 B: bits 0 has
  sound speed, 1 has elasticity, 2-9 material, 10-17 sound, 18-25 sequence; +4 speed, +8
  elasticity), +32/+34 s16 offsets of base/range (azimuth, zenith, speed, accel), +36 v0, +48 a0,
  +60 velocity, +72 acceleration, +84 direction, +96 elasticity, +100 rotation, +112 roll record
  (initial, rate, current), +114 spin / +116 scale records (initial, rate, current vectors),
  +118 random offset record (base 4 + range 4), +120 duration.
- Flags: 1 duration, 2 gravity (+drag when falling), 8 velocity from data/args, 0x10 random
  direction, 0x20 impact sound, 0x40 ground (altitude) contact, 0x80 ray contact, 0x100 spin,
  0x200 roll by displacement, 0x400 roll by velocity, 0x800 add ARG_VELOCITY, 0x1000 ARG_NORMAL
  direction, 0x2000/0x4000 ARG_VELOCITY direction (0x4000 reflect, result discarded: ELF quirk),
  0x8000 normalise, 0x10000 scale, 0x20000 args in node space.
- Callees: zAnimGetDirectionFromAzimuthZenith 0x1b7b90 (S, 208), CZAnimMain::
  GetDirectionRelativeToNode 0x1c30a0 (S, 396), CZAnimMain::InvExp 0x1c52e0 (S nonvoid, 92),
  CNode::SetScale(CPnt3D*) 0x227070 (S, 100), ftsGetAltitudeApprox 0x1f20f0 (S nonvoid, 1020:
  AI-map altitude, falls back to CWorld::GetAltitude; CAiMaps::GetLocation is unwritten and in
  zAI). Written: GetNode, GetPnt3D, Reflect (by value), BuildMTW, inverse, CMatrix::Rotate inline,
  GetIntersect/GetAltitude, GetSoundRef, ActivateSequence, CSnd::PlaySound3D(bool) (vtable +36).
- CNode vtable +52 = SetActive (the node is switched off around its own ray).

## Written (ELF addresses)
### a. OBJECT_MOTION
- zanim_cmd_tick.cpp: zAnimObjectMotionBegin 0x1bc540, zAnimObjectMotionTick 0x1bb330 (+ two
  file-local helpers for the inline material-entry search and the contact material lookup).
- zanim.h: `_zanim_cmd_motion` (record, 0x7c + sub-records) and `_zanim_motion_material` (12 B),
  names invented (no DWARF); zAnimGetDirectionFromAzimuthZenith declared.
- zanim_cmd_parse.cpp: zAnimGetDirectionFromAzimuthZenith 0x1b7b90 (linear zenith/90).
- anim_main.cpp: CZAnimMain::InvExp 0x1c52e0, GetDirectionRelativeToNode 0x1c30a0.
- node_main.cpp: CNode::SetScale(CPnt3D*) 0x227070.
- fts_main.cpp: ftsGetAltitudeApprox 0x1f20f0 (AI-map altitude; statics `di` typed CDIPoly and
  `hit` IntersectStruct); zfts.h declares it.
- Shared (edit files): zai.h inline CAiMap::GetLocation(const CPnt3D*, CAiMapLoc&) const 0x19b0f0
  (emitted from the header, no unit owns it) + GetMapEx returns char*; ai_mapdata.cpp
  CAiMap::GetMapEx 0x19f270.
- Root cause of the ammo box falling through the world after OBJECT_MOTION was written: the box
  starts ~1 unit under the snow (body origin); the world altitude probe only finds ground up to
  the lift (0.34) above the point, the ELF's AI-map altitude finds it anyway -> written.
### b. Stun (flashbang)
- zseal.h (edit zh01): `enum STUN_TYPE` 0..6 (names invented from callers: FLASHBANG, TEARGAS,
  TYPE_2, SMOKE, EXPLOSION, TASER, TASER_AFTER); the u8 duplicate declarations dropped.
  `class STUN_TYPE;` forward declarations replaced in seal_env/seal_control/seal_squirm and (edit
  sa01) seal_ai.cpp.
- seal_env.cpp: HandleStunDamage 0x293f30, HandleStunRecovery 0x294080, HandleStunFromHit 0x293e30,
  TickStun 0x293d20; HandleGrenadeExplosion's five stun calls.
- seal_control.cpp: CSealCtrl::OnStunDamage 0x287e30 (flashbang: sound groups 2/3/5 ducked to 0.65
  for 5 s; facing within cos 50 deg and 150: CHUD::Flash grey 128, 1.2/2/4 s), FLASHBANG_DOT =
  cos(50 deg) (__sinit_seal_control 0x46c960).
### c. Blood drips
- seal_env.cpp: HandleBloodDrip 0x2919a0; InitDecalHandles 0x293910 BLOOD_DRIP_DECALS part;
  UninitDatabaseHandles releases them (0x292230); m_blooddriptexhandles is a
  std::vector<CZDecalDef> (edit zh01 for the declaration).

## ELF quirks kept
- OBJECT_MOTION Begin 0x4000: the reflected velocity argument is computed and dropped (Reflect
  returns by value); the ground hit record is lifted in place; 0.35 x node height lift.
- HandleStunDamage tests type < 8 against 7 timers. HandleBloodDrip size = min + r*(max - max).
- Flashbang stun reaches bodies far outside the blast radius when unshielded (proximity hits from
  the grenade code, not changed here): teammates 250 away are stunned.

## Port deviations
- ftsGetAltitudeApprox: bilinear AI cells (CAiMap::GetBilinearAltitude 0x19a820, 2244 B, zAI) not
  written: those take the world altitude. Guard for a NULL cell (the ELF reads a NULL cell's flags).
- OBJECT_MOTION: impact sound handle NULL guard; CNode::SetActive called directly (vtable +0x34).

### d. Decals on other surfaces (no code change needed)
- d1-d4 logs (hook_actions targets computer_action / gen_fiddle_switch / alarm_action_plate, pad_d1):
  WOOD_THICK wall g883_1 2 tris per mark, generator (METAL_THIN, through-shot also marks the
  outbuilding wall) 4+2+5 tris, floor floors_di 3 tris; material -> decal set lookup and texture
  found for each. Screens: d3-72 / d4-72 (wall holes, test camera), d1-74_z (generator), d4-85 (floor).
- alarm_action_plate takes no mark: AddNewMark walks up to the nearest node with visuals but stops
  under the world; the plate is a DI-only node directly under the world (ELF behaviour).

## Results
- a: m2.log / fin.log (MOTION traces: begin flags 0x4b = duration 8 s, gravity, velocity, ground
  contact; e 0.25; rifle bounces once and rests; box on the AI-map ground), fin-59(_z).png rifle
  mid-fall, m2-60.png TAKE 552. Shell ejection: no OBJECT_MOTION command ran while firing the M4A1
  SD (only drop_item uses it in these runs).
- b: f1/f4.log: Mark141 detonation stuns exposed bodies (STUN type 0 amount 2), player facing the
  blast 132 away: CHUD::Flash 0.69 (a light grey veil, f4-75.png); recovery traces "STUN: .. recovered".
- c: c2.log / fin.log: wounded OutPatrol4 drips every 0..3 s (3 BLOOD_DRIP_DECALS loaded), c2-85_z.png.

## Not written / next
- CSealCtrlAi::OnStunDamage 0x269c00 (1176 B, seal_ai.cpp: aievents) and CAiSStunResponse Tick/
  OnSignal (seal_airesponse.cpp): enemies get the stun values but no stunned behaviour yet.
- HandleSmokeAndGas (smoke / tear gas volumes -> HandleStunFromHit); smoke / tear gas grenades are
  not in the m8 default kit (C4, Mark141, M67), not tested.
- CAiMap::GetBilinearAltitude 0x19a820 (bilinear AI cells fall back to the world altitude).
- OBJECT_MOTION_SI_SCRIPT, CZAnimFromToAcc, the loaders (anims come compiled).
- Dead bodies still drip twice after death (health 0 < 1; ELF has no alive test in HandleBloodDrip).
