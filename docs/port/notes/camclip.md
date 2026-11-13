# boot-camclip notes (2026-11-07, socom-port-camclip)

Scratch for the third-person camera's wall clipping (CAppCamera::ClipCameraChord). Untracked.

## Written (from the asm)
- ClipCameraChord 0x1ebbb0 (2480 B), GetNearestIntersectCamPoint 0x1ec580 (368 B): camera.cpp.
- dilr0..3: DiIntersect(16) (__sinit_camera.cpp); tetherPos (0, 8, 40) (no code reads it).
- CPnt3D::ToRightXZ 0x222e00 (was an empty stub); CPnt3D::Normalize() 0x222d40 returns the length
  (was void; ClipCameraChord uses it).

## ClipCameraChord (asm walk, asm_clip.txt)
a1 start (APTeatherCam: the pivot = eye + dist along the view line; death cam: seal + 10 up),
a2 end, a3 out (both the eye in APTeatherCam). f20 = |start-end| + 3, end pushed to start - unit*f20.
Seal node (and m_carry +0xda8) SetActive(false) around everything (vtable +0x34 = SetActive).
peekCur == 0 -> SetCameraCollideFlagRequired(1) then (0) (quirk; net: flag false).
camera_tether_intersects_something = 0; hit = GetNearestIntersectCamPoint(m_world->GetIntersects(start,end), start).
m_short_tether_timer (+0x2c, ctor -1) -= dT while > 0.
save_short_tether_length: len3 <= save -> save = len3; else if timer <= 0 || save < 6 || intersects ->
save += 0.03 (0x3cf5c28f) * (len3 - save); else hold.
hit: d = unit(hit - start), l = max(|hit-start| - 3, 3), save = min(l, save), out = start + d*min; timer 1.5.
no hit: end = start - unit*save; out = end.
Probes from out (type 2, one GetIntersectBatch of 4): right = ToRightXZ(dir) XZ-normalised *3:
dilr0 out+right, dilr1 out-right, dilr2 out+3y, dilr3 out-3y. Both sides hit -> out = midpoint;
one -> out.xz += hit - tip; up+down -> out.y = mid; up -> hit.y - 3; down -> hit.y + 3; each timer 1.5.
Last: |out - start| < 3 -> out = start + unit*3. Restore SetActive.

## Tools (this folder)
Copied from boot-collide (paths fixed): dis.sh/disx.py/dx.ps1, sym.py, xref.py, dw.py, mem.py,
lay.py/laycheck.sh, fences.py, stubchk.py, squash.py, fixnl.py, ccm.sh, fake.sh, hook.sh,
hook_wall.cpp (+ SOCOM_HOOK_BACK: face away from the wall; HOOK_BACK=1 hook.sh ...). New:
- tree.sh [--fresh|--head]: ~/.cache/socom/tree-camclip = HEAD + mine.txt files; --head:
  tree-camclip-head = plain HEAD (the "before" build). fake.sh/hook.sh default to tree-camclip.
- build2.sh <build> <tree>: fake.sh + HOOK_BACK hook.sh with the camera pad script.
- ga.sh <patternfile> [n]: egrep of the cached WSL /tmp/socom_full.asm (pattern in a file; run
  with MSYS_NO_PATHCONV=1 from Git Bash).

## Result
- a1.log (hook build, back to the alaska4d_depot wall, gap 10): first frame clipped (`CAM: clip
  chord/side/vert 100: ... 8.3 from the pivot, chord hit alaska4d_depot`): the camera sits between
  the player and the wall. HEAD (b1.log, same hook/pad) shows the house's inside instead.
  Turning along the wall: chord + side probe clips, then clear; walking away the tether eases out.
- a2.log: UP (first person) with the back to the wall, DOWN back to third person: clipped on the
  first third-person frame (state stays 100, no trace change); side-on toggles fine.
- d1.log: default build (HEAD + my files, ~/.cache/socom/camclip-default: library 0 errors, link
  undefined 0 multiple 0) boots to the main menu.
- Screenshots: build/port/screenshots/09-camera-clipping/2026-11-07_1256_m8-*.png
  (before = b1-51, after = a1-51, a1-59, a2-60, a2-62, a1-61).
- Pads: a1 `...,185:CROSS,420:LY=255+45,500:RX=255+30,560:UP,610:DOWN,660:RX=0+60,740:LY=0+60`;
  a2 `...,185:CROSS,430:UP,490:DOWN,540:RX=255+20,600:UP,650:DOWN,700:LY=255+40,780:RX=0+20`;
  hook `HOOK_BACK=1 hook.sh <b> <pad> 10 800 1680 2800 depot`. Log time and screenshot time drift
  ~1-2 s between runs (a2 ran next to another worker's PCSX2: world at 56.7 s instead of 48 s).
- LY=255 (stick back) with the back at the wall did not move the player (not investigated).

## Not written / next
- APLookAt 0x1ea200 (532 B, also calls ClipCameraChord): cam_mode_apLook (3) is never stored in
  the ELF (only the ctor and FTSTick write +0x89), so unreachable in this build; still empty.
- Death camera: GetDeadCamPoints 0x1e8fc0 (1620 B, nonvoid stub without return) and
  UpdateDeathCamState 0x1e9620 (2968 B) unwritten; GetTetherCamPoints calls the former once the
  player is dead (STOP through -fsanitize=return).
- Characters have no DIs (AddDIPolys / SetDIBBox unwritten), so the camera passes through other
  characters (ELF: only the seal and its m_carry are switched off for the chord).
