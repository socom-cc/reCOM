# Float constants: the port's words against the reference ELF's

**Compiler finding.** The pinned GCC (15.2, `mips64r5900el-ps2-elf`, hard float) converts decimal
float literals to `float` **rounding toward zero**, and folds float expressions and double-to-float
conversions the same way; Metrowerks, which built the reference ELF, rounds to nearest. Any inexact
float literal can therefore compile one ulp below the ELF's word, however many digits it has
(`0.3f` gives 0x3e999999, `.699999988f` gives 0x3f333332, `%.9g` output included).

**Rule.** An inexact float constant is written so that both roundings give the ELF's word, with the
word in a comment, and is read back from the compiled object; a literal that "should" be right is not
proof. Spelling used here: the nine-significant-digit decimal rounded **up** from the word's exact
value (`0.300000012f /* 0x3e99999a */`): it lies in `[word, word + ulp/2)`, so truncation and
round-to-nearest both give the word. A C99 hex float (`0x1.333334p-2f`) is exact too and is the
fallback, but it is not a spelling the 2002 Metrowerks C++ front end can be assumed to accept; the
decimal serves both compilers, which the source rule asks for (GCC-only spellings only where one
spelling cannot serve both). Every emitted site below was read back from the port build: none needed
the fallback. The ELF's own words are the standard, including ones its compiler rounded or folded.

Work item: float (and double) constants in `src/` whose value, as the port's compiler builds it, is
a near neighbour of the word the reference ELF uses in the same function (lead from
[audit-sample.md](audit-sample.md): `cz.py` printed seven digits). Result: 852 literal sites in 100
files now give the ELF's word in the port build; every one the compiler emits was read back from the
build (10 are not emitted at all: dead code, unused or folded statics).

## The root cause: GCC r5900 rounds toward zero

The seven-digit annotation was only half of it. The pinned compiler (GCC 15.2,
`mips64r5900el-ps2-elf`, hard float) gives `SFmode` the R5900's own format (no infinities, no
denormals, **round toward zero**), so every decimal-to-float conversion in the source, every
double-to-float conversion and every constant fold is truncated. Metrowerks, which built the ELF,
rounds to nearest. A probe (`float a = 0.3f;` and friends) shows it directly:

| source | GCC r5900 | Metrowerks / ELF |
|---|---|---|
| `0.3f` | 0x3e999999 | 0x3e99999a |
| `0.1f` | 0x3dcccccc | 0x3dcccccd |
| `0.8f` | 0x3f4ccccc | 0x3f4ccccd |
| `3.14159265358979f` | 0x40490fda | 0x40490fdb |
| `1.0f / 3.0f` (folded) | 0x3eaaaaaa | 0x3eaaaaab |
| `1.0f / 255.0f` (folded) | 0x3b808080 | 0x3b808081 |

So about half of all inexact literals were one ulp low in the port, whatever their digit count.
Nine digits are not enough either: `%.9g` rounds to nearest, and when the nine-digit decimal lies
below the exact value GCC truncates it to the word below (`9.99999997e-07f` gives 0x358637bc, not
0x358637bd). `cz.py`'s nine-digit output is therefore round-trip safe for Metrowerks but not
always for this GCC.

The spelling used here is the nine-significant-digit decimal **rounded up** from the word's exact
value (trailing zeros dropped): it lies in `[word, word + ulp/2)`, so truncation and round-to-nearest
both give the word, and one spelling serves both compilers. The hex word follows in a comment:
`0.300000012f /* 0x3e99999a */`. The R5900's run-time arithmetic also truncates, so a fold GCC
does at compile time usually equals what the ELF computes at run time; only Metrowerks' own
compile-time folds (round to nearest) had to be written out as literals.

## Method

Scratch tools in `build/port/boot-floatconst/` (ignored): `gbuild.sh` (a `-g` analysis build of the
isolated tree: same flags plus line info), `fcscan.py` (the scan), `fcfix.py` (the rewrite and its
log `changes.tsv`), `verify2.py` and `table.py` (read-back), `remain.py` (every literal whose two
roundings differ), `spell.py` (the spelling of a word), `hook_dyn.cpp` (test hook below).

1. **ELF side.** Per reference function, every constant word it uses: `lui`/`ori` pairs and lone
   `lui` immediates, `lwc1`/`lw` from `.sdata` (through `$gp`) and from `.rodata`/`.data`
   (`lui` + offset), and every word of the small data objects (up to 1 KB) the function builds an
   address of (tables, function statics). Data fences use the words of their data object.
2. **Source side.** Every literal token in `src/` (comments and strings blanked) inside a skeleton
   fence's region (a fence runs to the next fence, so helpers placed after a fence comment count),
   with both words computed exactly (toward zero for GCC, nearest for Metrowerks; a literal without
   `f` goes through double first). Rules: (A) the two roundings differ and the function uses the
   Metrowerks word: target = that word; (B) the GCC word is not used but a word within 16 ulps is,
   and only one: target = that word (the literal itself was imprecise, e.g. `0.01745329f`);
   (U) neither: changed only when the port side (step 3) confirms the word at that line.
3. **Port side.** Every float constant load of the `-g` build (`-g` moves code slightly, 1.3 % more
   `.text`, but not the constants; `lwc1`/`ld`/`lq` from `.rodata`, `lui`/`ori`, switch tables), attributed through
   `addr2line -i` to every frame of its inline chain, compared with the ELF words of those frames'
   functions. This finds what the source scan cannot: named constants (`RAD_TO_DEG`, class
   statics), defaults in headers and inline constructors, and GCC folds (`1.0f / 30.0f`).
4. **Rewrite**, then rebuild and rescan until both sides are empty except the kept cases below; the
   remaining ~60 sites were judged one by one against the disassembly (`z.sh`, `sym.py`).
5. **Read-back** from the final tree's build: the word at the line (547 sites), in the function
   (262), in the unit's assembly (28: statics, tables), from the run (3), or not emitted (10).

A function using both neighbours (HandleEvent: `0.2f` is 0x3e4ccccc at two sites and 0x3e4ccccd at a
third) was not decided by rule: the ELF's sites were matched to the source by hand.

## What changed

852 sites: 833 one ulp up (the truncation), 8 two ulps up, 1 four up (`1.570796f` in
`CAiSPursue::Tick` is pi/2 = 0x3fc90fdb), 8 one down, 1 three down (`1.047198f` there is pi/3 =
0x3f860a92), and one value fix (below). By kind:

- Plain literals rounded the other way by GCC (rule A): the bulk (`0.8f`, `0.99f`, `0.1f`, `0.2f`,
  `0.3f`, ...), in code, data initialisers and function statics.
- Imprecise literals (rule B and manual): `0.01745329f` / `0.017453292f` (0x3c8efa35 = pi/180),
  `0.2702703f` (10/37 is 0x3e8a60dd), `0.03333334f`, `0.95993114f` (55 degrees is 0x3f75be0b),
  `0.3490658f`, `1.3962634f`, `107.3296f`, `11.46`, `98.1`, `0.24`/`0.64` (SniperTick), the three
  `CAiSPursue::Tick` scan angles, `0.7f` where the ELF has 0x3f333334, the CDynGrenade copies in
  `seal_kit.cpp` / `seal_control.cpp` (`cos_45` 0x3f3504f7, elevation offset 0x3c8efa35, max
  elevation 0x3f75be0b).
- Named constants: `RAD_TO_DEG` in `zmath.h` (0x3c8efa35 at all 23 uses, CharacterDynamics::Load);
  `CZSealBody::turnV` 0x3ccccccd and `seal_foot_bone` 0x3f8b851f (`seal.cpp`, ELF data 0x450d20 /
  0x450d30); `CSealCtrlAi::aiAccuracyAngle` 0x3e860a92; statics written as 17-digit decimals that fall
  below the exact value (`PRONE_THROW_FRAC = 0.6600000262260437f` truncates to the word below).
- Defaults in headers: `throw_params` (`zchar.h`: 0.15, 0.6, 0.3), `m_maxSlopeCos`,
  `CRemoteCtrl` fade (`zinput.h`), the particle exp series (`zparticle.h`), `_fPressedTime`
  (`ztwod.h`).
- Metrowerks folds GCC refolds toward zero, now literals with the expression in the comment:
  `1.0f / 30.0f` (zanim_cmd_parse.cpp twice, CPad::Flush), `1.0f / 255.0f` (GetFogVisibility,
  ColConvTo3D's `scale`), `1.0f / 127.5f` (CPad::Tick, four sticks), the death camera's
  `fade_out + 0.5f * faded` (0x3e99999a stored by UpdateDeathCamState).
- Widened floats: `static double hacknumMin = 0.3f` (the ELF's double is 0x3fd3333340000000) and
  `startAnimDotThreshold = (double)-0.8f` (0xbfe99999a0000000).
- **One value fix, not a rounding:** `CSealCtrl::Tick`'s `epsilon` (@2802, `.sdata` 0x475008) was a
  guessed `0.001f` ("value not checked"); the ELF's word is 0x3d4ccccd, 0.05. The look now counts a
  turn throttle up to 0.05 as still (AIL_TASK) instead of up to 0.001.

## Kept as they are

- `PI = 3.141593f` (`zmath.h`): GCC truncates it to 0x40490fdb, the ELF's word at its one use
  (TickCameraWiggle 0x1ea710, which multiplies 2.0f by PI at run time; GCC folds to 0x40c90fdb, the
  same product). Metrowerks would read 0x40490fdc. Comment added, literal untouched (rule: do not
  touch a literal that already gives the ELF's word in the port). Several other literals are in the
  same position (right only under truncation, the ELF itself holding the lower word): `11.487f`
  (0x4137cac0, seal_env / seal_anim / seal_body), `15.3f` (0x4174cccc, PopBlend), `0.72f`
  (0x3f3851eb, hud_scorepopup). `remain.py` lists them.
- `0.2f` in `ev_take(this, ev, 0.3f + 0.2f * ev_rand01(), ...)` (HandleEvent, two sites): the ELF
  has 0x3e4ccccc there, which is Metrowerks' fold of `0.5f - 0.3f`; GCC's `0.2f` gives the same
  word.
- `CAiSGrenade::Tick`: GCC specialises the `skill == 0` path and folds `1.8f + 0 - 1.0f` and
  `2.9000001f - 2.1f`; both equal the ELF's run-time results (exact subtractions). `minTimeForSafe
  SealReturn` and the other sums with `tb_timeToThrow` are GCC folds of statics the ELF adds at run
  time (truncating either way).
- `seal.cpp` 794: `0xbfffffff` is a bit mask, not a float.
- `57.29578f` in a `SOCOM_PORT` trace (port-only).
- `recoil_table` in `seal_body.cpp` (175 tokens): the values are products of ELF constants evaluated
  in Python doubles by the generator (`recoil_gen.py`), not ELF words; they are neither in the ELF nor
  near its words. Making them faithful means emitting the ELF's run-time products (in its order and
  rounding): left as a lead.
- **Lead, not a rounding:** CharacterDynamics' defaults in `zchar.h` beyond `throw_params` differ
  from the ELF's inlined constructor (`__sinit_seal_dyn.cpp` 0x46ca00) by far more than ulps:
  `m_maxAimPitch = 1.483f` against 0x3fbde44e (85 degrees), `0.349f` against 0x3eb2b8c2 (20),
  `0.785f` against 0x3f490fdb, `1.55f` against 0x3fc6d3f2 (89), `0.139f` against 0x3e0efa35 (8),
  `-0.159f` against 0xbe23d58e. m8's `dynamics.rdr` sets these (the run shows them overwritten), so
  they do not act in the demo; the member-by-member mapping of that constructor is open.
- GCC also folds `cosf` / `sinf` of constants at compile time (`DEFAULT_CLOSESTNODE_DOT`,
  `RESTRAINT_DOT`, `CQB_DOT`, `max_y`): the arguments are now the ELF's words; the results come from
  GCC's folding, the ELF calls `cosf` at run time in `__sinit`.

### Read-back gaps (10 "not emitted")

The constant does not exist in the port build: dead branch (`CPad::Dilate`'s `which_dilation == 0`
path), unused statics (`YRate`, `a_followMultiplier`, `yDir`), `tanf(0.0f) * 0.707f` folded to 0,
`sinf(0.872664631f)` folded, `tb_timeToThrow` folded into its sums, the `cosf` statics above. Their
spelling was checked with the same arithmetic as the others (`spell.py`). The two negative entries of
GetThrowAnim's offset tables were read back by hand (0xbf7851ec, 0xc0cf5c29 in the unit).

## Behaviour

- CharacterDynamics (`hook_dyn.cpp` dumps the object after `Load`, same run on HEAD and on the final
  tree): 40 of 111 words differ. The angles read from `dynamics.rdr` times RAD_TO_DEG are 2-3 ulps
  larger (`m_maxAimPitch` 1.48352945 -> 1.48352981, 85 degrees is 0x3fbde44e: now exact), their
  cosines 2-7 ulps smaller, and three cosines near 90 degrees move further in ulps but by under
  4e-7 absolute (+0x9c 0.0871561542 -> 0.087155804, +0xb4 0.0174528603 -> 0.0174525026); the
  throw-params defaults move one ulp (0.149999991 -> 0.150000006, 0.6, 0.3). Nothing visible.
- CAiSPursue scan angles (pi/3, 85 degrees, pi/2) move by 1-4 ulps (about 2e-7 rad); the
  death-camera timer by one ulp; the pad's stick scale by one ulp. No comparison in the runs below
  flipped visibly.
- The one real change is the look epsilon: a turn throttle of 0.001-0.05 now counts as still.
- Runs on the final tree, all with focus kept:
  - fake-pad m8 (`hook_zseal1.cpp` from `boot-mod-zseal4` + `pad_fire.txt`, 240 s): intro skipped
    with CROSS at 57.3 s, briefing cameras with X at 57.4 / 58.7 s, 183 s in the mission; no STOP, no
    exception; 20 "fires at" lines (OutPatrol1 at the player, OutPatrol4 at Hutchins), kills and
    respawns, the team following (Bailey FOLLOW / HIDE FOLLOW / HIDE / WAIT, HUD "FOLLOWING"); heap in
    use 23.104-23.105 MB from 140 s to the end.
  - scripted win (`port/test-hooks/win`, -DSOCOM_HOOK_WIN, 270 s): Snow3 rescued (209.3 s), "EXIT:
    debrief open (objectives 3/7)" at 211.0 s, MISSION SUCCESSFUL on screen (3 of 5 primary, 7 of 8
    secondary, 70 %). The timing is the sample audit's (206.9 s) within the run-to-run spread.
  - state round trip (`port/test-hooks/state`, -DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=8), twice:
    in use 18,655,788 B at return 1 and 18,655,884 B at returns 2-8 in both runs (flat); largest free
    block 3,960,832 B, except at the returns where the break had grown during the mission (run 1:
    returns 2 and 4, run 2: return 2; break 0x1e92000, largest 2,584,576 B, back at the next
    return); 3,002,368 B at each mission start. HEAD's tree with the same hook (baseline run) shows
    the same figures and the same pattern (returns 2 and 4 grown; once 3,964,928 B), so the
    constants do not change the heap.
  - default build (no hooks, no fake pad): dlgMenu at 15.7 s, the main menu on screen.
- Screenshots (untracked): `build/port/screenshots/58-floatconst/`.

## Files

The rewrite touched 100 files under `src/` (no lines added or removed, no annotation or fence
changed). `src/gamez/zIntersect/int_material.cpp` (one site, `m_elasticity_coeff = 0.3f`) was held as
an edit file while another worker's checkout had it modified.

## Scope of the scan

Every float literal in `src/` was checked, not only the ones copied from `cz.py`: at HEAD 1019
literal tokens in 99 files had a toward-zero word different from their nearest word (`remain.py`).
After this work 199 remain, all judged: 175 in `recoil_table` (lead above), 7 CharacterDynamics
defaults in `zchar.h` (lead above), 15 whose GCC word is already the ELF's or that are port-only (`11.487f`,
`15.3f`, `0.72f`, HandleEvent's two `0.2f`, the port-only trace), one in a `#if 0` copy (`znode_holding.cpp`), and
`int_material.cpp`'s `0.3f` (fixed by the edit file). The ELF comparison (source and port sides) also
caught literals whose two roundings agree but which are themselves imprecise (rule B).

## Doubles and run-time parsing (reported, not changed)

- Double literals and double constant folding are IEEE round-to-nearest in this GCC (`DFmode` keeps
  the IEEE format; probe: `0.1` is 0x3fb999999999999a, `0.1 * 3.0` folds to 0x3fd3333333333334). A
  compile-time double-to-float conversion truncates like any float fold (`(float)(1.0 / 3.0)` is
  0x3eaaaaaa).
- At run time a double-to-float conversion is a call to libgcc's soft-float `__truncdfsf2` (the
  R5900 has no double unit); the soft-float double routines round to nearest by design. Not measured
  in a run.
- The reader parses reals with `strtod` and casts to `f32` (`zrdr_parse.cpp` 0x23f5e0; `atof` in
  `zanim_menu.cpp` and `zui_2d.cpp` likewise): newlib's `strtod` is correctly rounded, the cast goes
  through `__truncdfsf2`. That is the data path, separate from source literals; whether it matches the
  ELF's MSL parsing word for word was not checked.

### Counts by file (852 sites, 100 files)

| file | sites |
|---|---|
| gamez/zSeal/seal_ai.cpp | 75 |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 69 |
| gamez/zSeal/seal_env.cpp | 65 |
| gamez/zSeal/seal_body.cpp | 57 |
| gamez/zSeal/seal.cpp | 41 |
| gamez/zAnim/zanim_cmd_parse.cpp | 40 |
| gamez/zCamera/camera.cpp | 30 |
| Apps/FTS/hud/hud_objectives.cpp | 28 |
| Apps/FTS/hud/hud_main.cpp | 25 |
| gamez/zSeal/seal_kit.cpp | 24 |
| Apps/FTS/hud/hud_weaponsel.cpp | 19 |
| gamez/zInput/zin_main.cpp | 17 |
| Apps/FTS/hud/hud_ingame_weaponsel.cpp | 16 |
| gamez/zNode/node_world.cpp | 16 |
| gamez/zFTS/fts_mission.cpp | 15 |
| Apps/FTS/game/orders.cpp | 14 |
| Apps/FTS/hud/hud_pausemenu.cpp | 13 |
| gamez/zSeal/seal_control.cpp | 13 |
| gamez/zAI/ai_map.cpp | 11 |
| gamez/zWeapon/zwep_projectile.cpp | 11 |
| gamez/zVehicle/veh_turret.cpp | 10 |
| gamez/zCharacter/char_type.cpp | 9 |
| gamez/zSeal/seal_aiscan.cpp | 9 |
| gamez/zSeal/seal_weapon.cpp | 9 |
| gamez/zFTS/fts_remote.cpp | 8 |
| Apps/FTS/hud/hud_mapcompass.cpp | 7 |
| gamez/zSeal/seal_sensors.cpp | 7 |
| gamez/zSeal/seal_squirm.cpp | 7 |
| Apps/FTS/hud/hud_fader.cpp | 6 |
| gamez/zAI/ai_main.cpp | 6 |
| gamez/zSeal/seal_aifollow.cpp | 6 |
| gamez/zSeal/seal_airesponse.cpp | 6 |
| gamez/zUI/zui.cpp | 6 |
| gamez/zVisual/vis_main.cpp | 6 |
| gamez/zWeapon/zwep_weapon.cpp | 6 |
| Apps/FTS/hud/hud_teamnames.cpp | 5 |
| Apps/FTS/state/st_core.cpp | 5 |
| gamez/zGrid/grid_clutter.cpp | 5 |
| gamez/zSeal/seal_anim.cpp | 5 |
| gamez/zVehicle/vehicle_main.cpp | 5 |
| Apps/FTS/hud/hud_missioncams.cpp | 4 |
| Apps/FTS/hud/hud_newhudmap.cpp | 4 |
| Apps/FTS/hud/hud_scorepopup.cpp | 4 |
| gamez/zAI/ai_mapwalk.cpp | 4 |
| gamez/zCamera/zcam_main.cpp | 4 |
| gamez/zCharacter/zchar.h | 4 |
| gamez/zParticle/zparticle.cpp | 4 |
| gamez/zRender/zrndr_pipe.cpp | 4 |
| gamez/zSeal/seal_tasks.cpp | 4 |
| gamez/zUI/zui_2d.cpp | 4 |
| Apps/FTS/hud/hud_actionbitmap.cpp | 3 |
| Apps/FTS/hud/hud_lensflare.cpp | 3 |
| gamez/zAI/ai_maps.cpp | 3 |
| gamez/zAnim/zanim_anim.cpp | 3 |
| gamez/zAnim/zanim_cmd_tick.cpp | 3 |
| gamez/zCamera/zcam_update.cpp | 3 |
| gamez/zSeal/seal_aievent.cpp | 3 |
| gamez/zTexture/ztex_manager.cpp | 3 |
| Apps/FTS/state/st_exit.cpp | 2 |
| Apps/FTS/state/st_load.cpp | 2 |
| Apps/FTS/state/st_mpexit.cpp | 2 |
| gamez/zAnim/zanim_menu.cpp | 2 |
| gamez/zAnim/zanim_sequence.cpp | 2 |
| gamez/zMath/zmath_main.cpp | 2 |
| gamez/zParticle/zparticle.h | 2 |
| gamez/zParticle/zparticle_instance.cpp | 2 |
| gamez/zSeal/seal_aistate.cpp | 2 |
| gamez/zSeal/seal_cfg.cpp | 2 |
| gamez/zSound/zsnd_csnd.cpp | 2 |
| gamez/zTwoD/c2dbitmap_poly.cpp | 2 |
| gamez/zTwoD/ztwod_bitmap.cpp | 2 |
| gamez/zTwoD/ztwod_messageq.cpp | 2 |
| Apps/FTS/hud/hud_devtext.cpp | 1 |
| Apps/FTS/hud/hud_linemap.cpp | 1 |
| Apps/FTS/hud/hud_posebitmap.cpp | 1 |
| Apps/FTS/hud/hud_teammatenames.cpp | 1 |
| gamez/zAI/ai_astar.cpp | 1 |
| gamez/zAI/ai_mapdata.cpp | 1 |
| gamez/zAnim/anim_main.cpp | 1 |
| gamez/zBody/body.cpp | 1 |
| gamez/zFTS/fts_net_game.cpp | 1 |
| gamez/zGrid/grid_cell.cpp | 1 |
| gamez/zInput/remote_control.cpp | 1 |
| gamez/zInput/zinput.h | 1 |
| gamez/zIntersect/int_material.cpp | 1 |
| gamez/zMath/zmath.h | 1 |
| gamez/zMath/zmath_trig.cpp | 1 |
| gamez/zNode/node_main.cpp | 1 |
| gamez/zNode/node_util.cpp | 1 |
| gamez/zParticle/zparticle_buf.cpp | 1 |
| gamez/zParticle/zparticle_source.cpp | 1 |
| gamez/zSeal/seal_ctrl.cpp | 1 |
| gamez/zSeal/seal_unit.cpp | 1 |
| gamez/zSoftImage/si_object.cpp | 1 |
| gamez/zSound/zsnd_jukebox.cpp | 1 |
| gamez/zTwoD/c2dline.cpp | 1 |
| gamez/zTwoD/c2dstring.cpp | 1 |
| gamez/zTwoD/ztwod.h | 1 |
| gamez/zTwoD/ztwod_poly.cpp | 1 |
| gamez/zVisual/vis_bands.cpp | 1 |

### Counts by value (137 distinct rewrites)

| old | old word (GCC) | ELF word | new spelling | sites |
|---|---|---|---|---|
| `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | 93 |
| `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | 87 |
| `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | 83 |
| `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | 69 |
| `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | 52 |
| `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | 46 |
| `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | 34 |
| `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | 32 |
| `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | 26 |
| `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | 17 |
| `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | 16 |
| `0.995f` | 3f7eb851 | 3f7eb852 | `0.995000005f` | 16 |
| `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | 16 |
| `0.33f` | 3ea8f5c2 | 3ea8f5c3 | `0.330000014f` | 14 |
| `0.707f` | 3f34fdf3 | 3f34fdf4 | `0.707000018f` | 13 |
| `1.1f` | 3f8ccccc | 3f8ccccd | `1.10000003f` | 10 |
| `0.64f` | 3f23d70a | 3f23d70b | `0.640000046f` | 8 |
| `3.1415927f` | 40490fda | 40490fdb | `3.14159275f` | 8 |
| `0.97f` | 3f7851eb | 3f7851ec | `0.970000029f` | 7 |
| `0.98f` | 3f7ae147 | 3f7ae148 | `0.98000002f` | 7 |
| `3.14159274f` | 40490fda | 40490fdb | `3.14159275f` | 6 |
| `76.8f` | 42999999 | 4299999a | `76.8000031f` | 6 |
| `0.008f` | 3c03126e | 3c03126f | `0.00800000038f` | 5 |
| `(1.0f / 127.5f)` | 3c008080 | 3c008081 | `0.00784313772f` | 4 |
| `0.01745329f` | 3c8efa33 | 3c8efa35 | `0.0174532924f` | 4 |
| `0.2833f` | 3e910cb2 | 3e910cb3 | `0.283300013f` | 4 |
| `0.642f` | 3f245a1c | 3f245a1d | `0.64200002f` | 4 |
| `0.0005f` | 3a03126e | 3a03126f | `0.000500000024f` | 3 |
| `0.011111111f` | 3c360b60 | 3c360b61 | `0.0111111114f` | 3 |
| `0.075f` | 3d999999 | 3d99999a | `0.075000003f` | 3 |
| `0.2702703f` | 3e8a60de | 3e8a60dd | `0.270270259f` | 3 |
| `0.3490658f` | 3eb2b8c0 | 3eb2b8c2 | `0.349065841f` | 3 |
| `0.7f` | 3f333333 | 3f333334 | `0.700000048f` | 3 |
| `0.85f` | 3f599999 | 3f59999a | `0.850000024f` | 3 |
| `0.8725f` | 3f5f5c28 | 3f5f5c29 | `0.872500003f` | 3 |
| `0.999f` | 3f7fbe76 | 3f7fbe77 | `0.999000013f` | 3 |
| `1.0f / 30.0f` | 3d088888 | 3d088889 | `0.0333333351f` | 3 |
| `19.1f` | 4198cccc | 4198cccd | `19.1000004f` | 3 |
| `38.4f` | 42199999 | 4219999a | `38.4000016f` | 3 |
| `0.015384615f` | 3c7c0fc0 | 3c7c0fc1 | `0.0153846154f` | 2 |
| `0.025f` | 3ccccccc | 3ccccccd | `0.0250000004f` | 2 |
| `0.07f` | 3d8f5c28 | 3d8f5c29 | `0.0700000003f` | 2 |
| `0.166666f` | 3e2aaa7d | 3e2aaa7e | `0.166666002f` | 2 |
| `0.18f` | 3e3851eb | 3e3851ec | `0.180000008f` | 2 |
| `0.24434611f` | 3e7a35dd | 3e7a35de | `0.244346113f` | 2 |
| `0.31415927f` | 3ea0d97b | 3ea0d97c | `0.314159275f` | 2 |
| `0.33333334f` | 3eaaaaaa | 3eaaaaab | `0.333333344f` | 2 |
| `0.55f` | 3f0ccccc | 3f0ccccd | `0.550000012f` | 2 |
| `0.6000000238418579f` | 3f199999 | 3f19999a | `0.600000024f` | 2 |
| `0.68f` | 3f2e147a | 3f2e147b | `0.680000008f` | 2 |
| `0.707107f` | 3f3504f6 | 3f3504f7 | `0.707107008f` | 2 |
| `0.708f` | 3f353f7c | 3f353f7d | `0.708000005f` | 2 |
| `0.79f` | 3f4a3d70 | 3f4a3d71 | `0.790000022f` | 2 |
| `0.95993114f` | 3f75be0c | 3f75be0b | `0.959931076f` | 2 |
| `1.09f` | 3f8b851e | 3f8b851f | `1.09000004f` | 2 |
| `1.0f / 255.0f` | 3b808080 | 3b808081 | `0.00392156886f` | 2 |
| `1.134464f` | 3f91361d | 3f91361e | `1.13446403f` | 2 |
| `1.48353f` | 3fbde44f | 3fbde44e | `1.48352981f` | 2 |
| `1.5626f` | 3fc80346 | 3fc80347 | `1.56260002f` | 2 |
| `1.569051f` | 3fc8d6a9 | 3fc8d6aa | `1.56905103f` | 2 |
| `14.8f` | 416ccccc | 416ccccd | `14.8000002f` | 2 |
| `15.6f` | 41799999 | 4179999a | `15.6000004f` | 2 |
| `2.2f` | 400ccccc | 400ccccd | `2.20000005f` | 2 |
| `2.42f` | 401ae147 | 401ae148 | `2.42000008f` | 2 |
| `2.8274333f` | 4034f4aa | 4034f4ab | `2.82743335f` | 2 |
| `4.6e-05f` | 3840f01f | 3840f020 | `4.60000011e-5f` | 2 |
| `5.01f` | 40a051eb | 40a051ec | `5.01000023f` | 2 |
| `50.666664f` | 424aaaa9 | 424aaaaa | `50.6666642f` | 2 |
| `57.29578f` | 42652ee0 | 42652ee1 | `57.2957802f` | 2 |
| `9.8f` | 411ccccc | 411ccccd | `9.8000002f` | 2 |
| `0.000375f` | 39c49ba5 | 39c49ba6 | `0.000375000004f` | 1 |
| `0.001f` | 3a83126e | 3d4ccccd | `0.0500000008f` | 1 |
| `0.004f` | 3b83126e | 3b83126f | `0.00400000019f` | 1 |
| `0.024543693f` | 3cc90fda | 3cc90fdb | `0.0245436933f` | 1 |
| `0.029999999329447746f` | 3cf5c28e | 3cf5c28f | `0.0299999994f` | 1 |
| `0.03333334f` | 3d08888a | 3d088889 | `0.0333333351f` | 1 |
| `0.08726646f` | 3db2b8c1 | 3db2b8c2 | `0.0872664601f` | 1 |
| `0.099999994f` | 3dcccccb | 3dcccccc | `0.0999999941f` | 1 |
| `0.24f` | 3e75c28f | 3e75c290 | `0.24000001f` | 1 |
| `0.2617993950843811f` | 3e860a91 | 3e860a92 | `0.261799396f` | 1 |
| `0.28f` | 3e8f5c28 | 3e8f5c29 | `0.280000002f` | 1 |
| `0.33333f` | 3eaaaa3a | 3eaaaa3b | `0.333330006f` | 1 |
| `0.347f` | 3eb1a9fb | 3eb1a9fc | `0.347000003f` | 1 |
| `0.34906584f` | 3eb2b8c1 | 3eb2b8c2 | `0.349065841f` | 1 |
| `0.36397f` | 3eba5a46 | 3eba5a47 | `0.363970012f` | 1 |
| `0.44999998807907104f` | 3ee66665 | 3ee66666 | `0.449999989f` | 1 |
| `0.5235987901687622f` | 3f060a91 | 3f060a92 | `0.523598791f` | 1 |
| `0.56f` | 3f0f5c28 | 3f0f5c29 | `0.560000003f` | 1 |
| `0.62f` | 3f1eb851 | 3f1eb852 | `0.620000005f` | 1 |
| `0.64278f` | 3f248d3a | 3f248d3b | `0.642780006f` | 1 |
| `0.6600000262260437f` | 3f28f5c2 | 3f28f5c3 | `0.660000027f` | 1 |
| `0.66f` | 3f28f5c2 | 3f28f5c3 | `0.660000027f` | 1 |
| `0.67f` | 3f2b851e | 3f2b851f | `0.670000017f` | 1 |
| `0.6899999976158142f` | 3f30a3d6 | 3f30a3d7 | `0.689999998f` | 1 |
| `0.699999988079071f` | 3f333332 | 3f333333 | `0.699999989f` | 1 |
| `0.72f` | 3f3851eb | 3f3851ec | `0.720000029f` | 1 |
| `0.785f` | 3f48f5c2 | 3f48f5c3 | `0.785000027f` | 1 |
| `0.8726646f` | 3f5f66f2 | 3f5f66f3 | `0.872664631f` | 1 |
| `0.87f` | 3f5eb851 | 3f5eb852 | `0.870000005f` | 1 |
| `0.999848f` | 3f7ff609 | 3f7ff60a | `0.999848009f` | 1 |
| `1.0001f` | 3f800346 | 3f800347 | `1.00010002f` | 1 |
| `1.047198f` | 3f860a95 | 3f860a92 | `1.04719759f` | 1 |
| `1.075f` | 3f899999 | 3f89999a | `1.07500005f` | 1 |
| `1.11f` | 3f8e147a | 3f8e147b | `1.11000002f` | 1 |
| `1.149999976158142f` | 3f933332 | 3f933333 | `1.14999998f` | 1 |
| `1.3962634f` | 3fb2b8c2 | 3fb2b8c3 | `1.39626349f` | 1 |
| `1.414f` | 3fb4fdf3 | 3fb4fdf4 | `1.41400004f` | 1 |
| `1.570796f` | 3fc90fd7 | 3fc90fdb | `1.57079638f` | 1 |
| `1.96f` | 3ffae147 | 3ffae148 | `1.96000004f` | 1 |
| `10.13f` | 4122147a | 4122147b | `10.1300002f` | 1 |
| `10.6f` | 41299999 | 4129999a | `10.6000004f` | 1 |
| `100000.6f` | 47c3504c | 47c3504d | `100000.602f` | 1 |
| `107.3296f` | 42d6a8c1 | 42d6a8c3 | `107.329613f` | 1 |
| `11.47f` | 4137851e | 4137851f | `11.4700003f` | 1 |
| `12.6f` | 41499999 | 4149999a | `12.6000004f` | 1 |
| `13.8f` | 415ccccc | 415ccccd | `13.8000002f` | 1 |
| `14.3f` | 4164cccc | 4164cccd | `14.3000002f` | 1 |
| `15.05f` | 4170cccc | 4170cccd | `15.0500002f` | 1 |
| `15.59f` | 417970a3 | 417970a4 | `15.5900002f` | 1 |
| `17.2f` | 41899999 | 4189999a | `17.2000008f` | 1 |
| `2.39f` | 4018f5c2 | 4018f5c3 | `2.39000011f` | 1 |
| `2.9f` | 40399999 | 4039999a | `2.9000001f` | 1 |
| `3.13f` | 404851eb | 404851ec | `3.13000012f` | 1 |
| `3.14f` | 4048f5c2 | 4048f5c3 | `3.14000011f` | 1 |
| `3.2f` | 404ccccc | 404ccccd | `3.20000005f` | 1 |
| `369.6f` | 43b8cccc | 43b8cccd | `369.600007f` | 1 |
| `4.03f` | 4080f5c2 | 4080f5c3 | `4.03000021f` | 1 |
| `4.5454545e-4f` | 39ee500e | 39ee500f | `0.000454545458f` | 1 |
| `5.26f` | 40a851eb | 40a851ec | `5.26000023f` | 1 |
| `5.4f` | 40accccc | 40accccd | `5.4000001f` | 1 |
| `6.05f` | 40c19999 | 40c1999a | `6.0500002f` | 1 |
| `6.2925f` | 40c95c28 | 40c95c29 | `6.29250002f` | 1 |
| `6.48f` | 40cf5c28 | 40cf5c29 | `6.48000002f` | 1 |
| `7.8f` | 40f99999 | 40f9999a | `7.8000002f` | 1 |
| `9.55f` | 4118cccc | 4118cccd | `9.5500002f` | 1 |
| `98.100006f` | 42c43333 | 42c43334 | `98.1000062f` | 1 |
| `fade_out + 0.5f * faded` | 3e999999 | 3e99999a | `0.300000012f` | 1 |

### Site table (589 rows; one row per function and rewrite, lines listed)

Read-back: the word in the `-g` analysis build of the final tree, attributed to the line, else to the
function (inline chains included), else found in the unit's assembly (data, switch tables), else
"not emitted" (the compiler dropped or folded the constant: see "Read-back gaps"). Every read-back word
equals the ELF word.

| file | lines | function (ELF address) | old | old word | ELF word | new | read-back |
|---|---|---|---|---|---|---|---|
| Apps/FTS/game/orders.cpp | 376 376 | Draw__12C2DOrderItemFPQ23zdb7CCamera 0x17c3a0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| Apps/FTS/game/orders.cpp | 1235 1235 | SetupTeamDisplay__10OrdersMenuFv 0x1798c0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| Apps/FTS/game/orders.cpp | 1331 1331 | SetupCommandDisplay__10OrdersMenuFv 0x1792c0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| Apps/FTS/game/orders.cpp | 1410 1410 | SetupContextDisplay__10OrdersMenuFb 0x178eb0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| Apps/FTS/game/orders.cpp | 1747 | LoadTextures__10OrdersMenuFPQ23zdb6CWorldP7C2DFont 0x1772a0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/game/orders.cpp | 1748 | LoadTextures__10OrdersMenuFPQ23zdb6CWorldP7C2DFont 0x1772a0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| Apps/FTS/game/orders.cpp | 1748 1749 | LoadTextures__10OrdersMenuFPQ23zdb6CWorldP7C2DFont 0x1772a0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| Apps/FTS/game/orders.cpp | 1749 1750 | LoadTextures__10OrdersMenuFPQ23zdb6CWorldP7C2DFont 0x1772a0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| Apps/FTS/hud/hud_actionbitmap.cpp | 305 | SpecializeActionString__18CActionTxtrMachineFv 0x3d7b90 | `38.4f` | 42199999 | 4219999a | `38.4000016f` | line |
| Apps/FTS/hud/hud_actionbitmap.cpp | 686 | Init__14CZActionBitmapFP4CHUDP7C2DFont 0x3d5e40 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_actionbitmap.cpp | 715 | Init__14CZActionBitmapFP4CHUDP7C2DFont 0x3d5e40 | `38.4f` | 42199999 | 4219999a | `38.4000016f` | line |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 326 326 326 326 | Init__14BitmapReticuleFPQ23zdb6CWorldP7C2DFont 0x3cf6d0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 334 334 334 334 335 335 335 335 336 336 336 336 337 337 337 337 | Init__14BitmapReticuleFPQ23zdb6CWorldP7C2DFont 0x3cf6d0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | function |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 390 390 390 390 | Init__14BitmapReticuleFPQ23zdb6CWorldP7C2DFont 0x3cf6d0 | `0.995f` | 3f7eb851 | 3f7eb852 | `0.995000005f` | line |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 391 391 391 391 392 392 392 392 393 393 393 393 | Init__14BitmapReticuleFPQ23zdb6CWorldP7C2DFont 0x3cf6d0 | `0.995f` | 3f7eb851 | 3f7eb852 | `0.995000005f` | function |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 642 643 651 | UpdateColor__14BitmapReticuleFv 0x3ced20 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 652 | UpdateColor__14BitmapReticuleFv 0x3ced20 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 713 721 | UpdateAccuracy__14BitmapReticuleFv 0x3ce4e0 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | function |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 1043 1043 1043 1043 1065 1065 | ChangeReticule__14BitmapReticuleFi 0x3cd930 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 1044 1044 1044 1044 1045 1045 1045 1045 1046 1046 1046 1046 1066 1066 | ChangeReticule__14BitmapReticuleFi 0x3cd930 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | function |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 1065 1065 | ChangeReticule__14BitmapReticuleFi 0x3cd930 | `0.97f` | 3f7851eb | 3f7851ec | `0.970000029f` | line |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 1066 1066 | ChangeReticule__14BitmapReticuleFi 0x3cd930 | `0.97f` | 3f7851eb | 3f7851ec | `0.970000029f` | function |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 1144 | SetGBarVal__14BitmapReticuleFf 0x3cd490 | `0.97f` | 3f7851eb | 3f7851ec | `0.970000029f` | line |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 1168 | UpdateGBarColor__14BitmapReticuleFf 0x3cd320 | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | line |
| Apps/FTS/hud/hud_bitmapreticule.cpp | 1224 | TimerProgressTick__14BitmapReticuleFfP10CZSealBody 0x3cd110 | `38.4f` | 42199999 | 4219999a | `38.4000016f` | line |
| Apps/FTS/hud/hud_devtext.cpp | 467 | StatusLine__4CHUDFv 0x3d9820 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| Apps/FTS/hud/hud_fader.cpp | 53 54 | Tick__6CFaderFf 0x4035d0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| Apps/FTS/hud/hud_fader.cpp | 160 162 165 167 | Tick__8CFlashFXFf 0x4031a0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| Apps/FTS/hud/hud_ingame_weaponsel.cpp | 134 134 | Init__16CInGameWeaponSelFPQ23zdb6CWorldP7C2DFont 0x3fc5c0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| Apps/FTS/hud/hud_ingame_weaponsel.cpp | 135 | Init__16CInGameWeaponSelFPQ23zdb6CWorldP7C2DFont 0x3fc5c0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| Apps/FTS/hud/hud_ingame_weaponsel.cpp | 135 135 195 195 | Init__16CInGameWeaponSelFPQ23zdb6CWorldP7C2DFont 0x3fc5c0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | function |
| Apps/FTS/hud/hud_ingame_weaponsel.cpp | 147 147 | Init__16CInGameWeaponSelFPQ23zdb6CWorldP7C2DFont 0x3fc5c0 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | line |
| Apps/FTS/hud/hud_ingame_weaponsel.cpp | 395 | HandleOpenState__16CInGameWeaponSelFP4CPadf 0x3fba70 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| Apps/FTS/hud/hud_ingame_weaponsel.cpp | 395 397 | HandleOpenState__16CInGameWeaponSelFP4CPadf 0x3fba70 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| Apps/FTS/hud/hud_ingame_weaponsel.cpp | 402 | HandleOpenState__16CInGameWeaponSelFP4CPadf 0x3fba70 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| Apps/FTS/hud/hud_ingame_weaponsel.cpp | 1192 1225 | PlaceWeaponText__16CInGameWeaponSelFv 0x3f8860 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_ingame_weaponsel.cpp | 1201 | PlaceWeaponText__16CInGameWeaponSelFv 0x3f8860 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| Apps/FTS/hud/hud_lensflare.cpp | 232 | Init__18CLensFlareSaturateFv 0x3bdba0 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| Apps/FTS/hud/hud_lensflare.cpp | 283 | Tick__18CLensFlareSaturateFf 0x3bd640 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| Apps/FTS/hud/hud_lensflare.cpp | 325 | Tick__18CLensFlareSaturateFf 0x3bd640 | `0.025f` | 3ccccccc | 3ccccccd | `0.0250000004f` | line |
| Apps/FTS/hud/hud_linemap.cpp | 693 | TickRegions__9CZLineMapFRC6CAiMapb 0x3c86b0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_main.cpp | 402 | Init__4CHUDFPQ23zdb6CWorld 0x3ba0b0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_main.cpp | 403 404 424 479 481 489 535 | Init__4CHUDFPQ23zdb6CWorld 0x3ba0b0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| Apps/FTS/hud/hud_main.cpp | 453 | Init__4CHUDFPQ23zdb6CWorld 0x3ba0b0 | `76.8f` | 42999999 | 4299999a | `76.8000031f` | line |
| Apps/FTS/hud/hud_main.cpp | 624 | Tick__4CHUDFf 0x3b94e0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_main.cpp | 626 | Tick__4CHUDFf 0x3b94e0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| Apps/FTS/hud/hud_main.cpp | 783 792 | Tick__4CHUDFf 0x3b94e0 | `76.8f` | 42999999 | 4299999a | `76.8000031f` | line |
| Apps/FTS/hud/hud_main.cpp | 935 | IsOn__4CHUDFv 0x3b8ec0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_main.cpp | 1206 1213 1220 1227 1238 | SetupFiremode__4CHUDFP10CZSealBody 0x3b7ce0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_main.cpp | 1233 | SetupFiremode__4CHUDFP10CZSealBody 0x3b7ce0 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | line |
| Apps/FTS/hud/hud_main.cpp | 1268 | SetupAmmoCount__4CHUDFP10CZSealBody 0x3b79d0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_main.cpp | 1281 1295 | SetupAmmoCount__4CHUDFP10CZSealBody 0x3b79d0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| Apps/FTS/hud/hud_main.cpp | 1333 | DoRangeText__4CHUDFP10CZSealBody10MENU_STATE 0x3b7820 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| Apps/FTS/hud/hud_main.cpp | 1334 | DoRangeText__4CHUDFP10CZSealBody10MENU_STATE 0x3b7820 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_mapcompass.cpp | 276 | Tick__10MapCompassFP10CZSealBody 0x3cb160 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | function |
| Apps/FTS/hud/hud_mapcompass.cpp | 409 | Tick__10MapCompassFP10CZSealBody 0x3cb160 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| Apps/FTS/hud/hud_mapcompass.cpp | 412 412 | Tick__10MapCompassFP10CZSealBody 0x3cb160 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_mapcompass.cpp | 427 | Tick__10MapCompassFP10CZSealBody 0x3cb160 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | function |
| Apps/FTS/hud/hud_mapcompass.cpp | 428 428 | Tick__10MapCompassFP10CZSealBody 0x3cb160 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| Apps/FTS/hud/hud_missioncams.cpp | 288 | PlayCamera__16CZHudMissionCamsFP11CMissionCamb 0x403830 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_missioncams.cpp | 303 305 313 | PlayCamera__16CZHudMissionCamsFP11CMissionCamb 0x403830 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| Apps/FTS/hud/hud_newhudmap.cpp | 298 | GetZoomOut__11CZNewHudMapCFv 0x3c6470 | `4.5454545e-4f` | 39ee500e | 39ee500f | `0.000454545458f` | line |
| Apps/FTS/hud/hud_newhudmap.cpp | 580 | CalcNewMatrix__11CZNewHudMapFv 0x3c5510 | `3.1415927f` | 40490fda | 40490fdb | `3.14159275f` | line |
| Apps/FTS/hud/hud_newhudmap.cpp | 1123 1146 | TickFullScreenAnims__11CZNewHudMapCFf 0x3c3790 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| Apps/FTS/hud/hud_objectives.cpp | 221 | AddObjective__15CZObjectiveListFRC20CMissionObjectiveCamf 0x3c2210 | `0.68f` | 3f2e147a | 3f2e147b | `0.680000008f` | line |
| Apps/FTS/hud/hud_objectives.cpp | 401 401 | RefreshStatics__15CZObjectiveListFv 0x3c0c90 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| Apps/FTS/hud/hud_objectives.cpp | 407 407 | RefreshStatics__15CZObjectiveListFv 0x3c0c90 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_objectives.cpp | 410 410 413 413 419 420 431 433 434 435 465 465 | RefreshStatics__15CZObjectiveListFv 0x3c0c90 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| Apps/FTS/hud/hud_objectives.cpp | 416 | RefreshStatics__15CZObjectiveListFv 0x3c0c90 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | line |
| Apps/FTS/hud/hud_objectives.cpp | 417 | RefreshStatics__15CZObjectiveListFv 0x3c0c90 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | function |
| Apps/FTS/hud/hud_objectives.cpp | 422 | RefreshStatics__15CZObjectiveListFv 0x3c0c90 | `50.666664f` | 424aaaa9 | 424aaaaa | `50.6666642f` | line |
| Apps/FTS/hud/hud_objectives.cpp | 426 | RefreshStatics__15CZObjectiveListFv 0x3c0c90 | `50.666664f` | 424aaaa9 | 424aaaaa | `50.6666642f` | function |
| Apps/FTS/hud/hud_objectives.cpp | 456 | RefreshStatics__15CZObjectiveListFv 0x3c0c90 | `0.64f` | 3f23d70a | 3f23d70b | `0.640000046f` | line |
| Apps/FTS/hud/hud_objectives.cpp | 457 458 459 460 461 462 | RefreshStatics__15CZObjectiveListFv 0x3c0c90 | `0.64f` | 3f23d70a | 3f23d70b | `0.640000046f` | function |
| Apps/FTS/hud/hud_pausemenu.cpp | 264 | ReInit__11CZPauseTestFv 0x3bec30 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | line |
| Apps/FTS/hud/hud_pausemenu.cpp | 268 272 280 285 | ReInit__11CZPauseTestFv 0x3bec30 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | function |
| Apps/FTS/hud/hud_pausemenu.cpp | 368 | HudTick__11CZPauseTestFP4CPadf 0x3be880 | `17.2f` | 41899999 | 4189999a | `17.2000008f` | line |
| Apps/FTS/hud/hud_pausemenu.cpp | 369 | HudTick__11CZPauseTestFP4CPadf 0x3be880 | `12.6f` | 41499999 | 4149999a | `12.6000004f` | line |
| Apps/FTS/hud/hud_pausemenu.cpp | 370 | HudTick__11CZPauseTestFP4CPadf 0x3be880 | `5.4f` | 40accccc | 40accccd | `5.4000001f` | line |
| Apps/FTS/hud/hud_pausemenu.cpp | 371 399 | HudTick__11CZPauseTestFP4CPadf 0x3be880 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| Apps/FTS/hud/hud_pausemenu.cpp | 393 | HudTick__11CZPauseTestFP4CPadf 0x3be880 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_pausemenu.cpp | 395 | HudTick__11CZPauseTestFP4CPadf 0x3be880 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| Apps/FTS/hud/hud_pausemenu.cpp | 401 | HudTick__11CZPauseTestFP4CPadf 0x3be880 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | function |
| Apps/FTS/hud/hud_posebitmap.cpp | 52 | Init__10PoseBitmapFPQ23zdb6CWorld 0x3d9610 | `0.68f` | 3f2e147a | 3f2e147b | `0.680000008f` | line |
| Apps/FTS/hud/hud_scorepopup.cpp | 307 | SetupBackgroundBox__28@unnamed@hud_scorepopup_cpp@Fv 0x421920 | `0.2702703f` | 3e8a60de | 3e8a60dd | `0.270270259f` | line |
| Apps/FTS/hud/hud_scorepopup.cpp | 309 320 | SetupBackgroundBox__28@unnamed@hud_scorepopup_cpp@Fv 0x421920 | `0.2702703f` | 3e8a60de | 3e8a60dd | `0.270270259f` | function |
| Apps/FTS/hud/hud_scorepopup.cpp | 426 | SetupTeam__Q228@unnamed@hud_scorepopup_cpp@12CTeamDisplayFffffPCcM9CZNetGameFPCvPCv_ib 0x421140 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_teammatenames.cpp | 38 | Init__14CTeamMateNamesFP7C2DFont 0x3dee20 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_teamnames.cpp | 75 | SetOpacity__10CTeamNamesFf 0x3d9020 | `76.8f` | 42999999 | 4299999a | `76.8000031f` | function |
| Apps/FTS/hud/hud_teamnames.cpp | 76 | SetOpacity__10CTeamNamesFf 0x3d9020 | `76.8f` | 42999999 | 4299999a | `76.8000031f` | line |
| Apps/FTS/hud/hud_teamnames.cpp | 89 | SetOpacity__10CTeamNamesFf 0x3d9020 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| Apps/FTS/hud/hud_teamnames.cpp | 175 | Init__10CTeamNamesFv 0x3d8a00 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | line |
| Apps/FTS/hud/hud_teamnames.cpp | 176 | Init__10CTeamNamesFv 0x3d8a00 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | function |
| Apps/FTS/hud/hud_weaponsel.cpp | 146 146 | Init__10CWeaponSelFPQ23zdb6CWorldP7C2DFont 0x3d4430 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| Apps/FTS/hud/hud_weaponsel.cpp | 147 | Init__10CWeaponSelFPQ23zdb6CWorldP7C2DFont 0x3d4430 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| Apps/FTS/hud/hud_weaponsel.cpp | 147 147 198 198 | Init__10CWeaponSelFPQ23zdb6CWorldP7C2DFont 0x3d4430 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | function |
| Apps/FTS/hud/hud_weaponsel.cpp | 153 153 | Init__10CWeaponSelFPQ23zdb6CWorldP7C2DFont 0x3d4430 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | line |
| Apps/FTS/hud/hud_weaponsel.cpp | 403 | HandleOpenState__10CWeaponSelFP4CPadf 0x3d39f0 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| Apps/FTS/hud/hud_weaponsel.cpp | 403 405 | HandleOpenState__10CWeaponSelFP4CPadf 0x3d39f0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| Apps/FTS/hud/hud_weaponsel.cpp | 410 | HandleOpenState__10CWeaponSelFP4CPadf 0x3d39f0 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| Apps/FTS/hud/hud_weaponsel.cpp | 1099 | HudTick__10CWeaponSelFP4CPadf 0x3d1ad0 | `76.8f` | 42999999 | 4299999a | `76.8000031f` | line |
| Apps/FTS/hud/hud_weaponsel.cpp | 1200 1216 | PlaceHotSwapLabels__10CWeaponSelFv 0x3d0e40 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_weaponsel.cpp | 1263 | PlaceWeaponText__10CWeaponSelFv 0x3d0ac0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/hud/hud_weaponsel.cpp | 1272 1294 | PlaceWeaponText__10CWeaponSelFv 0x3d0ac0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| Apps/FTS/state/st_core.cpp | 175 | Tick__15CCinematicStateFf 0x17d9d0 | `1.1f` | 3f8ccccc | 3f8ccccd | `1.10000003f` | function |
| Apps/FTS/state/st_core.cpp | 181 | Tick__15CCinematicStateFf 0x17d9d0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| Apps/FTS/state/st_core.cpp | 193 | Tick__15CCinematicStateFf 0x17d9d0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| Apps/FTS/state/st_core.cpp | 315 | Init__10CCoreStateFv 0x17d2e0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| Apps/FTS/state/st_core.cpp | 325 | Init__10CCoreStateFv 0x17d2e0 | `10.6f` | 41299999 | 4129999a | `10.6000004f` | line |
| Apps/FTS/state/st_exit.cpp | 177 | SetRoundStatUiVars__21@unnamed@st_exit_cpp@Fii 0x320b60 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| Apps/FTS/state/st_exit.cpp | 177 | SetRoundStatUiVars__21@unnamed@st_exit_cpp@Fii 0x320b60 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| Apps/FTS/state/st_load.cpp | 124 | PrepControls__9CLoadMenuFPQ23zdb16CTextureRelocMgr 0x37fa30 | `369.6f` | 43b8cccc | 43b8cccd | `369.600007f` | line |
| Apps/FTS/state/st_load.cpp | 153 | MyTick__9CLoadMenuFf 0x37f940 | `3.1415927f` | 40490fda | 40490fdb | `3.14159275f` | line |
| Apps/FTS/state/st_mpexit.cpp | 105 106 | MultiplayerMsgStrings 0x476ef0 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zAI/ai_astar.cpp | 162 | path_queue__2ai 0x49b160 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | unit asm |
| gamez/zAI/ai_main.cpp | 224 242 | get_clock_direction__2aiFPC6CPnt3D 0x17de90 | `0.2833f` | 3e910cb2 | 3e910cb3 | `0.283300013f` | function |
| gamez/zAI/ai_main.cpp | 227 239 | get_clock_direction__2aiFPC6CPnt3D 0x17de90 | `0.708f` | 3f353f7c | 3f353f7d | `0.708000005f` | line |
| gamez/zAI/ai_main.cpp | 230 236 | get_clock_direction__2aiFPC6CPnt3D 0x17de90 | `0.2833f` | 3e910cb2 | 3e910cb3 | `0.283300013f` | line |
| gamez/zAI/ai_map.cpp | 161 161 | GetDirVec__6CAiMapFQ26CAiMap3DIRR6CPnt3D 0x187d90 | `0.707f` | 3f34fdf3 | 3f34fdf4 | `0.707000018f` | function |
| gamez/zAI/ai_map.cpp | 163 163 165 165 167 167 | GetDirVec__6CAiMapFQ26CAiMap3DIRR6CPnt3D 0x187d90 | `0.707f` | 3f34fdf3 | 3f34fdf4 | `0.707000018f` | line |
| gamez/zAI/ai_map.cpp | 181 197 | GetDirQuat__6CAiMapFQ26CAiMap3DIRR5CQuatb 0x187bd0 | `3.1415927f` | 40490fda | 40490fdb | `3.14159275f` | line |
| gamez/zAI/ai_map.cpp | 189 | GetDirQuat__6CAiMapFQ26CAiMap3DIRR5CQuatb 0x187bd0 | `3.1415927f` | 40490fda | 40490fdb | `3.14159275f` | function |
| gamez/zAI/ai_mapdata.cpp | 513 | ReRoute__6CAiMapFPQ26CAiMap5route 0x19e320 | `0.03333334f` | 3d08888a | 3d088889 | `0.0333333351f` | line |
| gamez/zAI/ai_maps.cpp | 512 592 | GetInterpolatedShadow__7CAiMapsFRC9CAiMapLocPC6CPnt3Db 0x19b290 | `0.98f` | 3f7ae147 | 3f7ae148 | `0.98000002f` | line |
| gamez/zAI/ai_maps.cpp | 515 | GetInterpolatedShadow__7CAiMapsFRC9CAiMapLocPC6CPnt3Db 0x19b290 | `0.33333334f` | 3eaaaaaa | 3eaaaaab | `0.333333344f` | line |
| gamez/zAI/ai_mapwalk.cpp | 157 | _VisLineCallback__FRC19MAP_LINEWALK_STRUCTPv 0x1a8360 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| gamez/zAI/ai_mapwalk.cpp | 161 | _VisLineCallback__FRC19MAP_LINEWALK_STRUCTPv 0x1a8360 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | function |
| gamez/zAI/ai_mapwalk.cpp | 217 | ComputeLineVisibility__6CAiMapFRC9CAiMapLocRC9CAiMapLoc 0x1a8280 | `0.33f` | 3ea8f5c2 | 3ea8f5c3 | `0.330000014f` | function |
| gamez/zAI/ai_mapwalk.cpp | 281 | ComputeLineVisibility__6CAiMapFRC9CAiMapLocRC9CAiMapLoc 0x1a8280 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zAnim/anim_main.cpp | 116 | Open__10CZAnimMainFv 0x1c53b0 | `9.8f` | 411ccccc | 411ccccd | `9.8000002f` | line |
| gamez/zAnim/zanim_anim.cpp | 339 | OnWeaponHit__8CZAnimExFPQ23zdb5CNodePQ23zdb15IntersectStructP12CZProjectile 0x1cf660 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zAnim/zanim_anim.cpp | 351 | OnWeaponHit__8CZAnimExFPQ23zdb5CNodePQ23zdb15IntersectStructP12CZProjectile 0x1cf660 | `0.707f` | 3f34fdf3 | 3f34fdf4 | `0.707000018f` | line |
| gamez/zAnim/zanim_anim.cpp | 352 | OnWeaponHit__8CZAnimExFPQ23zdb5CNodePQ23zdb15IntersectStructP12CZProjectile 0x1cf660 | `0.707f` | 3f34fdf3 | 3f34fdf4 | `0.707000018f` | function |
| gamez/zAnim/zanim_cmd_parse.cpp | 115 | zAnimGetDirectionFromAzimuthZenith__FffP6CPnt3D 0x1b7b90 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 118 | zAnimGetDirectionFromAzimuthZenith__FffP6CPnt3D 0x1b7b90 | `0.011111111f` | 3c360b60 | 3c360b61 | `0.0111111114f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 740 | zAnimLoadCamera__FP5_zrdr 0x1b4ca0 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 759 763 778 782 | zAnimLoadCamera__FP5_zrdr 0x1b4ca0 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 1512 1520 | zAnimLoadObjectRotateState__FP5_zrdr 0x1b2fb0 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 1513 1514 1521 1522 | zAnimLoadObjectRotateState__FP5_zrdr 0x1b2fb0 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | function |
| gamez/zAnim/zanim_cmd_parse.cpp | 1569 1574 | zAnimLoadObjectMotionFromTo__FP5_zrdr 0x1b1b90 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 1745 1756 | zAnimLoadObjectMotionFromTo__FP5_zrdr 0x1b1b90 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 1746 1747 1757 1758 | zAnimLoadObjectMotionFromTo__FP5_zrdr 0x1b1b90 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | function |
| gamez/zAnim/zanim_cmd_parse.cpp | 1870 | zAnimLoadObjectOpacityFromTo__FP5_zrdr 0x1b1a20 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 2869 | zAnimLoadObjectMotion__FP5_zrdr 0x1ac7d0 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 2933 3156 3157 3158 3165 3166 3167 3204 3211 | zAnimLoadObjectMotion__FP5_zrdr 0x1ac7d0 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 2934 | zAnimLoadObjectMotion__FP5_zrdr 0x1ac7d0 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | function |
| gamez/zAnim/zanim_cmd_parse.cpp | 2935 | zAnimLoadObjectMotion__FP5_zrdr 0x1ac7d0 | `0.011111111f` | 3c360b60 | 3c360b61 | `0.0111111114f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 3061 | zAnimLoadObjectMotion__FP5_zrdr 0x1ac7d0 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 3295 3346 | zAnimLoadObjectMotionSIScriptForObject__FP5_zrdriPCc 0x1ac460 | `1.0f / 30.0f` | 3d088888 (folded) | 3d088889 | `0.0333333351f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 3335 | zAnimLoadObjectMotionSIScriptForObject__FP5_zrdriPCc 0x1ac460 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zAnim/zanim_cmd_parse.cpp | 3336 3337 | zAnimLoadObjectMotionSIScriptForObject__FP5_zrdriPCc 0x1ac460 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | function |
| gamez/zAnim/zanim_cmd_tick.cpp | 1707 | zAnimObjectMotionTick__FP14_zanim_cmd_hdrPf 0x1bb330 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zAnim/zanim_cmd_tick.cpp | 1830 1839 | zAnimObjectMotionTick__FP14_zanim_cmd_hdrPf 0x1bb330 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zAnim/zanim_menu.cpp | 1543 1548 | UICheckForcedLaunch__FP13C2DAnimCmdHdrPf 0x1d43f0 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zAnim/zanim_sequence.cpp | 79 | GetFractionalRotations__FPC6CPnt3DPfPf 0x1dcde0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zAnim/zanim_sequence.cpp | 89 | GetFractionalRotations__FPC6CPnt3DPfPf 0x1dcde0 | `1.3962634f` | 3fb2b8c2 | 3fb2b8c3 | `1.39626349f` | line |
| gamez/zBody/body.cpp | 832 | SetMultiplier__10CZBodyAnimFb 0x1e1bf0 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zCamera/camera.cpp | 1089 1144 1165 1192 1198 1208 1250 1280 | UpdateDeathCamState__10CAppCameraFf 0x1e9620 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zCamera/camera.cpp | 1090 | UpdateDeathCamState__10CAppCameraFf 0x1e9620 | `1.075f` | 3f899999 | 3f89999a | `1.07500005f` | line |
| gamez/zCamera/camera.cpp | 1145 1146 1166 | UpdateDeathCamState__10CAppCameraFf 0x1e9620 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | function |
| gamez/zCamera/camera.cpp | 1147 | UpdateDeathCamState__10CAppCameraFf 0x1e9620 | `fade_out + 0.5f * faded` | 3e999999 (folded) | 3e99999a | `0.300000012f` | line |
| gamez/zCamera/camera.cpp | 1164 1282 | UpdateDeathCamState__10CAppCameraFf 0x1e9620 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zCamera/camera.cpp | 1182 1192 1208 | UpdateDeathCamState__10CAppCameraFf 0x1e9620 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zCamera/camera.cpp | 1192 | UpdateDeathCamState__10CAppCameraFf 0x1e9620 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zCamera/camera.cpp | 1197 | UpdateDeathCamState__10CAppCameraFf 0x1e9620 | `1.1f` | 3f8ccccc | 3f8ccccd | `1.10000003f` | line |
| gamez/zCamera/camera.cpp | 1208 | UpdateDeathCamState__10CAppCameraFf 0x1e9620 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zCamera/camera.cpp | 1379 1395 | GetDeadCamPoints__10CAppCameraFP6CPnt3DP6CPnt3DP7CMatrixf 0x1e8fc0 | `0.8725f` | 3f5f5c28 | 3f5f5c29 | `0.872500003f` | function |
| gamez/zCamera/camera.cpp | 1400 | GetDeadCamPoints__10CAppCameraFP6CPnt3DP6CPnt3DP7CMatrixf 0x1e8fc0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zCamera/camera.cpp | 1402 | GetDeadCamPoints__10CAppCameraFP6CPnt3DP6CPnt3DP7CMatrixf 0x1e8fc0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zCamera/camera.cpp | 1403 | GetDeadCamPoints__10CAppCameraFP6CPnt3DP6CPnt3DP7CMatrixf 0x1e8fc0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| gamez/zCamera/camera.cpp | 1415 | GetDeadCamPoints__10CAppCameraFP6CPnt3DP6CPnt3DP7CMatrixf 0x1e8fc0 | `0.8725f` | 3f5f5c28 | 3f5f5c29 | `0.872500003f` | line |
| gamez/zCamera/camera.cpp | 1419 | GetDeadCamPoints__10CAppCameraFP6CPnt3DP6CPnt3DP7CMatrixf 0x1e8fc0 | `6.2925f` | 40c95c28 | 40c95c29 | `6.29250002f` | line |
| gamez/zCamera/camera.cpp | 1428 1431 | GetDeadCamPoints__10CAppCameraFP6CPnt3DP6CPnt3DP7CMatrixf 0x1e8fc0 | `3.1415927f` | 40490fda | 40490fdb | `3.14159275f` | line |
| gamez/zCamera/zcam_main.cpp | 170 | __ct__Q23zdb7CCameraFv 0x1e7780 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zCamera/zcam_main.cpp | 174 | __ct__Q23zdb7CCameraFv 0x1e7780 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | function |
| gamez/zCamera/zcam_main.cpp | 653 | CmdTickParams__Q23zdb7CCameraFP14_zanim_cmd_hdrPf 0x1e5570 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zCamera/zcam_main.cpp | 656 | CmdTickParams__Q23zdb7CCameraFP14_zanim_cmd_hdrPf 0x1e5570 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | function |
| gamez/zCamera/zcam_update.cpp | 59 | GetFogVisibility__Q23zdb7CCameraCFPC6CPnt3DPC6CPnt3D 0x1e85f0 | `1.0f / 255.0f` | 3b808080 (folded) | 3b808081 | `0.00392156886f` | line |
| gamez/zCamera/zcam_update.cpp | 159 | Update__Q23zdb7CCameraFQ23zdb13tag_ZCAM_TYPE 0x1e7f30 | `0.785f` | 3f48f5c2 | 3f48f5c3 | `0.785000027f` | function |
| gamez/zCamera/zcam_update.cpp | 181 | Update__Q23zdb7CCameraFQ23zdb13tag_ZCAM_TYPE 0x1e7f30 | `1.0001f` | 3f800346 | 3f800347 | `1.00010002f` | line |
| gamez/zCharacter/char_type.cpp | 282 341 | Open__14CCharacterTypeFPCc 0x24a4c0 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zCharacter/char_type.cpp | 342 343 | Open__14CCharacterTypeFPCc 0x24a4c0 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | function |
| gamez/zCharacter/char_type.cpp | 538 | __ct__14CCharacterTypeFPCcPC14CCharacterType 0x249790 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zCharacter/char_type.cpp | 539 | __ct__14CCharacterTypeFPCcPC14CCharacterType 0x249790 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zCharacter/char_type.cpp | 540 | __ct__14CCharacterTypeFPCcPC14CCharacterType 0x249790 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zCharacter/char_type.cpp | 543 | __ct__14CCharacterTypeFPCcPC14CCharacterType 0x249790 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| gamez/zCharacter/char_type.cpp | 546 | __ct__14CCharacterTypeFPCcPC14CCharacterType 0x249790 | `0.075f` | 3d999999 | 3d99999a | `0.075000003f` | line |
| gamez/zCharacter/zchar.h | 58 | - | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | run (DYN +0x198) |
| gamez/zCharacter/zchar.h | 61 | - | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | run (DYN +0x1a4) |
| gamez/zCharacter/zchar.h | 62 | - | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | run (DYN +0x1a8) |
| gamez/zCharacter/zchar.h | 241 | - | `0.64278f` | 3f248d3a | 3f248d3b | `0.642780006f` | overwritten by Load (cos of the rdr angle) |
| gamez/zFTS/fts_mission.cpp | 931 | PreOpen__8CMissionFPCc 0x1f8750 | `2.2f` | 400ccccc | 400ccccd | `2.20000005f` | line |
| gamez/zFTS/fts_mission.cpp | 932 | PreOpen__8CMissionFPCc 0x1f8750 | `0.55f` | 3f0ccccc | 3f0ccccd | `0.550000012f` | line |
| gamez/zFTS/fts_mission.cpp | 1030 | Open__8CMissionFPCci 0x1f7f50 | `0.98f` | 3f7ae147 | 3f7ae148 | `0.98000002f` | line |
| gamez/zFTS/fts_mission.cpp | 1652 | Tick__8CMissionFf 0x1f6b40 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zFTS/fts_mission.cpp | 1968 | OnMissionComplete__8CMissionF13MISSION_STATE 0x1f6200 | `0.98f` | 3f7ae147 | 3f7ae148 | `0.98000002f` | line |
| gamez/zFTS/fts_mission.cpp | 2008 2008 | FadeToEndMissionTick__8CMissionFf 0x1f60a0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zFTS/fts_mission.cpp | 2009 | FadeToEndMissionTick__8CMissionFf 0x1f60a0 | `1.1f` | 3f8ccccc | 3f8ccccd | `1.10000003f` | function |
| gamez/zFTS/fts_mission.cpp | 2061 | FadeToEndMission__8CMissionFfi 0x1f5ff0 | `0.98f` | 3f7ae147 | 3f7ae148 | `0.98000002f` | line |
| gamez/zFTS/fts_mission.cpp | 2281 | ftsFixupAiMap__FP6CAiMap 0x1f47d0 | `0.01745329f` | 3c8efa33 | 3c8efa35 | `0.0174532924f` | function |
| gamez/zFTS/fts_mission.cpp | 2308 | ftsFixupAiMap__FP6CAiMap 0x1f47d0 | `0.01745329f` | 3c8efa33 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zFTS/fts_mission.cpp | 2835 | MasterStartGame__9CZNetGameFv 0x1f3910 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zFTS/fts_mission.cpp | 2868 | GetGameTime__8CMissionFv 0x1f37d0 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zFTS/fts_mission.cpp | 2916 2934 | DecrementRoundClockSec__9CZNetGameFi 0x1f35d0 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zFTS/fts_net_game.cpp | 317 | UpdateLocalGame__11CZGameStateFP9CZNetGame 0x205e70 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zFTS/fts_remote.cpp | 268 | zRemoteClientConnectsCallback__FiiPCc 0x2042d0 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zFTS/fts_remote.cpp | 472 | HitPacketHandler__FiiiPv 0x203950 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | function |
| gamez/zFTS/fts_remote.cpp | 851 855 859 | SendWeaponPUMessage__FUsUsP6CPnt3DP5CQuat 0x202c70 | `3.14159274f` | 40490fda | 40490fdb | `3.14159275f` | line |
| gamez/zFTS/fts_remote.cpp | 878 879 | WeaponPUPacketHandler__FiiiPv 0x202ac0 | `3.14159274f` | 40490fda | 40490fdb | `3.14159275f` | function |
| gamez/zFTS/fts_remote.cpp | 880 | WeaponPUPacketHandler__FiiiPv 0x202ac0 | `3.14159274f` | 40490fda | 40490fdb | `3.14159275f` | line |
| gamez/zGrid/grid_cell.cpp | 33 | __ct__Q23zdb5CCellFPC6CPnt3Df 0x217380 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zGrid/grid_clutter.cpp | 299 313 | Render__Q23zdb8CClutterFP6CPnt3D 0x218a10 | `0.008f` | 3c03126e | 3c03126f | `0.00800000038f` | line |
| gamez/zGrid/grid_clutter.cpp | 580 590 | ClutterTick__Q23zdb19CClutterAnimManagerFPQ23zdb8CClutter 0x217ba0 | `5.01f` | 40a051eb | 40a051ec | `5.01000023f` | line |
| gamez/zGrid/grid_clutter.cpp | 654 | l_Tick__Q23zdb19CClutterAnimManagerFfPv 0x217840 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | line |
| gamez/zInput/remote_control.cpp | 218 | PostMortemPreTick__11CRemoteCtrlFf 0x2ce220 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zInput/zin_main.cpp | 131 132 | __ct__4CPadFii 0x21b3a0 | `1.5626f` | 3fc80346 | 3fc80347 | `1.56260002f` | line |
| gamez/zInput/zin_main.cpp | 170 | Flush__4CPadFv 0x21b2b0 | `1.0f / 30.0f` | 3d088888 (folded) | 3d088889 | `0.0333333351f` | line |
| gamez/zInput/zin_main.cpp | 204 | SetAcceleration__4CPadFif 0x21b0f0 | `0.85f` | 3f599999 | 3f59999a | `0.850000024f` | line |
| gamez/zInput/zin_main.cpp | 223 | GetAcceleration__4CPadFi 0x21b020 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zInput/zin_main.cpp | 257 | SetPreset__4CPadFii 0x21af40 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zInput/zin_main.cpp | 259 265 271 | SetPreset__4CPadFii 0x21af40 | `0.33f` | 3ea8f5c2 | 3ea8f5c3 | `0.330000014f` | line |
| gamez/zInput/zin_main.cpp | 281 | ReadControlFile__10CStickTypeFi 0x21ae80 | `0.33f` | 3ea8f5c2 | 3ea8f5c3 | `0.330000014f` | line |
| gamez/zInput/zin_main.cpp | 289 | ReadControlFile__10CStickTypeFi 0x21ae80 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zInput/zin_main.cpp | 295 | ReadControlFile__10CStickTypeFi 0x21ae80 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zInput/zin_main.cpp | 377 | Dilate__4CPadFRfRfi 0x21aa50 | `0.28f` | 3e8f5c28 | 3e8f5c29 | `0.280000002f` | not emitted |
| gamez/zInput/zin_main.cpp | 570 571 572 573 | Tick__4CPadFf 0x219aa0 | `(1.0f / 127.5f)` | 3c008080 (folded) | 3c008081 | `0.00784313772f` | line |
| gamez/zInput/zinput.h | 242 | - | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zIntersect/int_material.cpp | 194 | CreateDefaultMaterials__16CMaterialExArrayFv 0x21ede0 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zMath/zmath.h | 56 | - | `0.01745329f` | 3c8efa33 | 3c8efa35 | `0.0174532924f` | line (23 uses, seal_dyn.cpp) |
| gamez/zMath/zmath_main.cpp | 491 | SlerpFaster__5CQuatCFPC5CQuatfP5CQuat 0x220a20 | `0.87f` | 3f5eb851 | 3f5eb852 | `0.870000005f` | line |
| gamez/zMath/zmath_main.cpp | 516 | SlerpFaster__5CQuatCFPC5CQuatfP5CQuat 0x220a20 | `0.004f` | 3b83126e | 3b83126f | `0.00400000019f` | line |
| gamez/zMath/zmath_trig.cpp | 41 | init_trig_table__Fv 0x223050 | `0.024543693f` | 3cc90fda | 3cc90fdb | `0.0245436933f` | line |
| gamez/zNode/node_main.cpp | 1044 | SetTexture__Q23zdb9CLightMapFPQ23zdb8CTexture 0x226750 | `1.414f` | 3fb4fdf3 | 3fb4fdf4 | `1.41400004f` | line |
| gamez/zNode/node_util.cpp | 18 | DEFAULT_CLOSESTNODE_DOT 0x44fb80 | `1.134464f` | 3f91361d | 3f91361e | `1.13446403f` | not emitted |
| gamez/zNode/node_world.cpp | 186 | __ct__Q23zdb6CWorldFPCc 0x230030 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zNode/node_world.cpp | 193 212 213 | __ct__Q23zdb6CWorldFPCc 0x230030 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| gamez/zNode/node_world.cpp | 211 | __ct__Q23zdb6CWorldFPCc 0x230030 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zNode/node_world.cpp | 226 | __ct__Q23zdb6CWorldFPCc 0x230030 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zNode/node_world.cpp | 227 228 233 235 | __ct__Q23zdb6CWorldFPCc 0x230030 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | function |
| gamez/zNode/node_world.cpp | 236 | __ct__Q23zdb6CWorldFPCc 0x230030 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zNode/node_world.cpp | 1405 1415 | CmdParseWind__5CWindFP5_zrdr 0x22cd40 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zNode/node_world.cpp | 1603 | Tick__5CWindFf 0x22c720 | `3.1415927f` | 40490fda | 40490fdb | `3.14159275f` | line |
| gamez/zNode/node_world.cpp | 1626 | Tick__5CWindFf 0x22c720 | `0.011111111f` | 3c360b60 | 3c360b61 | `0.0111111114f` | line |
| gamez/zNode/node_world.cpp | 1697 | Reset__5CWindFv 0x22c4f0 | `0.08726646f` | 3db2b8c1 | 3db2b8c2 | `0.0872664601f` | line |
| gamez/zParticle/zparticle.cpp | 82 | Open__8ParticleFv 0x234310 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zParticle/zparticle.cpp | 247 | CreateVisuals__8ParticleFP6CPnt3DP6CPnt3DP6CPnt3D6CPnt3D6CPnt3D6CPnt3D7CMatrixPQ23zdb10CTexHandleP6CPnt4DfPQ23zdb6CModelP6CPnt3DP6CPnt3DP6CPnt3DPQ28Particle5Propsf 0x232ea0 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zParticle/zparticle.cpp | 247 | CreateVisuals__8ParticleFP6CPnt3DP6CPnt3DP6CPnt3D6CPnt3D6CPnt3D6CPnt3D7CMatrixPQ23zdb10CTexHandleP6CPnt4DfPQ23zdb6CModelP6CPnt3DP6CPnt3DP6CPnt3DPQ28Particle5Propsf 0x232ea0 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zParticle/zparticle.cpp | 268 | CreateVisuals__8ParticleFP6CPnt3DP6CPnt3DP6CPnt3D6CPnt3D6CPnt3D6CPnt3D7CMatrixPQ23zdb10CTexHandleP6CPnt4DfPQ23zdb6CModelP6CPnt3DP6CPnt3DP6CPnt3DPQ28Particle5Propsf 0x232ea0 | `0.33333334f` | 3eaaaaaa | 3eaaaaab | `0.333333344f` | line |
| gamez/zParticle/zparticle.h | 394 | - | `0.166666f` | 3e2aaa7d | 3e2aaa7e | `0.166666002f` | line |
| gamez/zParticle/zparticle.h | 394 | - | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zParticle/zparticle_buf.cpp | 457 | DrawRotated__Q28Particle13BufferElementFRA4_A4_f 0x234c90 | `2.2f` | 400ccccc | 400ccccd | `2.20000005f` | not emitted |
| gamez/zParticle/zparticle_instance.cpp | 662 | Tick__Q28Particle20Destruction_InstanceFf 0x236390 | `0.166666f` | 3e2aaa7d | 3e2aaa7e | `0.166666002f` | line |
| gamez/zParticle/zparticle_instance.cpp | 662 | Tick__Q28Particle20Destruction_InstanceFf 0x236390 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zParticle/zparticle_source.cpp | 127 | Default__Q28Particle6SourceFv 0x23a860 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zRender/zrndr_pipe.cpp | 1102 | RenderNode__5CPipeFPQ23zdb5CNodeQ23zdb12tag_ZVIS_FOV 0x243730 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zRender/zrndr_pipe.cpp | 1229 | RenderMesh__5CPipeFPQ23zdb5CNodePQ23zdb5CMeshP7CMatrixQ23zdb12tag_ZVIS_FOV 0x2431a0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zRender/zrndr_pipe.cpp | 1300 | SaveDelayedNode__5CPipeFP7CMatrixPQ23zdb5CNodeQ23zdb12tag_ZVIS_FOV 0x242f50 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zRender/zrndr_pipe.cpp | 1734 | RenderUiNodeRecursive__5CPipeFPQ23zdb5CNode 0x241ab0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSeal/seal.cpp | 256 | stoppedV__10CZSealBody 0x450d28 | `0.029999999329447746f` | 3cf5c28e | 3cf5c28f | `0.0299999994f` | unit asm |
| gamez/zSeal/seal.cpp | 260 | stoppedV__10CZSealBody 0x450d28 | `0.025f` | 3ccccccc | 3ccccccd | `0.0250000004f` | unit asm |
| gamez/zSeal/seal.cpp | 264 | stoppedV__10CZSealBody 0x450d28 | `1.09f` | 3f8b851e | 3f8b851f | `1.09000004f` | unit asm |
| gamez/zSeal/seal.cpp | 611 | __ct__10CZSealBodyFPQ23zdb5CNodeP14CCharacterType 0x2577d0 | `0.707f` | 3f34fdf3 | 3f34fdf4 | `0.707000018f` | not emitted |
| gamez/zSeal/seal.cpp | 924 | __ct__10CZSealBodyFPQ23zdb5CNodeP14CCharacterType 0x2577d0 | `1.09f` | 3f8b851e | 3f8b851f | `1.09000004f` | line |
| gamez/zSeal/seal.cpp | 1510 | Tick__10CZSealBodyFf 0x255870 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| gamez/zSeal/seal.cpp | 1606 | Tick__10CZSealBodyFf 0x255870 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSeal/seal.cpp | 1628 1628 1628 | Tick__10CZSealBodyFf 0x255870 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal.cpp | 1843 | UpdateAiEvent__10CZSealBodyFv 0x255400 | `0.67f` | 3f2b851e | 3f2b851f | `0.670000017f` | function |
| gamez/zSeal/seal.cpp | 1845 | UpdateAiEvent__10CZSealBodyFv 0x255400 | `0.33f` | 3ea8f5c2 | 3ea8f5c3 | `0.330000014f` | function |
| gamez/zSeal/seal.cpp | 1849 | UpdateAiEvent__10CZSealBodyFv 0x255400 | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | function |
| gamez/zSeal/seal.cpp | 2092 2181 | CollidePlayers__10CZSealBodyFR6CPnt3D 0x2545e0 | `19.1f` | 4198cccc | 4198cccd | `19.1000004f` | line |
| gamez/zSeal/seal.cpp | 2287 | HandleSliding__10CZSealBodyFf 0x254130 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal.cpp | 2427 2427 2427 | ComputeNextPosition__10CZSealBodyFf 0x250f40 | `0.0005f` | 3a03126e | 3a03126f | `0.000500000024f` | line |
| gamez/zSeal/seal.cpp | 2436 | ComputeNextPosition__10CZSealBodyFf 0x250f40 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zSeal/seal.cpp | 2466 | ComputeNextPosition__10CZSealBodyFf 0x250f40 | `19.1f` | 4198cccc | 4198cccd | `19.1000004f` | line |
| gamez/zSeal/seal.cpp | 2522 | ComputeNextPosition__10CZSealBodyFf 0x250f40 | `9.55f` | 4118cccc | 4118cccd | `9.5500002f` | line |
| gamez/zSeal/seal.cpp | 2527 | ComputeNextPosition__10CZSealBodyFf 0x250f40 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal.cpp | 2528 | ComputeNextPosition__10CZSealBodyFf 0x250f40 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | line |
| gamez/zSeal/seal.cpp | 2609 2610 2683 | ComputeNextPosition__10CZSealBodyFf 0x250f40 | `1.1f` | 3f8ccccc | 3f8ccccd | `1.10000003f` | function |
| gamez/zSeal/seal.cpp | 2643 | ComputeNextPosition__10CZSealBodyFf 0x250f40 | `1.1f` | 3f8ccccc | 3f8ccccd | `1.10000003f` | line |
| gamez/zSeal/seal.cpp | 2678 | ComputeNextPosition__10CZSealBodyFf 0x250f40 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal.cpp | 2729 | ComputeNextPosition__10CZSealBodyFf 0x250f40 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zSeal/seal.cpp | 2821 | HandleWeaponIntersect__10CZSealBodyFv 0x250a80 | `1.1f` | 3f8ccccc | 3f8ccccd | `1.10000003f` | line |
| gamez/zSeal/seal.cpp | 2877 | HandleWeaponIntersect__10CZSealBodyFv 0x250a80 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal.cpp | 3020 | PostComputeNextPosition__10CZSealBodyFf 0x24fc10 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zSeal/seal.cpp | 3051 | PostComputeNextPosition__10CZSealBodyFf 0x24fc10 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | function |
| gamez/zSeal/seal.cpp | 3179 | NormalizeToTerrain__10CZSealBodyFv 0x24f9a0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| gamez/zSeal/seal.cpp | 3180 | NormalizeToTerrain__10CZSealBodyFv 0x24f9a0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | function |
| gamez/zSeal/seal.cpp | 3267 | OnDeath__10CZSealBodyFv 0x24f6d0 | `0.18f` | 3e3851eb | 3e3851ec | `0.180000008f` | line |
| gamez/zSeal/seal.cpp | 3327 | SetHealth__10CZSealBodyFf15SEAL_DEATH_TYPE 0x24f590 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| gamez/zSeal/seal.cpp | 3613 | ExecuteAction_CQBAttack__10CZSealBodyFP10CZSealBody 0x24ed60 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal.cpp | 4332 | TickHeartbeat__10CZSealBodyFv 0x24d6e0 | `0.33f` | 3ea8f5c2 | 3ea8f5c3 | `0.330000014f` | line |
| gamez/zSeal/seal.cpp | 4334 | TickHeartbeat__10CZSealBodyFv 0x24d6e0 | `0.66f` | 3f28f5c2 | 3f28f5c3 | `0.660000027f` | line |
| gamez/zSeal/seal_ai.cpp | 378 | accelRate 0x43a390 | `0.44999998807907104f` | 3ee66665 | 3ee66666 | `0.449999989f` | unit asm |
| gamez/zSeal/seal_ai.cpp | 393 | minTurnAngle__2ai 0x474f34 | `0.5235987901687622f` | 3f060a91 | 3f060a92 | `0.523598791f` | unit asm |
| gamez/zSeal/seal_ai.cpp | 417 | aiAccuracyAngle__11CSealCtrlAi 0x474f58 | `0.2617993950843811f` | 3e860a91 | 3e860a92 | `0.261799396f` | unit asm |
| gamez/zSeal/seal_ai.cpp | 1073 | __ct__11CSealCtrlAiFv 0x26b1c0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_ai.cpp | 1074 | __ct__11CSealCtrlAiFv 0x26b1c0 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zSeal/seal_ai.cpp | 1075 | __ct__11CSealCtrlAiFv 0x26b1c0 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_ai.cpp | 1078 | __ct__11CSealCtrlAiFv 0x26b1c0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| gamez/zSeal/seal_ai.cpp | 1081 | __ct__11CSealCtrlAiFv 0x26b1c0 | `0.075f` | 3d999999 | 3d99999a | `0.075000003f` | line |
| gamez/zSeal/seal_ai.cpp | 1100 | __ct__11CSealCtrlAiFv 0x26b1c0 | `0.7f` | 3f333333 | 3f333334 | `0.700000048f` | line |
| gamez/zSeal/seal_ai.cpp | 1101 | __ct__11CSealCtrlAiFv 0x26b1c0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_ai.cpp | 1102 | __ct__11CSealCtrlAiFv 0x26b1c0 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zSeal/seal_ai.cpp | 1341 | InitAiBrain__11CSealCtrlAiFv 0x26a8d0 | `0.01745329f` | 3c8efa33 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zSeal/seal_ai.cpp | 1582 1602 1615 | OnStunDamage__11CSealCtrlAiF9STUN_TYPEfPC6CPnt3D 0x269c00 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_ai.cpp | 1583 1603 1609 | OnStunDamage__11CSealCtrlAiF9STUN_TYPEfPC6CPnt3D 0x269c00 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zSeal/seal_ai.cpp | 1636 | OnStunDamage__11CSealCtrlAiF9STUN_TYPEfPC6CPnt3D 0x269c00 | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | line |
| gamez/zSeal/seal_ai.cpp | 1840 1842 | Tick__11CSealCtrlAiFf 0x268880 | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | function |
| gamez/zSeal/seal_ai.cpp | 1844 | Tick__11CSealCtrlAiFf 0x268880 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| gamez/zSeal/seal_ai.cpp | 1977 | PostTick__11CSealCtrlAiFf 0x268530 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zSeal/seal_ai.cpp | 2708 | LadderClimbTick__11CSealCtrlAiFf 0x266320 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_ai.cpp | 2874 | awareRangeMin 0x451160 | `0.6000000238418579f` | 3f199999 | 3f19999a | `0.600000024f` | unit asm |
| gamez/zSeal/seal_ai.cpp | 2877 | awareRangeMax 0x451180 | `0.6000000238418579f` | 3f199999 | 3f19999a | `0.600000024f` | unit asm |
| gamez/zSeal/seal_ai.cpp | 2951 | PathFollowTick__11CSealCtrlAiFf 0x264e20 | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | function |
| gamez/zSeal/seal_ai.cpp | 3086 | PathFollowTick__11CSealCtrlAiFf 0x264e20 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_ai.cpp | 3203 | PathFollowTick__11CSealCtrlAiFf 0x264e20 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_ai.cpp | 3487 | CreepTick__9CSealCtrlFf 0x2646a0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_ai.cpp | 3734 3742 | SelectFireParams__11CSealCtrlAiFv 0x263a30 | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | line |
| gamez/zSeal/seal_ai.cpp | 3736 3744 | SelectFireParams__11CSealCtrlAiFv 0x263a30 | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | function |
| gamez/zSeal/seal_ai.cpp | 3740 | SelectFireParams__11CSealCtrlAiFv 0x263a30 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | line |
| gamez/zSeal/seal_ai.cpp | 3743 | SelectFireParams__11CSealCtrlAiFv 0x263a30 | `0.099999994f` | 3dcccccb | 3dcccccc | `0.0999999941f` | line |
| gamez/zSeal/seal_ai.cpp | 3804 | AttackTick__11CSealCtrlAiFfb 0x2626c0 | `0.999848f` | 3f7ff609 | 3f7ff60a | `0.999848009f` | function |
| gamez/zSeal/seal_ai.cpp | 3883 | AttackTick__11CSealCtrlAiFfb 0x2626c0 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zSeal/seal_ai.cpp | 4058 | FireWhenReady__11CSealCtrlAiFR13AI_FIREPARAMSf 0x2624b0 | `0.98f` | 3f7ae147 | 3f7ae148 | `0.98000002f` | function |
| gamez/zSeal/seal_ai.cpp | 4104 | FireWhenReady__11CSealCtrlAiFR13AI_FIREPARAMSf 0x2624b0 | `0.98f` | 3f7ae147 | 3f7ae148 | `0.98000002f` | line |
| gamez/zSeal/seal_ai.cpp | 4156 4168 4180 4191 | ChooseWeapon__11CSealCtrlAiFR10CAiWepHint 0x261eb0 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_ai.cpp | 4279 | SetStanceDelayed__11CSealCtrlAiF11SEAL_STANCEf 0x261ac0 | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | line |
| gamez/zSeal/seal_ai.cpp | 4279 | SetStanceDelayed__11CSealCtrlAiF11SEAL_STANCEf 0x261ac0 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zSeal/seal_ai.cpp | 4327 | DoSetStance__11CSealCtrlAiF11SEAL_STANCE 0x261740 | `0.07f` | 3d8f5c28 | 3d8f5c29 | `0.0700000003f` | line |
| gamez/zSeal/seal_ai.cpp | 4813 | SetAiAware__11CSealCtrlAiF8AI_AWAREPC6CPnt3D 0x2602d0 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zSeal/seal_ai.cpp | 5302 | ComputeProjectileFireParams__11CSealCtrlAiFR13AI_FIREPARAMS 0x25e7b0 | `0.8726646f` | 3f5f66f2 | 3f5f66f3 | `0.872664631f` | not emitted |
| gamez/zSeal/seal_ai.cpp | 5332 | ComputeProjectileFireParams__11CSealCtrlAiFR13AI_FIREPARAMS 0x25e7b0 | `0.707f` | 3f34fdf3 | 3f34fdf4 | `0.707000018f` | line |
| gamez/zSeal/seal_ai.cpp | 5696 | Tick__10CAiSDeployFfP11CSealCtrlAi 0x25d110 | `1.11f` | 3f8e147a | 3f8e147b | `1.11000002f` | line |
| gamez/zSeal/seal_ai.cpp | 6030 6048 | SetReturnVelocity__11CSealCtrlAiFP12CZProjectileP6CPnt3Db 0x25c860 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_ai.cpp | 6041 | SetReturnVelocity__11CSealCtrlAiFP12CZProjectileP6CPnt3Db 0x25c860 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_ai.cpp | 6041 | SetReturnVelocity__11CSealCtrlAiFP12CZProjectileP6CPnt3Db 0x25c860 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zSeal/seal_ai.cpp | 6042 6042 6043 | SetReturnVelocity__11CSealCtrlAiFP12CZProjectileP6CPnt3Db 0x25c860 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | function |
| gamez/zSeal/seal_ai.cpp | 6043 | SetReturnVelocity__11CSealCtrlAiFP12CZProjectileP6CPnt3Db 0x25c860 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | function |
| gamez/zSeal/seal_ai.cpp | 6086 | Tick__11CAiSGrenadeFfP11CSealCtrlAi 0x25af40 | `0.56f` | 3f0f5c28 | 3f0f5c29 | `0.560000003f` | not emitted |
| gamez/zSeal/seal_ai.cpp | 6135 | Tick__11CAiSGrenadeFfP11CSealCtrlAi 0x25af40 | `2.9f` | 40399999 | 4039999a | `2.9000001f` | line |
| gamez/zSeal/seal_ai.cpp | 6143 | Tick__11CAiSGrenadeFfP11CSealCtrlAi 0x25af40 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | unit asm |
| gamez/zSeal/seal_ai.cpp | 6176 | Tick__11CAiSGrenadeFfP11CSealCtrlAi 0x25af40 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | unit asm |
| gamez/zSeal/seal_ai.cpp | 6215 | Tick__11CAiSGrenadeFfP11CSealCtrlAi 0x25af40 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_ai.cpp | 6280 | Tick__11CAiSGrenadeFfP11CSealCtrlAi 0x25af40 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_ai.cpp | 6403 6404 | Tick__11CAiSGrenadeFfP11CSealCtrlAi 0x25af40 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | function |
| gamez/zSeal/seal_ai.cpp | 6406 | Tick__11CAiSGrenadeFfP11CSealCtrlAi 0x25af40 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_ai.cpp | 6496 6501 | Tick__11CAiSGrenadeFfP11CSealCtrlAi 0x25af40 | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | line |
| gamez/zSeal/seal_ai.cpp | 6496 6501 | Tick__11CAiSGrenadeFfP11CSealCtrlAi 0x25af40 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zSeal/seal_ai.cpp | 6707 | Tick__10CAiSPursueFfP11CSealCtrlAi 0x259930 | `1.047198f` | 3f860a95 | 3f860a92 | `1.04719759f` | line |
| gamez/zSeal/seal_ai.cpp | 6976 | Tick__10CAiSPursueFfP11CSealCtrlAi 0x259930 | `1.48353f` | 3fbde44f | 3fbde44e | `1.48352981f` | line |
| gamez/zSeal/seal_ai.cpp | 6989 | Tick__10CAiSPursueFfP11CSealCtrlAi 0x259930 | `1.570796f` | 3fc90fd7 | 3fc90fdb | `1.57079638f` | line |
| gamez/zSeal/seal_aievent.cpp | 253 | HandleEvent__11CSealCtrlAiFPC8CAiEvent 0x2dcd60 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | function |
| gamez/zSeal/seal_aievent.cpp | 513 | HandleEvent__11CSealCtrlAiFPC8CAiEvent 0x2dcd60 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| gamez/zSeal/seal_aievent.cpp | 520 | HandleEvent__11CSealCtrlAiFPC8CAiEvent 0x2dcd60 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_aifollow.cpp | 587 | FollowTick__11CSealCtrlAiFf 0x2df1c0 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | unit asm |
| gamez/zSeal/seal_aifollow.cpp | 589 685 | FollowTick__11CSealCtrlAiFf 0x2df1c0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| gamez/zSeal/seal_aifollow.cpp | 656 | FollowTick__11CSealCtrlAiFf 0x2df1c0 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_aifollow.cpp | 683 | FollowTick__11CSealCtrlAiFf 0x2df1c0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_aifollow.cpp | 970 | FollowTick__11CSealCtrlAiFf 0x2df1c0 | `0.3490658f` | 3eb2b8c0 | 3eb2b8c2 | `0.349065841f` | line |
| gamez/zSeal/seal_airesponse.cpp | 117 | OnSignal__10CAiSShotAtFQ28CAiState6SIGNALP11CSealCtrlAi 0x2e8f90 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | line |
| gamez/zSeal/seal_airesponse.cpp | 117 | OnSignal__10CAiSShotAtFQ28CAiState6SIGNALP11CSealCtrlAi 0x2e8f90 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_airesponse.cpp | 172 | Tick__10CAiSShotAtFfP11CSealCtrlAi 0x2e8590 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_airesponse.cpp | 338 | Tick__10CAiSReloadFfP11CSealCtrlAi 0x2e8030 | `0.07f` | 3d8f5c28 | 3d8f5c29 | `0.0700000003f` | function |
| gamez/zSeal/seal_airesponse.cpp | 1288 1300 | Tick__9CAiSEventFfP11CSealCtrlAi 0x2e5e80 | `0.3490658f` | 3eb2b8c0 | 3eb2b8c2 | `0.349065841f` | line |
| gamez/zSeal/seal_aiscan.cpp | 96 | SetDefaultLookParams__9CSealCtrlF7AI_LOOK 0x2e4660 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| gamez/zSeal/seal_aiscan.cpp | 96 | SetDefaultLookParams__9CSealCtrlF7AI_LOOK 0x2e4660 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| gamez/zSeal/seal_aiscan.cpp | 125 139 | SetDefaultLookParams__9CSealCtrlF7AI_LOOK 0x2e4660 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_aiscan.cpp | 137 | SetDefaultLookParams__9CSealCtrlF7AI_LOOK 0x2e4660 | `0.7f` | 3f333333 | 3f333334 | `0.700000048f` | line |
| gamez/zSeal/seal_aiscan.cpp | 190 | SetLookDirW__9CSealCtrlF7AI_LOOKPC6CPnt3Db 0x2e4510 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_aiscan.cpp | 231 | SetLookDirR__9CSealCtrlF7AI_LOOKPC6CPnt3Db 0x2e4390 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_aiscan.cpp | 282 | ScanTick__9CSealCtrlFf 0x2e3bf0 | `0.97f` | 3f7851eb | 3f7851ec | `0.970000029f` | function |
| gamez/zSeal/seal_aiscan.cpp | 288 | ScanTick__9CSealCtrlFf 0x2e3bf0 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | unit asm |
| gamez/zSeal/seal_aistate.cpp | 777 | Tick__9CAiSAvoidFfP11CSealCtrlAi 0x2da4a0 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | line |
| gamez/zSeal/seal_aistate.cpp | 902 | Tick__8CAiSGotoFfP11CSealCtrlAi 0x2d9780 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| gamez/zSeal/seal_anim.cpp | 335 | CombineRotations__9CSealAnimFii 0x26d550 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | function |
| gamez/zSeal/seal_anim.cpp | 337 | CombineRotations__9CSealAnimFii 0x26d550 | `0.999f` | 3f7fbe76 | 3f7fbe77 | `0.999000013f` | function |
| gamez/zSeal/seal_anim.cpp | 404 | AnimOverlay__9CSealAnimFf 0x26d250 | `0.999f` | 3f7fbe76 | 3f7fbe77 | `0.999000013f` | function |
| gamez/zSeal/seal_anim.cpp | 408 | AnimOverlay__9CSealAnimFf 0x26d250 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | function |
| gamez/zSeal/seal_anim.cpp | 500 | SetVertical__10CZSealBodyFv 0x26cb90 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_body.cpp | 197 | PRONE_THROW_FRAC 0x474fcc | `0.6600000262260437f` | 3f28f5c2 | 3f28f5c3 | `0.660000027f` | unit asm |
| gamez/zSeal/seal_body.cpp | 200 | CROUCH_THROW_FRAC 0x474fd0 | `0.699999988079071f` | 3f333332 | 3f333333 | `0.699999989f` | unit asm |
| gamez/zSeal/seal_body.cpp | 209 | STAND_TOSS_FRAC 0x474fdc | `0.6899999976158142f` | 3f30a3d6 | 3f30a3d7 | `0.689999998f` | unit asm |
| gamez/zSeal/seal_body.cpp | 608 | PushBlend__10CZSealBodyF8AnimTypeib 0x27c090 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_body.cpp | 609 610 | PushBlend__10CZSealBodyF8AnimTypeib 0x27c090 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zSeal/seal_body.cpp | 618 | PushBlend__10CZSealBodyF8AnimTypeib 0x27c090 | `0.72f` | 3f3851eb | 3f3851ec | `0.720000029f` | line |
| gamez/zSeal/seal_body.cpp | 622 | PushBlend__10CZSealBodyF8AnimTypeib 0x27c090 | `0.62f` | 3f1eb851 | 3f1eb852 | `0.620000005f` | line |
| gamez/zSeal/seal_body.cpp | 966 | IsStopped__10CZSealBodyFfff 0x27b300 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_body.cpp | 1038 | InStateStand__10CZSealBodyFfff 0x27ab70 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_body.cpp | 1110 1112 | StandStill__10CZSealBodyFfff 0x27a7a0 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zSeal/seal_body.cpp | 1163 | StandTurning__10CZSealBodyFfff 0x27a5d0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_body.cpp | 1163 | StandTurning__10CZSealBodyFfff 0x27a5d0 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zSeal/seal_body.cpp | 1246 1255 | UpdateQuadrant__10CZSealBodyFRfRfb 0x27a250 | `2.8274333f` | 4034f4aa | 4034f4ab | `2.82743335f` | function |
| gamez/zSeal/seal_body.cpp | 1247 1254 | UpdateQuadrant__10CZSealBodyFRfRfb 0x27a250 | `0.31415927f` | 3ea0d97b | 3ea0d97c | `0.314159275f` | function |
| gamez/zSeal/seal_body.cpp | 1413 1415 | InStateCrouch__10CZSealBodyFfff 0x279740 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zSeal/seal_body.cpp | 1457 | InStateCrouch__10CZSealBodyFfff 0x279740 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_body.cpp | 1457 | InStateCrouch__10CZSealBodyFfff 0x279740 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zSeal/seal_body.cpp | 1468 1468 | InStateCrouch__10CZSealBodyFfff 0x279740 | `14.8f` | 416ccccc | 416ccccd | `14.8000002f` | line |
| gamez/zSeal/seal_body.cpp | 1468 | InStateCrouch__10CZSealBodyFfff 0x279740 | `107.3296f` | 42d6a8c1 | 42d6a8c3 | `107.329613f` | line |
| gamez/zSeal/seal_body.cpp | 1806 1827 | TurnControl__10CZSealBodyFff 0x278700 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zSeal/seal_body.cpp | 1808 1809 1828 1830 | TurnControl__10CZSealBodyFff 0x278700 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | function |
| gamez/zSeal/seal_body.cpp | 1820 | TurnControl__10CZSealBodyFff 0x278700 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_body.cpp | 1822 1823 | TurnControl__10CZSealBodyFff 0x278700 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| gamez/zSeal/seal_body.cpp | 2821 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `4.03f` | 4080f5c2 | 4080f5c3 | `4.03000021f` | function |
| gamez/zSeal/seal_body.cpp | 2823 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `3.13f` | 404851eb | 404851ec | `3.13000012f` | unit asm |
| gamez/zSeal/seal_body.cpp | 2823 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `13.8f` | 415ccccc | 415ccccd | `13.8000002f` | unit asm |
| gamez/zSeal/seal_body.cpp | 2825 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `6.05f` | 40c19999 | 40c1999a | `6.0500002f` | unit asm |
| gamez/zSeal/seal_body.cpp | 2825 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `15.59f` | 417970a3 | 417970a4 | `15.5900002f` | unit asm |
| gamez/zSeal/seal_body.cpp | 2825 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `1.96f` | 3ffae147 | 3ffae148 | `1.96000004f` | unit asm |
| gamez/zSeal/seal_body.cpp | 2827 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `15.05f` | 4170cccc | 4170cccd | `15.0500002f` | unit asm |
| gamez/zSeal/seal_body.cpp | 2827 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `0.97f` | 3f7851eb | 3f7851ec | `0.970000029f` | not emitted |
| gamez/zSeal/seal_body.cpp | 2829 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `2.39f` | 4018f5c2 | 4018f5c3 | `2.39000011f` | unit asm |
| gamez/zSeal/seal_body.cpp | 2831 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `7.8f` | 40f99999 | 40f9999a | `7.8000002f` | unit asm |
| gamez/zSeal/seal_body.cpp | 2831 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `10.13f` | 4122147a | 4122147b | `10.1300002f` | unit asm |
| gamez/zSeal/seal_body.cpp | 2833 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `11.47f` | 4137851e | 4137851f | `11.4700003f` | unit asm |
| gamez/zSeal/seal_body.cpp | 2833 | GetThrowAnim__10CZSealBodyFfR8AnimTypeRfRfR6CPnt3D 0x274ae0 | `6.48f` | 40cf5c28 | 40cf5c29 | `6.48000002f` | not emitted |
| gamez/zSeal/seal_body.cpp | 3209 | FlingBody__10CZSealBodyFPC6CPnt3Dff 0x273bd0 | `98.100006f` | 42c43333 | 42c43334 | `98.1000062f` | line |
| gamez/zSeal/seal_body.cpp | 4078 | Tick_0__10CZSealBodyFf 0x26ffd0 | `0.000375f` | 39c49ba5 | 39c49ba6 | `0.000375000004f` | line |
| gamez/zSeal/seal_body.cpp | 4109 4119 | BlendOverlayPreTick__10CZSealBodyFff 0x26fe50 | `0.79f` | 3f4a3d70 | 3f4a3d71 | `0.790000022f` | line |
| gamez/zSeal/seal_body.cpp | 4196 | CrouchToPickupBuddy__10CZSealBodyFP10CZSealBody 0x26f750 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_body.cpp | 4198 4199 | CrouchToPickupBuddy__10CZSealBodyFP10CZSealBody 0x26f750 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | function |
| gamez/zSeal/seal_body.cpp | 4234 4274 | CrouchToPickupBuddy__10CZSealBodyFP10CZSealBody 0x26f750 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSeal/seal_body.cpp | 4471 | StabBuddy__10CZSealBodyFP10CZSealBody 0x26ef00 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSeal/seal_cfg.cpp | 394 394 | ReadMotionRdr__10CZSealBodyFv 0x27eda0 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zSeal/seal_control.cpp | 230 | __ct__9CSealCtrlFv 0x288330 | `0.34906584f` | 3eb2b8c1 | 3eb2b8c2 | `0.349065841f` | line |
| gamez/zSeal/seal_control.cpp | 334 | OnWeaponHit__9CSealCtrlFPQ23zdb15IntersectStructP12CZProjectile 0x288010 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | line |
| gamez/zSeal/seal_control.cpp | 374 | OnStunDamage__9CSealCtrlF9STUN_TYPEfPC6CPnt3D 0x287e30 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | line |
| gamez/zSeal/seal_control.cpp | 387 | OnSetHealth__9CSealCtrlFff 0x287d30 | `0.18f` | 3e3851eb | 3e3851ec | `0.180000008f` | line |
| gamez/zSeal/seal_control.cpp | 508 | SetMenuState__9CSealCtrlF10MENU_STATE 0x287ab0 | `0.707107f` | 3f3504f6 | 3f3504f7 | `0.707107008f` | function |
| gamez/zSeal/seal_control.cpp | 523 | SetMenuState__9CSealCtrlF10MENU_STATE 0x287ab0 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zSeal/seal_control.cpp | 571 | PostTick__9CSealCtrlFf 0x287450 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| gamez/zSeal/seal_control.cpp | 606 | PostTick__9CSealCtrlFf 0x287450 | `0.95993114f` | 3f75be0c | 3f75be0b | `0.959931076f` | line |
| gamez/zSeal/seal_control.cpp | 610 | PostTick__9CSealCtrlFf 0x287450 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_control.cpp | 655 | Tick__9CSealCtrlFf 0x2872e0 | `0.001f` | 3a83126e | 3d4ccccd | `0.0500000008f` | function |
| gamez/zSeal/seal_control.cpp | 891 | ThrottlesPreTick__9CSealCtrlFP4CPadf 0x286950 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_control.cpp | 892 | ThrottlesPreTick__9CSealCtrlFP4CPadf 0x286950 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | function |
| gamez/zSeal/seal_control.cpp | 1886 | OnActionButton__9CSealCtrlFv 0x284560 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_ctrl.cpp | 283 | TickMPBomb__9CSealCtrlFf 0x2838f0 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_env.cpp | 312 | RESTRAINT_DOT 0x453a80 | `1.48353f` | 3fbde44f | 3fbde44e | `1.48352981f` | not emitted |
| gamez/zSeal/seal_env.cpp | 318 | CQB_DOT 0x453a90 | `1.134464f` | 3f91361d | 3f91361e | `1.13446403f` | not emitted |
| gamez/zSeal/seal_env.cpp | 413 | BuddyPickupRefpoint 0x5086d0 | `5.26f` | 40a851eb | 40a851ec | `5.26000023f` | unit asm |
| gamez/zSeal/seal_env.cpp | 584 | SealGetIntersect__10CZSealBodyFPC6CPnt3DPC6CPnt3D 0x2a3040 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSeal/seal_env.cpp | 1003 | CheckDIFwd1__10CZSealBodyFRfRfRf 0x2a1bb0 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | line |
| gamez/zSeal/seal_env.cpp | 1287 | HomingTick__10CZSealBodyFv 0x2a0f20 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_env.cpp | 1294 1301 | HomingTick__10CZSealBodyFv 0x2a0f20 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| gamez/zSeal/seal_env.cpp | 1470 1483 | AlignForClimb__10CZSealBodyFbR6CPnt3DR6CPnt3DP6CPnt3D 0x2a05f0 | `2.42f` | 401ae147 | 401ae148 | `2.42000008f` | line |
| gamez/zSeal/seal_env.cpp | 1494 | AlignForClimb__10CZSealBodyFbR6CPnt3DR6CPnt3DP6CPnt3D 0x2a05f0 | `15.6f` | 41799999 | 4179999a | `15.6000004f` | line |
| gamez/zSeal/seal_env.cpp | 1495 | AlignForClimb__10CZSealBodyFbR6CPnt3DR6CPnt3DP6CPnt3D 0x2a05f0 | `15.6f` | 41799999 | 4179999a | `15.6000004f` | function |
| gamez/zSeal/seal_env.cpp | 1558 | PreClimbLadderDown__10CZSealBodyFv 0x2a0350 | `0.347f` | 3eb1a9fb | 3eb1a9fc | `0.347000003f` | line |
| gamez/zSeal/seal_env.cpp | 1558 | PreClimbLadderDown__10CZSealBodyFv 0x2a0350 | `3.2f` | 404ccccc | 404ccccd | `3.20000005f` | line |
| gamez/zSeal/seal_env.cpp | 1873 | PostCheckDIDown__10CZSealBodyFRfRfRf 0x29eb00 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zSeal/seal_env.cpp | 2196 2206 | SetEyeLookDir__10CZSealBodyFffPC6CPnt3Df 0x29db50 | `0.24434611f` | 3e7a35dd | 3e7a35de | `0.244346113f` | line |
| gamez/zSeal/seal_env.cpp | 2255 | CalcGoalDir__10CZSealBodyFPC6CPnt3DPC6CPnt3DP6CPnt3Dffff 0x29d740 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_env.cpp | 2649 | PitchAnim__10CZSealBodyFP6CPnt3DP6CPnt3D 0x29c620 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_env.cpp | 2667 | PitchAnim__10CZSealBodyFP6CPnt3DP6CPnt3D 0x29c620 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zSeal/seal_env.cpp | 2694 | PitchAnim__10CZSealBodyFP6CPnt3DP6CPnt3D 0x29c620 | `0.999f` | 3f7fbe76 | 3f7fbe77 | `0.999000013f` | line |
| gamez/zSeal/seal_env.cpp | 2731 | OnWeaponHit__10CZSealBodyFPQ23zdb15IntersectStructP12CZProjectile 0x29c430 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSeal/seal_env.cpp | 2831 | HandleFallingDamage__10CZSealBodyFf 0x29bff0 | `0.33f` | 3ea8f5c2 | 3ea8f5c3 | `0.330000014f` | line |
| gamez/zSeal/seal_env.cpp | 3060 | DrawAutoReticle__FP6CPnt3D 0x29b650 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | function |
| gamez/zSeal/seal_env.cpp | 3221 | CheckDIShoot__10CZSealBodyFP6CPnt3DP7CMatrix 0x29a850 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSeal/seal_env.cpp | 3351 | CheckDIShoot__10CZSealBodyFP6CPnt3DP7CMatrix 0x29a850 | `0.008f` | 3c03126e | 3c03126f | `0.00800000038f` | line |
| gamez/zSeal/seal_env.cpp | 3352 3352 | CheckDIShoot__10CZSealBodyFP6CPnt3DP7CMatrix 0x29a850 | `0.008f` | 3c03126e | 3c03126f | `0.00800000038f` | function |
| gamez/zSeal/seal_env.cpp | 4496 | DamageRArm__10CZSealBodyFff 0x296910 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_env.cpp | 4608 | DamageLArm__10CZSealBodyFff 0x296420 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_env.cpp | 4648 | DamageHead__10CZSealBodyFP12CZProjectile 0x295ae0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSeal/seal_env.cpp | 4821 | DamageLLeg__10CZSealBodyFff 0x2955e0 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_env.cpp | 4933 | DamageRLeg__10CZSealBodyFff 0x2950a0 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_env.cpp | 5041 | DamageBody__10CZSealBodyFff 0x294b60 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_env.cpp | 5043 | DamageBody__10CZSealBodyFff 0x294b60 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_env.cpp | 5069 | GetHeadDamage__10CZSealBodyFff 0x294af0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSeal/seal_env.cpp | 5078 | GetLegDamage__10CZSealBodyFff 0x294a70 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_env.cpp | 5091 | GetArmDamage__10CZSealBodyFff 0x2949f0 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_env.cpp | 5104 | GetBodyDamage__10CZSealBodyFff 0x294940 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_env.cpp | 5106 | GetBodyDamage__10CZSealBodyFff 0x294940 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_env.cpp | 5131 5163 | UpdateHealth__10CZSealBodyF15DAMAGE_LOCATION15SEAL_DEATH_TYPE 0x294210 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_env.cpp | 5136 5176 | UpdateHealth__10CZSealBodyF15DAMAGE_LOCATION15SEAL_DEATH_TYPE 0x294210 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_env.cpp | 5165 | UpdateHealth__10CZSealBodyF15DAMAGE_LOCATION15SEAL_DEATH_TYPE 0x294210 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSeal/seal_env.cpp | 5915 | WeaponHitAnim__10CZSealBodyF8AnimType10SEAL_STATEb 0x291190 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | line |
| gamez/zSeal/seal_env.cpp | 6161 | SetBodyDamage__10CZSealBodyFi 0x290990 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| gamez/zSeal/seal_env.cpp | 6162 | SetBodyDamage__10CZSealBodyFi 0x290990 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| gamez/zSeal/seal_env.cpp | 6184 | SetHeadDamage__10CZSealBodyFi 0x290850 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | function |
| gamez/zSeal/seal_env.cpp | 6200 6201 | SetLArmDamage__10CZSealBodyFi 0x2906f0 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| gamez/zSeal/seal_env.cpp | 6218 6219 | SetRArmDamage__10CZSealBodyFi 0x290590 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| gamez/zSeal/seal_env.cpp | 6236 6237 | SetLLegDamage__10CZSealBodyFi 0x290430 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| gamez/zSeal/seal_env.cpp | 6254 6255 | SetRLegDamage__10CZSealBodyFi 0x2902d0 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| gamez/zSeal/seal_env.cpp | 6311 | GetNumExplosiveHits__10CZSealBodyFP12CZProjectile 0x28feb0 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | line |
| gamez/zSeal/seal_env.cpp | 6313 | GetNumExplosiveHits__10CZSealBodyFP12CZProjectile 0x28feb0 | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | line |
| gamez/zSeal/seal_env.cpp | 6317 | GetNumExplosiveHits__10CZSealBodyFP12CZProjectile 0x28feb0 | `0.85f` | 3f599999 | 3f59999a | `0.850000024f` | line |
| gamez/zSeal/seal_env.cpp | 6567 | DamageRandomLocation__10CZSealBodyFP12CZProjectile 0x28f490 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_env.cpp | 6580 | DamageRandomLocation__10CZSealBodyFP12CZProjectile 0x28f490 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSeal/seal_env.cpp | 6595 | DamageRandomLocation__10CZSealBodyFP12CZProjectile 0x28f490 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zSeal/seal_env.cpp | 6600 | DamageRandomLocation__10CZSealBodyFP12CZProjectile 0x28f490 | `0.55f` | 3f0ccccc | 3f0ccccd | `0.550000012f` | line |
| gamez/zSeal/seal_env.cpp | 6618 | DamageRandomLocation__10CZSealBodyFP12CZProjectile 0x28f490 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_kit.cpp | 1961 | TickReticule__5CZKitFf 0x2ab220 | `0.015384615f` | 3c7c0fc0 | 3c7c0fc1 | `0.0153846154f` | line |
| gamez/zSeal/seal_kit.cpp | 1967 | TickReticule__5CZKitFf 0x2ab220 | `0.015384615f` | 3c7c0fc0 | 3c7c0fc1 | `0.0153846154f` | function |
| gamez/zSeal/seal_kit.cpp | 2026 | TickReticule__5CZKitFf 0x2ab220 | `0.707107f` | 3f3504f6 | 3f3504f7 | `0.707107008f` | function |
| gamez/zSeal/seal_kit.cpp | 2041 | TickReticule__5CZKitFf 0x2ab220 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zSeal/seal_kit.cpp | 2047 | TickReticule__5CZKitFf 0x2ab220 | `0.95993114f` | 3f75be0c | 3f75be0b | `0.959931076f` | function |
| gamez/zSeal/seal_kit.cpp | 2144 | TickExplosives__5CZKitFf 0x2aa7a0 | `14.3f` | 4164cccc | 4164cccd | `14.3000002f` | line |
| gamez/zSeal/seal_kit.cpp | 2219 | TickExplosives__5CZKitFf 0x2aa7a0 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_kit.cpp | 2640 | GetFireDelay__5CZKitFv 0x2a97d0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_kit.cpp | 2650 | GetFireDelay__5CZKitFv 0x2a97d0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_kit.cpp | 2652 | GetFireDelay__5CZKitFv 0x2a97d0 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_kit.cpp | 2995 | HandleFireWeapon__5CZKitFiff 0x2a8a00 | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | line |
| gamez/zSeal/seal_kit.cpp | 3546 | SetCurAccuracy__5CZKitFv 0x2a75a0 | `0.707f` | 3f34fdf3 | 3f34fdf4 | `0.707000018f` | line |
| gamez/zSeal/seal_kit.cpp | 4428 4504 4527 | SniperTick__5CZKitFfR11CTargetMods 0x2a5040 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_kit.cpp | 4434 | SniperTick__5CZKitFfR11CTargetMods 0x2a5040 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zSeal/seal_kit.cpp | 4434 | SniperTick__5CZKitFfR11CTargetMods 0x2a5040 | `0.24f` | 3e75c28f | 3e75c290 | `0.24000001f` | line |
| gamez/zSeal/seal_kit.cpp | 4439 | SniperTick__5CZKitFfR11CTargetMods 0x2a5040 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_kit.cpp | 4445 4502 4527 | SniperTick__5CZKitFfR11CTargetMods 0x2a5040 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_kit.cpp | 4445 | SniperTick__5CZKitFfR11CTargetMods 0x2a5040 | `0.64f` | 3f23d70a | 3f23d70b | `0.640000046f` | line |
| gamez/zSeal/seal_kit.cpp | 4502 | SniperTick__5CZKitFfR11CTargetMods 0x2a5040 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | function |
| gamez/zSeal/seal_kit.cpp | 4529 | SniperTick__5CZKitFfR11CTargetMods 0x2a5040 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| gamez/zSeal/seal_sensors.cpp | 156 | vis_rate_max 0x475050 | `1.149999976158142f` | 3f933332 | 3f933333 | `1.14999998f` | unit asm |
| gamez/zSeal/seal_sensors.cpp | 923 | SensorPreTick__11CSealCtrlAiFf 0x2b21e0 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_sensors.cpp | 923 | SensorPreTick__11CSealCtrlAiFf 0x2b21e0 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | line |
| gamez/zSeal/seal_sensors.cpp | 1003 | OnSetTargetVisible__11CSealCtrlAiFR7CTargetbPQ23zdb11DiIntersect 0x2b1980 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| gamez/zSeal/seal_sensors.cpp | 1171 | SensorTick__9CSealCtrlFf 0x2b1110 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | function |
| gamez/zSeal/seal_sensors.cpp | 1350 | EnemyCallout__11CSealCtrlAiFPC7CTargetP7CEntity 0x2b0e90 | `0.15f` | 3e199999 | 3e19999a | `0.150000006f` | function |
| gamez/zSeal/seal_sensors.cpp | 1837 | PerturbAimVector__11CSealCtrlAiFP6CPnt3D 0x2afbc0 | `1.2f` | 3f999999 | 3f99999a | `1.20000005f` | line |
| gamez/zSeal/seal_squirm.cpp | 60 | __ct__15CSealCtrlSquirmFv 0x2e2e00 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_squirm.cpp | 61 | __ct__15CSealCtrlSquirmFv 0x2e2e00 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zSeal/seal_squirm.cpp | 63 | __ct__15CSealCtrlSquirmFv 0x2e2e00 | `0.7f` | 3f333333 | 3f333334 | `0.700000048f` | line |
| gamez/zSeal/seal_squirm.cpp | 217 245 246 | PreTick__15CSealCtrlSquirmFf 0x2e24f0 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zSeal/seal_squirm.cpp | 219 | PreTick__15CSealCtrlSquirmFf 0x2e24f0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_tasks.cpp | 787 | Parse__10CTFireModeFP5_zrdr 0x2bd3a0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_tasks.cpp | 788 | Parse__10CTFireModeFP5_zrdr 0x2bd3a0 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zSeal/seal_tasks.cpp | 1438 | Parse__8CTLookAtFP5_zrdr 0x2bb1c0 | `0.85f` | 3f599999 | 3f59999a | `0.850000024f` | line |
| gamez/zSeal/seal_tasks.cpp | 1975 | Begin__6CTMoveFP14_zanim_cmd_hdr 0x2b9c90 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | function |
| gamez/zSeal/seal_unit.cpp | 2404 | GetMyPointOutAnimStart__9CSealUnitFP10CZSealBody 0x2ced80 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| gamez/zSeal/seal_weapon.cpp | 68 | WepWaitOn__10CZSealBodyFv 0x2c0620 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zSeal/seal_weapon.cpp | 71 | WepWaitOn__10CZSealBodyFv 0x2c0620 | `100000.6f` | 47c3504c | 47c3504d | `100000.602f` | line |
| gamez/zSeal/seal_weapon.cpp | 94 94 | SetWeaponState__10CZSealBodyF12WEAPON_STATE 0x2c0490 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSeal/seal_weapon.cpp | 517 517 | UpdateAimDir__10CZSealBodyFb 0x2bf340 | `0.642f` | 3f245a1c | 3f245a1d | `0.64200002f` | line |
| gamez/zSeal/seal_weapon.cpp | 561 564 | CanProneAim__10CZSealBodyFv 0x2bf240 | `0.642f` | 3f245a1c | 3f245a1d | `0.64200002f` | line |
| gamez/zSeal/seal_weapon.cpp | 609 | CanAttainAim__10CZSealBodyFR6CPnt3D 0x2befc0 | `1.1f` | 3f8ccccc | 3f8ccccd | `1.10000003f` | line |
| gamez/zSoftImage/si_object.cpp | 177 | GetRotRaw__10CZSIObjectFiifP5CQuat 0x1dda00 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zSound/zsnd_csnd.cpp | 963 | PlaySound3D__4CSndFPC6CPnt3DfiP12CSndInstanceUi 0x2ecaf0 | `57.29578f` | 42652ee0 | 42652ee1 | `57.2957802f` | line |
| gamez/zSound/zsnd_csnd.cpp | 1099 | CalcVolPan__4CSndFPC6CPnt3DfPiPi 0x2ec7f0 | `57.29578f` | 42652ee0 | 42652ee1 | `57.2957802f` | line |
| gamez/zSound/zsnd_jukebox.cpp | 320 | PlayRandom__11CSndJukeboxF10MUSIC_MODE 0x2f1220 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zTexture/ztex_manager.cpp | 762 | doSetupBuffers__Q23zdb11CTexManagerFPCc 0x2fa3c0 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | line |
| gamez/zTexture/ztex_manager.cpp | 763 764 | doSetupBuffers__Q23zdb11CTexManagerFPCc 0x2fa3c0 | `0.001f` | 3a83126e | 3a83126f | `0.00100000005f` | function |
| gamez/zTwoD/c2dbitmap_poly.cpp | 241 | Rotate_Zaxis__13C2DBitmapPolyFf 0x2fdd30 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zTwoD/c2dbitmap_poly.cpp | 242 | Rotate_Zaxis__13C2DBitmapPolyFf 0x2fdd30 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | function |
| gamez/zTwoD/c2dline.cpp | 38 | __ct__7C2DLineFv 0x300980 | `4.6e-05f` | 3840f01f | 3840f020 | `4.60000011e-5f` | line |
| gamez/zTwoD/c2dstring.cpp | 145 | Tick__9C2DStringFf 0x302cf0 | `3.14f` | 4048f5c2 | 4048f5c3 | `3.14000011f` | line |
| gamez/zTwoD/ztwod.h | 736 | - | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zTwoD/ztwod_bitmap.cpp | 41 42 | __ct__9C2DBitmapFv 0x3039c0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zTwoD/ztwod_messageq.cpp | 161 | Init__12C2DMessage_QFP7C2DFontP8CRdrFile 0x200ba0 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | line |
| gamez/zTwoD/ztwod_messageq.cpp | 166 | Init__12C2DMessage_QFP7C2DFontP8CRdrFile 0x200ba0 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | function |
| gamez/zTwoD/ztwod_poly.cpp | 43 | __ct__7C2DPolyFv 0x3016d0 | `4.6e-05f` | 3840f01f | 3840f020 | `4.60000011e-5f` | line |
| gamez/zUI/zui.cpp | 353 | UiGetDirStickMoved__Fv 0x384380 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zUI/zui.cpp | 355 | UiGetDirStickMoved__Fv 0x384380 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zUI/zui.cpp | 590 | HandlePad__9CGameMenuFPC4CPad 0x382f00 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zUI/zui.cpp | 590 | HandlePad__9CGameMenuFPC4CPad 0x382f00 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zUI/zui.cpp | 1296 1297 | Tick__9CGameMenuFf 0x380700 | `0.05f` | 3d4ccccc | 3d4ccccd | `0.0500000008f` | function |
| gamez/zUI/zui_2d.cpp | 2474 | SetPressed__10CUIListBoxFv 0x38d4e0 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zUI/zui_2d.cpp | 4157 | Render__9C2DVisualFP7CMatrix 0x386ec0 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zUI/zui_2d.cpp | 4269 | HandlePad__10CUIMapCtrlFPC4CPadi 0x386840 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zUI/zui_2d.cpp | 4536 | TickZAnimCmd__10CUIMapCtrlFP14_zanim_cmd_hdrPfPb 0x3858e0 | `0.33333f` | 3eaaaa3a | 3eaaaa3b | `0.333330006f` | line |
| gamez/zVehicle/veh_turret.cpp | 96 | - | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zVehicle/veh_turret.cpp | 97 | - | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zVehicle/veh_turret.cpp | 160 161 | __ct__10CTurretDefFv 0x37ccf0 | `1.569051f` | 3fc8d6a9 | 3fc8d6aa | `1.56905103f` | line |
| gamez/zVehicle/veh_turret.cpp | 162 | __ct__10CTurretDefFv 0x37ccf0 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zVehicle/veh_turret.cpp | 195 201 | Parse__10CTurretDefFPCcP5_zrdr 0x37c550 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | line |
| gamez/zVehicle/veh_turret.cpp | 196 202 | Parse__10CTurretDefFPCcP5_zrdr 0x37c550 | `0.017453292f` | 3c8efa34 | 3c8efa35 | `0.0174532924f` | function |
| gamez/zVehicle/veh_turret.cpp | 665 | Fire__7CTurretFv 0x37ae70 | `0.36397f` | 3eba5a46 | 3eba5a47 | `0.363970012f` | line |
| gamez/zVehicle/vehicle_main.cpp | 132 | __ct__9AI_PARAMSFv 0x1a5270 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | line |
| gamez/zVehicle/vehicle_main.cpp | 133 | __ct__9AI_PARAMSFv 0x1a5270 | `0.6f` | 3f199999 | 3f19999a | `0.600000024f` | line |
| gamez/zVehicle/vehicle_main.cpp | 134 | __ct__9AI_PARAMSFv 0x1a5270 | `0.2f` | 3e4ccccc | 3e4ccccd | `0.200000003f` | line |
| gamez/zVehicle/vehicle_main.cpp | 137 | __ct__9AI_PARAMSFv 0x1a5270 | `0.8f` | 3f4ccccc | 3f4ccccd | `0.800000012f` | function |
| gamez/zVehicle/vehicle_main.cpp | 140 | __ct__9AI_PARAMSFv 0x1a5270 | `0.075f` | 3d999999 | 3d99999a | `0.075000003f` | line |
| gamez/zVisual/vis_bands.cpp | 380 | ColConvTo3D__FUi 0x310460 | `1.0f / 255.0f` | 3b808080 (folded) | 3b808081 | `0.00392156886f` | function |
| gamez/zVisual/vis_main.cpp | 1479 1485 | VuObjectSetup__Q23zdb7CVisualFP8_word128P16tag_ObjectHeader 0x30c350 | `0.33f` | 3ea8f5c2 | 3ea8f5c3 | `0.330000014f` | line |
| gamez/zVisual/vis_main.cpp | 1480 1481 1486 1487 | VuObjectSetup__Q23zdb7CVisualFP8_word128P16tag_ObjectHeader 0x30c350 | `0.33f` | 3ea8f5c2 | 3ea8f5c3 | `0.330000014f` | function |
| gamez/zWeapon/zwep_projectile.cpp | 277 | SetModelOrientation__12CZProjectileFbPC6CPnt3D 0x319b60 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zWeapon/zwep_projectile.cpp | 324 325 | SetModelOrientation__12CZProjectileFbPC6CPnt3D 0x319b60 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | function |
| gamez/zWeapon/zwep_projectile.cpp | 374 | PreTick__12CZProjectileFf 0x319850 | `9.8f` | 411ccccc | 411ccccd | `9.8000002f` | line |
| gamez/zWeapon/zwep_projectile.cpp | 385 | PreTick__12CZProjectileFf 0x319850 | `1.1f` | 3f8ccccc | 3f8ccccd | `1.10000003f` | line |
| gamez/zWeapon/zwep_projectile.cpp | 743 | HandleBounce__12CZProjectileFPQ23zdb15IntersectStructfP6CPnt3D 0x318750 | `0.99f` | 3f7d70a3 | 3f7d70a4 | `0.99000001f` | line |
| gamez/zWeapon/zwep_projectile.cpp | 755 | HandleBounce__12CZProjectileFPQ23zdb15IntersectStructfP6CPnt3D 0x318750 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zWeapon/zwep_projectile.cpp | 805 | HandleBounce__12CZProjectileFPQ23zdb15IntersectStructfP6CPnt3D 0x318750 | `0.4f` | 3ecccccc | 3ecccccd | `0.400000006f` | line |
| gamez/zWeapon/zwep_projectile.cpp | 848 | HandleShotgunImpact__12CZProjectileFPQ23zdb15IntersectStructffP6CPnt3D 0x3185d0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zWeapon/zwep_projectile.cpp | 898 935 | HandleImpact__12CZProjectileFPQ23zdb15IntersectStructffP6CPnt3D 0x318230 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zWeapon/zwep_weapon.cpp | 202 | __ct__8CZWeaponFv 0x31f850 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zWeapon/zwep_weapon.cpp | 346 | Fire__8CZWeaponFPQ23zdb5CNodeP6CZAmmoPC6CPnt3DPC6CPnt3DPC6CPnt3DP12CZProjectileiPQ23zdb6CModelff 0x31f2b0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zWeapon/zwep_weapon.cpp | 383 | Fire__8CZWeaponFPQ23zdb5CNodeP8CZWeaponP6CZAmmoPC6CPnt3DPC6CPnt3DPC6CPnt3DPQ23zdb6CModelP12CZProjectileUiff 0x31f100 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zWeapon/zwep_weapon.cpp | 416 | Fire__8CZWeaponFR12CZProjectile 0x31eff0 | `0.1f` | 3dcccccc | 3dcccccd | `0.100000002f` | line |
| gamez/zWeapon/zwep_weapon.cpp | 1116 | ReadDecalNames__10CZMarkListFPc 0x31dae0 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
| gamez/zWeapon/zwep_weapon.cpp | 1183 | ReadWeaponDecals__10CZMarkListFP5_zrdr 0x31d960 | `0.3f` | 3e999999 | 3e99999a | `0.300000012f` | line |
