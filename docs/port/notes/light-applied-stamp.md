# Local lights added several times: CLight::m_appliedToNode (2026-11-25)

Reported by the user from play: near a bright light the characters showed purple and cyan
patches (the spot: 1430 118 2550 in m8, the hut with the hanging lamp).

## Cause

`BuildNodeLocalLightList` (0x243c10) walks the grid cells under a node and adds each cell's
lights. A light whose range covers several cells is in several lists, so the function stamps each
light it meets with its call counter (`AppliedToNodeNum`, 0x474eec) and skips a light already
carrying the current stamp:

- the ELF loads and stores the whole word: `lw v0,228(a0)` at 0x243fdc, `sw v1,228(a0)` at
  0x243fe8;
- DWARF: `CLight` +0xe4 `m_appliedToNode`, `uint`.

The port declared the member `bool`. The stored stamp was then always `true`, the comparison with
the counter never held after the first call, and a light was added once per cell that lists it,
up to the ten slots. The VU1 code adds every slot's colour and converts the result with `ftoi0`
and no upper clamp (`vuNextLocalLightVertex`, `vuGatherFixKick`), so a channel pushed past 255
wraps around: the coloured patches.

It showed only after the region-mask fix of the zNode audit (dc86cb6d), which made the local
lights reach most nodes in the first place.

## Fix

`m_appliedToNode` is `u32` (`src/gamez/zNode/node_light.h`). The layout does not change (the
`bool` was followed by three bytes of padding).

## Checks

- A diagnostic count in the scripted mission run, before the fix (cut off at about 195 s): of
  93,786 lit draws, 50,251 carried at least one light more than once (215,924 repeats; the hut's
  own nodes filled all ten slots with repeats). The count was not repeated after the fix.
- Screenshots of the reported spot from two builds that differ only in this member's type, the
  player put there by the new test hook `port/test-hooks/lightspot` and the game started with
  `--nodie --nosee`: `build/port/screenshots/2026-11-25_light-repeat-1430-118-2550-before.png`
  shows the patches on the player and a team-mate, `-after.png` shows both lit plainly.

## Tools added on the way

- `port/tools/dev/pcsx2-boot.ps1 -GameArgs` and `port/tools/dev/socom-run.ps1 -GameArgs` pass the
  game's own command line through PCSX2's `-gameargs` (`process_arguments` then sees it: `-f`
  shows the status line with the player's position).
- `port/test-hooks/lightspot`: the player at a given position once the mission cameras are over.

## The same kind of mistake elsewhere

A sweep of the 384 classes that have DWARF (3,351 members): every member the port declares with a
one-byte type against DWARF's wider integer or pointer type. Three more, none changing behaviour,
corrected in the commit after the fix:

- `_zanim_sound::stop_on_exit` (+0x2): DWARF `sshort`, the port had `bool`; it only holds 0 or 1.
- `_zvid_public::showTextureBuffer` (+0x4) and `showTextureBufferFormat` (+0x8): DWARF `sint`,
  the port had `bool`; nothing reads them. With `s32` the members after them sit at DWARF's
  offsets (`frameNumber` +0x10). The first member is `wireFrameFlag` in DWARF (was
  `wideFrameFlag`).
