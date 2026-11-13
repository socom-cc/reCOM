# boot-weapons (port P21: weapons)

Scratch for the weapons worker. Nothing here is tracked. Changed files: `mine.txt`.
Function list with addresses: `written_addr.txt` (312 written or fixed). Edit batches: `edits/w01..w23`
(`=== <mangled>` blocks applied by `rep.py`; one-line bodies were replaced by hand).

## Tools here

- `sym.py <regex>` / `sym.py -s <addr>` (string at address), `xref.py <addr>` (callers),
  `ctree.py <addr> <depth>` (call tree, W/S = written/stub), `fences.py <regex>` (fence status),
  `dx.ps1 <addr>` (objdump of one ELF function with string annotations).
- `fake.sh <build> "<pad script>"` configures a scratch build with `SOCOM_PORT_FAKE_PAD` and links.
- `ccm.sh <unit...>` compiles single units (quick check).
- `laytool/` copies of boot-player's `lay.py` / `laycheck.sh` writing here (types.pkl read from
  boot-player). `unscratch.py` strips `#ifdef SOCOM_PORT` blocks whose first line says "weapon test".
- Pad scripts: `pad_f10.txt` (final report run), `pad_f12.txt` (+ body-hidden test).

## Timing (fake pad)

~30 pad reads/s; read 520 is about 57.5 s with the standard menu path (60:CROSS ... 185:CROSS).
Buttons hold 3 reads, so a held trigger is an entry every 3 reads. Player ticks 60/s from ~52 s.

## Results (f13 = clean build + pad_f10)

- Load: `WEP: zweapon.zar: 30 ammo, 59 weapons`; every seal gets its kit; player 5 items,
  slot 0 M4A1 SD (m4Acarbine) under rhand, P9S under rthigh.
- L3 cycles single -> burst -> auto; R1 fires (auto drains 30 -> 15), R3 reloads (partial mag kept,
  "2 MAGS"); empty mag reloads by itself; L2 draws the pistol (callback 0x2987b0 moves it to the
  hand), L1 back to the rifle (0x2986e0 back to the thigh as gear).
- Hits: one-frame direct fire, world DI intersections, material SNOW resolved, hit anim found
  (22 of 37 materials have bullet_hit_<material>).
- PitchAnim: aiming up (RY=30) raises the fire point 51 -> 57 and the shot direction pitches up.
- HUD: weapon name, "%d/%d", "%d MAGS", fire mode bitmap follow the kit (SetupAmmoCount,
  SetupFiremode). The fire mode name text is never drawn (ELF: m_firemodename is in no phase).
- The player's rifle is hidden by his own body from the chase camera (proved by hiding the body
  mesh in a test build: rifle in hand, pistol on thigh - screenshot `*_rifle-in-hand-body-hidden`).

## Engine bugs fixed (port)

- `zrdr_findSTRING` (0x23d300) took the array header's 16-bit `length` field instead of the
  element count `array[0].integer` (lw 4(array)), so every `TAG ("value")` string lookup failed:
  materials.rdr SOILS gave only the 2 defaults (all hits UNKNOWN, no hit anims).
- `CMission::ZAnimLoad` (0x1f7730) and `CZAnimMain::LoadZAR(const char*, const char*)` (0x1bfe90)
  were empty: no mission/common anim sets (fire/hit anims NULL). Now mzanim/zanim + czanim.zar.
- `CPnt3D::Normalize(CPnt3D*) const` (0x222cb0) had no return (STOP on fire): returns length.

## Not written / next

- Particle system: `zAnimParticleSourceTick` is a `return true` stub and Particle::Source/Instance/
  BufferElement draw are stubs, so muzzle flash and impact anims activate but draw nothing.
- `CWeaponSel` (R2 Inventory menu): all 22 functions unwritten (0x3d0ac0..0x3d4f80, ~19 KB).
- Decals: CreateMarkList returns false (CZMarkList, decal sets not loaded).
- Grenades/C4/claymore/satchel throw and placement, HandleBounce, HandleShotgunImpact (bool
  stubs), AI events (AIE_WEPFIRE/WEPHIT), network fire messages. Character hits need collision
  shapes (later worker). Sounds are called into the 989snd shim.
- Rifle slung as gear sits at the spine (pos -1,0,0) inside the torso; gear offsets
  (m_rifle_as_gear) not checked against the ELF - may be right (SOCOM shows no slung rifle?).
