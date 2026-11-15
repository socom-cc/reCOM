# Undeclared DWARF types and enums filed (socom-port-types, 2026-11-15)

The reference ELF's DWARF 1 names 435 game classes / structs / unions and 79 game enums (leaf-name
estimate, `build/typecov/typecov.py`, untracked). At HEAD d035c977 the source declared 382 of the
types and 68 of the enums by name; the estimate listed 53 type names and 11 enums as undeclared. Each
was read from the DWARF records (`port/tools/dev/dw.py`, the rows' function locals and members) and
the ELF's code, then classified:

- GAME: authored by the game; declared with the DWARF name, members, order, offsets and bitfields,
  placed by the units that carry the record and the functions that use it, and used where the code
  already meant it.
- PROVIDER: the Metrowerks MSL C++ library or an SDK / middleware library; not declared in `src/`.
- ALREADY: declared, but the estimate missed it (it only matches `class|struct|union Name {`).

Placement is the user's decision: each row says where the type went and why; "placement to confirm"
marks rows with a second, equally supported place.

## Numbers

| | before (HEAD d035c977) | after |
| --- | --- | --- |
| game types declared | 382 of 435 (87.8%) | 399 of 435 (91.7%) |
| game types with every member | 366 | 383 |
| game type members named | 3398 of 3518 | 3438 of 3518 |
| game enums declared | 68 of 79 | 72 of 79 |
| source definitions with no DWARF name | 615 | 612 (the ad-hoc `_zcam_params_track`, `_zcam_cmd_params`, `StatRow` replaced) |

The 36 names still listed after are the 2 ALREADY rows the estimate cannot see (`spore`, `line`),
`RSA_KEY` (a typedef) and the 33 PROVIDER / anonymous rows below. The 7 enums still listed are
PROVIDER.

## Types

Layout: `lay.py` + `laycheck.sh` under the port compiler (size and every non-bitfield member offset
against DWARF). Bitfields: DWARF 1's bit numbers here count from bit 0 of the word (CmdParseAcquire
0x1e74b0 sets `acquire` = 2, CmdParseSetRegions 0x1e72f0 sets `set_on` = 1), which is where GCC's
little-endian MIPS layout puts the first declared field.

| name | class | DWARF size | where (and why) | layout | uses now | flags |
| --- | --- | --- | --- | --- | --- | --- |
| `_camera_params_cmd` | GAME | 36 | `src/gamez/zCamera/zcam_main.cpp` (top, after the forward fence): only CU zcam_main.cpp; replaces the ad-hoc `_zcam_cmd_params` / `_zcam_params_track` / track enum (the same offsets) | match, 36 | CmdParseParams 0x1e6300 (flags, `run_time`, the six `*_offset` / `*_count` pairs), CmdBeginParams 0x1e61c0 (`save_params`, `fog_enabled_set` / `fog_enabled`, `fog_altitude_*`), CmdTickParams 0x1e5570 (`run_time`, tracks, `restore_params`) | the record's names are DWARF's; the comments after the members are the port's |
| `_camera_param_1d_data` | GAME | 8 | zcam_main.cpp, as above (DWARF type of the `lod` locals) | match | the LOD_MULTIPLIER keys (ParamsParseTrack / ParamsSample `<_camera_param_1d_data>`) | |
| `_camera_param_2d_data` | GAME | 12 | zcam_main.cpp (the `fov`, `clip`, `fog` locals) | match | FOV, CLIP, FOG_RANGE, FOG_ALTITUDE keys | |
| `_camera_param_3d_data` | GAME | 16 | zcam_main.cpp (the `clip_all` locals) | match | CLIP_ALL keys | |
| `_camera_control_cmd` | GAME | 8 | zcam_main.cpp (the `cmd` locals of CmdParseAcquire / CmdParseRelease / CmdTickControlSwitch) | match, `release` / `acquire` `int :1` | CmdTickControlSwitch 0x1e7470 (m8: release at the start of each camera, acquire at its end) | CmdParseRelease 0x1e7530 / CmdParseAcquire 0x1e74b0 are still placeholders returning NULL (the ELF callocs the 8-byte record and sets the bit). m8's cameras do not need them (their records come compiled in the disc's anims: the ticks run, the parsers are never called), so they were left: writing them is new behaviour for text-parsed anims |
| `_camera_set_regions_cmd` | GAME | 8 | zcam_main.cpp (CmdParseSetRegions' `cmd`) | match, `set_on` `int :1` | CmdTickSetRegions 0x1e72f0 (m8: OFF at the start, ON at the end) | CmdParseSetRegions 0x1e7320 is a placeholder returning NULL (ELF: record + ON / OFF): left, as above |
| `RequireCameraCollideFlag` | GAME | 1 | `src/gamez/zCamera/camera.cpp`: only CU camera.cpp (ClipCameraChord's `temp`, frame +748) | size 1 | ClipCameraChord 0x1ebbb0: `{ RequireCameraCollideFlag temp; }` for the back-to-back SetCameraCollideFlagRequired(true) / (false) at 0x1ebd0c / 0x1ebd14 | no symbol for its ctor / dtor: their bodies are inferred from those two calls. Placement to confirm: `zgrid.h` beside SetCameraCollideFlagRequired |
| `StatInfo` | GAME | 36 | `src/Apps/FTS/state/st_exit.cpp`, inside SetRoundStatUiVars 0x320b60 (replaces its ad-hoc `StatRow`, same members): only that function (`arrStatInfo[11]` at frame +176, copied from 0x43b600; the `info` references) | port 32: `pGetter` is DWARF fund type void, the MW 12-byte member pointer (+0x18..+0x24); a GCC member pointer is 8 bytes. `arrUiVars` is DWARF `char *[5]`, `const char *` here for the string-literal initialisers | SetRoundStatUiVars: `arrStatInfo`, `info.arrUiVars` / `iTotal` / `pGetter` | placement to confirm: function-local (as the ad-hoc struct was) or file scope (DWARF's name is not qualified by the function) |
| `CIntStr` | GAME | 16 | `src/Apps/FTS/hud/hud_scorepopup.cpp`, file scope after the forward fence: only CU hud_scorepopup.cpp; DWARF's name is not in the unit's anonymous namespace | match (`_ach[16]`) | CTeamDisplay::SetupTeam 0x421140 `strWins`, CTeamDisplay::AddRow 0x421510 `strFragsVal` / `strDeathsVal` (were `char[16]` buffers) | DWARF names no member function: the `sprintf("%d")` stays at the users (the original probably had an inline `CIntStr(int)`) |
| `SealDir` | GAME | 12 | `src/Apps/FTS/hud/hud_newhudmap.cpp`, file scope after the COverlayLine fence: only CU hud_newhudmap.cpp | `CPnt3D` base, 12 | SetupNorthIndicator 0x3c6a50 `dir`, CZNewHudMap::CalcNewMatrix 0x3c5510 (DWARF `direction`, port `dir`), GetScrollPermissions 0x3c50f0 / HandleScrolling 0x3c4950 `ptDir` (were `CPnt3D`) | DWARF names no member function: the negated z row is still filled at each user (probably an inline `SealDir(CZSealBody *)` in the original) |
| `RecoParams` | GAME (to confirm) | 8 | `src/Apps/FTS/game/orders.h`, after InternalRecoParams (the reco records' header) | not compiled into a check (unused); `int` + 1-byte `RecoGender`, 8 | none: no function, variable or member of reco.cpp uses it | it sits among the gsapi provider records of reco.cpp and the game's own copy is InternalRecoParams: it may be the provider's |
| `CMultiplayerMsgVec` | GAME | 12 | `src/gamez/zCharacter/zchar.h`, before CCharacterType (its member's class) | vector base, nothing of its own | `CCharacterType::MultiplayerMessages` (was `std::vector<MultiplayerMsg*>`) | element type from InitMultiplayerMessages (DWARF's vector base does not name it) |
| `CObjAnchorVec` | GAME | 12 | `src/gamez/zFTS/zfts.h`, after SObjectiveCam_Anchor (the forward declaration was there already) | vector base | `CMission::m_objanchor_vec` (was `std::vector<SObjectiveCam_Anchor>`) | |
| `CMissionCamList` | GAME | 12 | `src/gamez/zFTS/zfts.h`, after the CMissionCam forward declaration | list base | `CMission::m_missioncams` (was `std::list<CMissionCam*>`) | |
| `slist` | GAME | 12 | `src/gamez/zSeal/zseal.h`, file scope before CSealUnit (DWARF: not nested) | list base | `CSealUnit::m_seals`, `m_escortees`, `m_dead_guys` (were `std::list<CZSealBody*>`) | element type the port's (CZSealBody *) |
| `clist` | GAME | 12 | zseal.h, file scope before CSealUnit | list base | `CSealUnit::m_commands` (was `std::list<FT_COMMAND>`) | element type the port's (FT_COMMAND) |
| `CSealUnit::ulist` | GAME | 12 | zseal.h, nested in CSealUnit (DWARF qualified name) | list base | `CSealUnit::m_sub_units` (was `std::list<CSealUnit*>`) | |
| `spore` | ALREADY | 12 | `CAiMap::spore`, `src/gamez/zAI/zai.h` (defined out of class: `class CAiMap::spore`) | | | |
| `line` | ALREADY | 16 | `CAiMap::line`, zai.h (out of class) | | | |
| `RSA_KEY` | ALREADY (provider) | 64 | `src/rsa/rsadef.h` typedef (the RSA library's `{ RSA_NUMBER n, e; }`), the type of `CZNetwork::m_PubKey` in znet.h | | | DWARF's RSA_KEY (the game units' view) is `key[16]` of 4-byte longs, 64 bytes: a different layout from rsadef.h's; not changed |
| `_GSAPI_WORDIDLIST` | PROVIDER | 8 | gsapi speech SDK (`u32NumElem`, `pWordIds`) | | reco.cpp's port stand-in `GSAPI_WORD_LIST` (recoEnableWord's `wordlist`) | reco.cpp's `_GSAPI_RESULT` stand-in has invented member names (DWARF: Type, u16NbrWords, u16Conf, pWordIds): not changed (provider) |
| `_BCD` | PROVIDER | 8 | MSL `locale.cpp` (decimal conversion) | | libstdc++ internals | |
| `ctype`, `Init`, `basic_ios`, `basic_istream`, `basic_ostream`, `fpos`, `_MSLstring` | PROVIDER | 24 / 1 / 72 / 104 / 88 / 16 / 8 | MSL iostreams (ios.cpp, iostream.cpp, locale.cpp) | | libstdc++ iostreams (the port's MSL `__msl_ios_base_*init` objects are `#ifndef SOCOM_PORT`) | |
| `vector`, `list`, `deque`, `cdeque`, `map`, `queue`, `stack`, `pair`, `allocator` | PROVIDER | 12 / 12 / 28 / 16 / 16 / 28 / 28 / 8 / 1 | MSL containers (template instances; the `@hash` names are DWARF's unnamed template arguments) | | libstdc++ `std::vector`, `list`, `deque`, `map`, `queue`, `stack`, `pair`, `allocator` | |
| `node_base`, `generic_iterator`, `alloc_ptr`, `compressed_pair`, `compressed_pair_imp`, `_EmptyMemberOpt`, `value_compare`, `number`, `compile_assert` | PROVIDER | 8-12 / 4 / 8 / 4-8 / 4-8 / 4 / 1 / 1 / 1 | MSL / Metrowerks:: container internals | | libstdc++ internals (none named in `src/`) | |
| `binder2nd`, `less`, `equal_to`, `unary_function`, `binary_function` | PROVIDER | 8 / 1 / 1 / 1 / 1 | MSL `<functional>` (hud_newhudmap.cpp, hud_linemap.cpp, st_load.cpp) | | libstdc++ `<functional>` / `std::less` (the port's maps) | |
| (empty name) | not a type name | - | the estimate's row for DWARF's anonymous records (`@anon<n>`, `@class`, the `@unnamed@<unit>@` classes): each is filed with its owner or named elsewhere | | | |

## Enums

Underlying size: DWARF byte_size 1, spelled `enum X : unsigned char` (or `signed char` for a
negative enumerator), as the neighbouring enums do.

| name | class | DWARF size | where (and why) | uses now | flags |
| --- | --- | --- | --- | --- | --- |
| `AI_LADDER_STATE` | GAME | 1 | `src/gamez/zSeal/zseal.h`, before CSealCtrlAi (its member's class; every CU that carries CSealCtrlAi) | `CSealCtrlAi::m_ladder_state` typed AI_LADDER_STATE (was `u8`); CSealCtrlAi's ctor, SetAiMode and LadderClimbTick (`seal_ai.cpp`) compare and assign AIL_SETUP / AIL_MOVETO / AIL_CLIMBUP / AIL_CLIMBDN | LadderClimbTick's `u8 old_state` left as it was |
| `Input` | GAME | 1 | `src/Apps/FTS/hud/hud.h`, after Selection (whose neighbours Selection / Action are, like Input, only in CU hud_pausemenu.cpp) | CZPauseTest::HandleSelectionInput 0x3bef50 `input` (was `s32` 0-3) | placement to confirm: hud_pausemenu.cpp (its only unit) |
| `WeaponTextLoc` | GAME | 1 (signed) | hud.h before CWeaponSel (both weapon-select units carry it, both include hud.h) | none: no DWARF member / parameter / local / variable has the type and no code is known to use it | |
| `RecoGender` | GAME (to confirm) | 1 | orders.h with RecoParams (its only user) | `RecoParams::gender` | see RecoParams |
| `_GSAPI_RESULTTYPE` | PROVIDER | 4 | gsapi SDK (`_GSAPI_RESULT::Type`) | | not declared (reco.cpp's `_GSAPI_RESULT` stand-in has no Type) |
| `PTT_SyncReason` | PROVIDER | 1 | libpttclient (push-to-talk voice library, `g_syncReason` 0x476c98) | | the port's voice layer is offline (`port/compat/ptt_offline.cpp`) |
| `PTTServer_SyncReason` | PROVIDER | 1 | libpttserver (`g_syncReason` 0x476cc8) | | as above |
| `event`, `fmtflags`, `iostate`, `result` | PROVIDER | 1 / 2 / 1 / 1 | MSL `ios_base` (`event`, `fmtflags`, `iostate`) and `codecvt_base::result` (ios.cpp, iostream.cpp) | | libstdc++'s |

## Code changes (behaviour unchanged)

- zcam_main.cpp: the CAMERA_PARAMS parser and ticks use the DWARF records. The key tracks are read
  and sampled through templates over the key record (`ParamsParseTrack<K>`, `ParamsSample<K>`) with
  the same arithmetic as the width-based helpers they replace; a track's offset and count are
  collected while parsing and stored in the record's named bitfields after the track (the record
  grows through zAnimCmdAddData, so the final record gets them, as before). m8 never calls
  CmdParseParams (its CAMERA_PARAMS records come compiled from the disc), so the parser's rewrite is
  checked by review and compilation only; CmdBeginParams and CmdTickParams run. The records are declared
  at the top of the unit (CmdTickControlSwitch and CmdTickSetRegions, earlier in the unit, use them).
- camera.cpp, st_exit.cpp, hud_scorepopup.cpp, hud_newhudmap.cpp, hud_pausemenu.cpp: locals typed
  with the DWARF types (same widths and offsets).
- The container members (CMission, CCharacterType, CSealUnit) are typed with their empty DWARF
  subclasses of the same std containers; every user compiles unchanged (base references, swaps and
  iterators bind to the base).

## Checks

Final tree: HEAD b800665b + these files. Test builds use the state round-trip hook
(`port/test-hooks/state/hook_state.cpp`) with the fake pad; every run kept the focus.

- Compile: the default build links (no failing unit); 1425 warnings, the same set as HEAD's default
  build (diffed with paths and line numbers dropped): none from the new declarations.
- Briefing cameras in full (`-DSOCOM_HOOK_MISSIONS=1 -DSOCOM_HOOK_PLAY_AT=999999
  -DSOCOM_HOOK_CAMS_PLAY`, with test-only traces in the camera command handlers): m8bs and m8tut1 play
  to the end. Each starts with DYNAMICS_RELEASE_CAMERA (`release` set), SET_CAMERA_REGION_TEST OFF and a
  CAMERA_PARAMS with SAVE_PARAMS (hfov 0.6101 -> 0.6109, planes 4 / 3000 / 3200, fog 200-2100), and
  ends with ACQUIRE (`acquire` set), region test ON and RESTORE_PARAMS (hfov 0.6101, far 601.80 /
  603.00 back). The same traces on HEAD d035c977's own record struct gave the same values.
- m8 with the cameras skipped (intro movie CROSS, cameras X, then idle): mission from 71 s to 251 s
  (180 s), no STOP; heap in use 23.01 MB at 110 s, 23.04 MB from 130 s to 248 s.
- Round trip (`-DSOCOM_HOOK_MISSIONS=8`): eight missions and eight returns, no STOP; in use 18,666,948 B
  at return 1, then 18,667,044 B at returns 2-8, arena 25,701,868 throughout: flat, the HEAD figures
  (HEAD d035c977 alone gave the same). One earlier run of the same build on d035c977 stopped at return
  2 in zsys_memory.cpp's allocation assert while the menus reloaded (heap use 14.9 MB): the menus' heap
  fragmentation described in `menu-heap.md` (whether the 2.6 MB uizanim.zar buffer finds a hole); a rerun
  of the same ELF and this final run were flat.
- Default build (no hook, no fake pad): dlgMenu at 15.6 s, the main menu on screen.
- `python tools/socom.py audit independence --strict` passes.
