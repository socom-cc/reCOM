# Three leads the correctness audit left open (2026-11-20, socom-port-audit-leads)

Evidence work on the audit's open leads ([AUDIT_PLAN.md](../AUDIT_PLAN.md)), HEAD abb909ac. No game
source changed. Scratch: `build/port/boot-audit-leads/` (the hook `hook_leads.cpp` with
`port/test-hooks/state/hook_state.cpp`, the pad script, the disc readers' dumps and the small
scanners named below; disc data stays untracked).

## Lead 1: the CMission constructor's grade (audit-medium-fts #21, 0x1f94a0)

Verdict: **A** (was B). The TIMER part is masked on m8, but the see-farther part of the same fix
changes every scope and binocular view of the mission.

TIMER (masked):

- No reader on the disc spells a TIMER command: the text readers (`RUN/READERC.ZAR`, the UI reader
  archives, m8's `READERM.ZAR`) hold no `TIMER` string. The mission's anims are compiled
  (`RUN/SP/M8/MZANIM.ZAR`, `RUN/CZANIM.ZAR`), where a command is its data type.
- TIMER's data type is 0x002b: the run's dump of the command table (lt1) reads
  `set 0 '' [43] TIMER type 002b` (between MESSAGE 0x2a and FIRE_WEAPON 0x2c, the order of
  `zanim_cmd_parse.cpp`'s AddCmd calls).
- A histogram of every command header of every sequence of both archives has no 0x002b (m8: 63
  types from 0x0001 to 0x021e; common: 28 types). The only other HUD-timer command,
  HUD_START_DEFUSE_TIMER (0x003e), is absent too.
- Run lt1 (73 s of play after the briefing cameras): `TIMER ticks 0`; the win / loss timer runs
  -1.02 at the first frame to -73.17 at play+4200 fields (increment -1), `gametime` negative
  throughout, so CHUD::Tick (0x3b9ba4) clears the clock text in single player either way. Before
  the fix the increment was 0 and the timer stayed at CCoreState::Init's -1: the same empty text.
- The satchel fuse does not use the win / loss timer (it reads m_satcheltimer, which
  CMission::Read sets to 10 before its findreal); the MP bomb that does is not in the m8 kit.
- The constructor's save-module registration (theMemCard.m_game, 0x1f94bc) only matters when a
  game is saved; the demo's screens start no memory-card save.

See-farther (visible):

- The constructor stores m_seefarther_binocs 200 and m_seefarther_weapzoom 300 (0x1f9720 /
  0x1f9728); CMission::Read (0x1f6fc0) overwrites them only when mission.rdr has
  SEEFARTHER_BINOCS / SEEFARTHER_WEAPZOOM, and m8's mission.rdr has neither (dump of
  `READERM.ZAR /mission.rdr`). Before the fix both were 0 (the global's zeroed storage).
- CameraZoom::HandleNewZoom (0x31fee0) calls SeeFarther (0x3202c0) with them on a binocular or
  weapon zoom: fog near and far, mid and far clip move out by that distance.
- Run lt1, scope (zoom state 4, the M4A1 SD's 2.5x after two UP presses): `camera mid 1072 far
  1079 fog 1..1042` in first person, then `mid 1374 far 1382 fog 301..1343` in the scope. With the
  old 0 the scope view keeps fog from 1 and the far plane where it was.
- Screenshot pair (scope 2.5x, the same test-camera view from the start point toward the town,
  play+1700 fields on): `build/port/screenshots/2026-11-20_cmission-seefarther-scope-before.png`
  (run lt3: the current tree with the three members put back to 0 by the hook at the first
  mission frame, `fog 1..1053 far 1091`) and `...-after.png` (run lt2b, `fog 301..1353 far 1391`).
  Before, the shed's far side, the trees and the slope behind are washed toward the fog colour
  (mean grey of the trees 56 against 47, of the slope 58 against 47); after, they keep their
  contrast.

Counts in [audit-medium-fts.md](audit-medium-fts.md) changed to A 1, B 2, C 2.

## Lead 2: persistent valves, 30 (not 36)

The right number is **30**, and the port holds 30.

- The ELF's CValve::Parse (0x2f6180) reads each "valves" entry's `type` word with strcasecmp:
  PERM 1 (0x2f6240 / 0x2f6254), TEMP 2 (0x2f6260 / 0x2f6274), PERSIST 3 (0x2f6280 / 0x2f6290);
  no or another word keeps the caller's type (the delay slot `move s4,s8` at 0x2f6234). A new
  valve is acquired with that type and appended (0x2f630c); an existing one becomes PERM unless
  persistent, and PERSIST when the word says so (0x2f6378..0x2f63b8). The port's body (valve_list.cpp) is that.
- The only CValve::Open is CMission::Init's `Open("global_valves.rdr", 1)` (0x1f91ac..0x1f91b4).
  Its file (`RUN/READERC.ZAR /global_valves.rdr`) has 88 entries: 30 with `type PERSIST`, 58
  without a type (so PERM), no name twice. With lodLevel (zVid_Init, PERM) that is the 89 valves,
  59 PERM and 30 PERSIST, of the audit's run mrd1.
- Saving writes only type 3 (CValveSaveManager::Serialize 0x2f73a0), so a config save holds 30.
- Other persistent creators in the ELF (every Create / Acquire call with its type register,
  scanned in the reference disassembly): CMission::PreOpen's "Valves" block of mission.rdr (a
  PERSIST tag, 0x1f89b0..0x1f89c0) and CValveSaveManager::UnSerialize (type 3, 0x2f734c, the names of a
  save). m8's mission.rdr "Valves" has 63 entries without PERM / PERSIST tags (TEMP;
  CurrentMission already exists as PERM and stays so). m8's `valves.rdr` (84 entries, no types)
  is not opened by anything (no `valves.rdr` reference besides global_valves.rdr's, and only
  Parse reads a "valves" tag).
- Run lt1, m8's first mission frame: `348 listed, type0 0 perm 74 temp 244 persist 30`, the 30
  names those of global_valves.rdr.
- Where 36 came from: only the verdict row of #35 in
  [audit-medium-rest-d.md](audit-medium-rest-d.md) says 36; the same note's run section, the
  scratch notes and the commit message of that list (9f3a07d7) say 30, and no reader or code path
  gives 36. A slip in the row text, corrected there.

## Lead 3: before / after screenshots of the zNode lighting fixes (dc86cb6d)

Both fixes show, in the same place: the dredge's office (the "source" lamps at 1753 150 1429 and
1771 141 1488, diffuse yellow, range 35..42). Test camera views A (table02, map01, binder01) from
play+120 fields and B (computer, chair01, table01) from play+720, the same frame in every run.

- Census after LoadWorld: the current tree has 263 world nodes with m_dynamic_light and all 31
  lights with region mask 0; with both fixes reverted 75 nodes and every light mask 1, so
  RenderNode (zrndr_pipe.cpp) skips each light for the 1,174 nodes with a nonzero mask.
- `build/port/screenshots/2026-11-20_znode-lighting-dredge-map-before.png` / `-after.png` and
  `2026-11-20_znode-lighting-dredge-laptop-before.png` / `-after.png` (before = both hunks of
  dc86cb6d reverted in a test tree, run lt4; after = the current tree, run lt2): before, the office
  is lit only by the global light, dark and grey; after, the lamps light the floor, tables, map
  and chair warm yellow (mean grey: floor 33 -> 104 in A, 43 -> 83 in B; map 21 -> 68; chair
  39 -> 71).
- Which fix does it: with only InheritRegionMasks reverted (run lt5) the frames equal the full
  "before" (same means, mean pixel difference 0.01 in A); with only SetDynamicLight reverted
  (run lt6) the lamp light is there. So the office's light is the region-mask fix (A confirmed).
- SetDynamicLight alone: lt6 against lt2 differs only on the laptop (2,714 pixels in B, none
  elsewhere beyond the window title): without the fix the lid and bezel (the computer's child
  visuals, flagged only with the fix: 263 against 75 nodes) are drawn unlit, bright white; with
  it they take the lamp light and are dark. Pair:
  `2026-11-20_znode-lighting-dynlight-only-laptop-before.png` / `-after.png`. Visible but small:
  A stands (it changes what the player sees), the weakest of the three.

## Runs

All from the isolated tree of HEAD abb909ac (`tree-audit-leads`), fake pad, the hook and
`hook_state.cpp` (`-DSOCOM_HOOK_MISSIONS=1 -DSOCOM_HOOK_PLAY_AT=999999`), pad script
`play+1500:UP,play+1620:UP` (first person, then the scope); the "before" trees are `tree.sh`
copies of HEAD with the scratch edits `edits/znode-*.txt` applied in the tree only. Every run:
focus kept, no memory card, no exception; play anchor at 107.7..109.2 s (the views are timed
from it, so the frames match).

| run | build | what it showed |
|---|---|---|
| lt1 | current tree, no camera | command table (TIMER 0x002b), 0 TIMER ticks, 30 persistent valves, light / dynamic-light census, scope planes |
| lt2 | current tree, views A / B / C (low) | the "after" of lead 3 |
| lt2b | current tree, view C raised | the "after" of lead 1 (scope) |
| lt3 | current tree, `-DLEADS_OLDCTOR` | the "before" of lead 1 |
| lt4 | both zNode hunks reverted | the "before" of lead 3 |
| lt5 | InheritRegionMasks reverted only | as dark as lt4 |
| lt6 | SetDynamicLight reverted only | as lt2 except the laptop |

Smoke: no game source changed; the notes only (`audit docs --strict`, `audit independence
--strict`).
