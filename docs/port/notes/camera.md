# boot-camera notes (2026-11-07, socom-port-camera)

Scratch for the first-person / zoom camera and aim pitch. Untracked.

## Result
Pad UP (zoom in) enters first person, pad DOWN leaves it; twice in a row, no freeze (f2/f3.log).
The right stick pitches the aim (stick up = look up; -70..60 deg, prone -60..25) and both cameras
follow. Screenshots: build/port/screenshots/2026-11-07_0156_m8-{third-person-looking-up,first-person,
third-person-after-toggle}.png (= f4-58/66/74.png: HEAD 910b3b8 with the HUD + my edits, f4.log).
Default build (working tree = 910b3b8 + my edits): ~/.cache/socom/boot-camera-default, exit 0,
undefined 0, multiple 0. Also wrote CZKit::GetCurItem 0x2abd40 (the HUD inlines it as hud_curitem).

## Freeze (r1.log, HEAD + fake pad)
controller.rdr "Default" has no AimMode button; first person is the zoom: CSealCtrl::PreTick pad UP ->
IncrZoomState, DOWN -> DecrZoomState (FireMode is L3 = CZKit::CycleFireMode). No STOP: UP hid the body
(opacity 0; HandleNewZoom stub, so the camera stayed in third person), DOWN showed it and the next frame
logged `sceGsSyncPath: path stuck (D1 10000145 D2 03400045 VIF1 0100008b GIF 00000e04)` (GIF APATH 3
waiting for image data, D2 done with a REFE tag that is not ours). Cause: the hidden body's textures
went to the alpha buffer (SaveDelayedNode, opacity < 0.99); when the list emptied again Load returned
early with m_chainp NULL (SetDynTexList) but m_pktbuf still sized, and InterruptFromVIF1 (ELF too: it
tests m_pktbuf size) kicked D2 at TADR 0. The ELF never empties that buffer: decal textures
(CZMarkList::Init -> ReadBloodDecals/ReadDecalEntry -> CWorld::AddTextureAssetDecals) are always there;
in the port CZMarkList is unwritten. Port guard added in zrndr_pipe.cpp (also needed after the fix:
the zoom-in frame still renders the body at opacity 0 before FP hides the node).

## Grey screen (f1.log)
With TickAimPitch written the camera is pitched (init -9 deg) and nothing drew (FOV-culled): port
compat sceVu0InversMatrix summed the translation along the transposed rows instead of columns (ELF
0x152360 vmulax/vmadday/vmaddz); a level camera's WorldToView 3x3 is symmetric so it never showed.

## Tools (this folder)
Copied from boot-control (paths fixed). tree.sh [--fresh]: ~/.cache/socom/tree-camera = HEAD src/ port/
+ the files in mine.txt (incremental). fake.sh / ccm.sh default to that tree. edits/e0*.txt: ed.py
edit files used. Session scratchpad held the disc ZAR and full.asm (ga.py regex search with function).

## Not written / next
- CheckDIShoot 0x29a850 (2.8 KB: GetIntersects, GetCurItem, GetMaxRange, GetCharacterHit,
  SealGetIntersect, SetAimPointW -> UpdateAimDir, DrawAutoReticle, GetAP): no aim point, so the
  transitions keep the aim pitch (port guard on m_aim_point_valid) and the body never aims.
- Body aim pitch: PitchAnim 0x29c620 runs only with the fire overlay up (a weapon; the kit has none).
  Head look (LookTick, ApplyLookAnim, GetFractionalRotations) unwritten; for the player the ELF's head
  look only follows SetLookDir (ctor / AI scan), not the aim pitch.
- CHUD::ZoomIn/ZoomOut (HUD worker), CZKit::SetCurReticule path is written.
- Vu0MatrixInverseWithUniformScale (zmath_matrix.cpp, provisional general 4x4 inverse) used by the
  transitions: unverified against 0x221f90 (unreachable until CheckDIShoot sets an aim point).
