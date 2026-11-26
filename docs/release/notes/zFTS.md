# Stage 2: gamez/zFTS (2026-11-26)

The one list of `gamez/zFTS` (list a): the owner files fts_mission.cpp, fts_player.cpp,
fts_action.cpp, fts_main.cpp, fts_network.cpp, fts_network_dme.cpp, fts_remote.cpp,
fts_net_seal.cpp, fts_net_game.cpp, fts_net_grenade.cpp, fts_net_bomb.cpp, fts_net_persona.cpp,
fts_controller.cpp, fts_objectivecam.cpp and fts_missioncam.cpp (release 0x1f3a70-0x20ec70). It
holds 42 uncertain rows (36 new, 4 removed, 2 unsure), 15 sampled deviating rows out of 168, and
175 exact rows that were not checked one by one. Pairing produced by `socom-release-compare-c1`
(`python tools/release/compare.py`); checked by `socom-release-check-fts`, who did not write the
tool, at HEAD fa04cf2f. The check sheet (`compare.py --sheet gamez/zFTS --list a`) was the
starting point. Both images were disassembled with the release tools; callers were found by
scanning both images for `jal`/`j`, data words and `lui`/`addiu` pairs, and the arguments of
registration calls were recovered by tracking `lui`/`addiu` into a0-t1. Ghidra was not needed.

As the guard on the committed pairs, all 345 paired rows of the owner files had their callers and
address-loaders compared with the prototype's through the map; the 28 paired functions that load
the address of a zFTS function had their ordered pointer loads compared; the 18 zFTS functions
stored in data had the stored neighbours of each slot compared. Every difference is explained
below.

What settled rows, in the order it was used: the `CZAnimMain::AddCmd` registrations (command
string, parse, begin and tick pointers) that `CMission::Init` makes in the prototype and new
0x1fbcd0 makes in the release; the `NetRegisterApplicationMessage` sequence of `DMERegister`; the
call site in a paired caller (VoterPacketHandler, UIHaveBeenBannedFromGame, CreateLadderTable,
ExecuteAction, the CMission constructor, `__sinit_fts_net_seal.cpp`, CCoreState::Tick); strings;
the slot between paired neighbours.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x1f7c80 | - | new | confirmed | searches the ladder list (36-byte entries) for the entry whose node (+0x18) is the argument, or optionally its +0x64; callers CreateLadderTable and two new CZSealBody uses (ImpactFront, CanTraverse) |
| 0x1f7fa0 | - | new, copy | confirmed | `jr ra; addiu v0,a0,8`: an out-of-line accessor called only by CreateLadderTable, which did not call one in the prototype |
| 0x1f7fb0 | - | new, copy | confirmed | `jr ra; lw v0,4(a0)`: the same kind, the same sole caller |
| 0x1f7fc0 | - | new | confirmed | builds a min/max box from eight points; callers CreateLadderTable (after the 8-point Transform; the prototype transformed 2 points) and zdb gridAddNodeToGrids |
| 0x1f84f0 | - | new | confirmed | CMission method (this+0x70 test): _OnMissionComplete, CVideo::Clear, CFlashFXVector::Reset, ResetDeathCam, CGame::Push: the closing sequence of OnMissionComplete, now called by CCoreState::Tick |
| 0x1f88b0 | - | new, copy | confirmed | `j UpdateLocalGame; move a0,a1`: called by ForceStatusReport with theMission and its net game (+0x594); the prototype ForceStatusReport only set a flag |
| 0x1f9210 | - | new | confirmed | the player's controller (+0xc0) tested against states 2-5 through new 0x28f120 (`+0x221 == arg`); caller BitmapReticule::HudTick |
| 0x1f9710 | - | new | confirmed | fills a 48-byte member at CMission+0xb4 with constants (0, 4, 10000.0, 60.0, 0.75, 2500.0, 2.0, 1.0, 0.25, 9, 5); sole caller the CMission constructor |
| 0x1fbcd0 | - | new | confirmed | registers the eight HUD zAnim commands (HUD_ON ... HUD_TRIGGER_POPUP) that the prototype CMission::Init registered inline; sole caller Init |
| 0x1fbe50 | - | new | confirmed | tick of the new command HUD_TRIGGER_POPUP (registered so by 0x1fbcd0): ZAnim GetName, then new 0x420c20 |
| 0x1fbe80 | - | new | confirmed | parse of HUD_TRIGGER_POPUP: calloc at fts_mission.cpp line 1126, stores ZAnim AddName of its string argument |
| 0x1fc010 | - | new | confirmed | parse of the new command HUD_STOP_DEFUSE_TIMER (calloc line 1091, no arguments) |
| 0x1fc080 | - | new | corrected to 0x1f9740 `HUDStartDefuseTimerTick__FP14_zanim_cmd_hdrPf` | the tick registered with "HUD_START_DEFUSE_TIMER" on both sides; calls hudStartDefuseTimer with the command's float (now at +8, a bool from +4 added) |
| 0x1fc0b0 | - | new | corrected to 0x1f9760 `HUDStartDefuseTimerParse__FP5_zrdr` | the parse registered with "HUD_START_DEFUSE_TIMER" on both sides; the same number reader and calloc (line 1021 -> 1055), now also reads a COUNT_UP tag |
| - | 0x1f9760 `HUDStartDefuseTimerParse__FP5_zrdr` | removed | corrected to 0x1fc0b0 | see the row above |
| 0x1fc310 | 0x1f9980 `HUDTriggerMissionCamParse__FP5_zrdr` | unsure, position | confirmed, deviating | the parse registered with "HUD_TRIGGER_MISSION_CAM" on both sides, with the paired Begin (0x1fc2c0) and Tick (0x1fc260) |
| - | 0x1fc770 `__ct__Q210Metrowerks17compile_assert<1>F...` | removed | confirmed | its six call sites in insert<CUIVariable> are gone: the release insert calls new 0x3bd630 (the out-of-line CUIVariable copy constructor, zUI) where the prototype called the vector_pod copy constructor and this |
| - | 0x1fdb50 `ftsSetPlayerCount__Fi` | removed | confirmed | sole caller process_arguments (command-line parsing), removed with it |
| - | 0x1fe130 `ftsSetSquirm__Fb` | removed | confirmed | the same |
| 0x200c30 | - | new, no owner | confirmed; owner fts_action.cpp | walks `CNodeAction::m_actions` and pauses the running action animations (or resumes the paused ones); callers CZNewHudMap SwitchToCompassMap and SwitchMapToFullScreen; sits before SyncActionsMP |
| 0x200f50 | - | new | confirmed | the animation callback that ExecuteAction stores in the new CZAnim (+0x1c, with the action at +0x20): clears the action's anim (+0x10) and bumps an 8-bit counter in +0x2e |
| 0x200f80 | - | new | confirmed | returns `m_anim (+0x10) == 0`; caller CSealCtrlAi::AllowCommand on the reticule action |
| 0x205e10 | - | new | confirmed | the handler of a new six-field DME message that DMERegister registers between PushBlend and ActionAnim (all other registrations correspond one to one); for net game type 3 it unpacks an object index, a short, a byte and a 3-byte vector and passes them to an empty CZSealBody method (0x287500) |
| 0x206dd0 | - | new, copy | confirmed | `j 0x208a80` on m_RemoteGuyList: clears the remote guy list; caller CLoadState::Init |
| 0x208640 | - | new | confirmed | vector insert ("vector::insert length error") on m_RemoteGuyList; caller RemoteSealCreationCallback, which in the prototype allocated 8 bytes and inserted the pointer into a list |
| 0x208a60 | - | new, copy | confirmed | swaps two words (std::swap of a pointer); callers the new insert and reserve |
| 0x208a80 | - | new, copy | confirmed | vector clear for 8-byte elements; callers UnloadRemoteGuyList, RemoteSealUpdateCallback, 0x206dd0 (all used list erase in the prototype) |
| 0x208ad0 | - | new, copy | confirmed | the vector's destructor (clear, delete the buffer, optionally delete this); callers the CRemoteGuyList destructor (paired) and the insert |
| 0x208b70 | - | new, copy | confirmed | vector reserve ("vector::reserve length error"); caller `__sinit_fts_net_seal.cpp`, with 14 |
| 0x208d20 | - | new, copy | confirmed | `jr ra; move v0,a0` (allocator accessor); caller the reserve |
| 0x208da0 | - | new, copy, no owner | confirmed; owner fts_net_seal.cpp | the vector constructor (three words cleared); caller `__sinit_fts_net_seal.cpp`, which built a list_deleter there in the prototype |
| 0x20adc0 | - | new | confirmed | for each persona with a voice address (+0x2ac) calls CZNetVoice::ServerPermit; caller zDoClientLeavesCallback |
| 0x20ae80 | 0x2088c0 `NumActiveTerrorists__14CZPersonaStateFv` | unsure, call-deviating | corrected to new | returns a bool: counts the local player's team (terrorist 0x100 or seal 1, the prototype NumActiveTerrorists and NumActiveSeals loops written inline) and tests whether the vote count 0x20b090 exceeds half of it. UIHaveBeenBannedFromGame tail-calls it where the prototype returned the banned flag that VoterPacketHandler set after that same test |
| - | 0x2088c0 `NumActiveTerrorists__14CZPersonaStateFv` | (paired) | removed | its loop is inline in 0x20ae80; no release function has its body |
| 0x20b140 | - | new | confirmed | returns byte +0x2d4 of the persona whose +0x2d1 is the argument; callers OrdersMenu ScrollForward and RefreshContext |
| 0x20b200 | - | new | confirmed | sets that byte +0x2d4; caller SendVoteMessage |
| 0x20b2c0 | - | new | confirmed | sets byte +0x2d3 (a vote against the local player) of the sending persona; caller VoterPacketHandler, in place of the prototype's counter at player+0xebc |
| 0x20d220 | - | new, no owner | confirmed; owner fts_controller.cpp | reads `g_pCurrentConfig` (an unnamed-namespace global of fts_controller.cpp) and sets two flags of the controller (+0x1c9, +0x1f1); caller CSealCtrl::PreTick |
| 0x20de70 | - | new | confirmed | byte lookup `a0[0x13 + idx]`; callers GetPitchStickPosDilated and GetFwdBackStickPos |
| 0x20de80 | - | new | confirmed | `lb v0,0(a0)`; the same callers |
| 0x20de90 | - | new | confirmed | `a0 + a1`; the same callers |
| 0x20e060 | - | new | confirmed | the pressure (float, +0x24 table of the pad) of the button the current config maps to an index, 0 when unmapped (16); caller CSealCtrl::PreTick |
| 0x20e6a0 | - | new | confirmed | CMissionObjectiveCam method: sets the bit of a letter (a-z or A-Z) of a string in the mask at +0x50; caller LoadObjectiveCams |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x1f4eb0 | 0x1f3460 `UnSerialize__8CMissionFPCcP8CRdrFilei` | yes | slot +0x10 of the CMission vtable on both sides |
| 0x1f5f30 | 0x1f3d50 `LateJoiner__9CZNetGameFb` | yes | the same three callers |
| 0x1f7b30 | 0x1f5a90 `GetClosestLadder__11CLadderListFPC6CPnt3Df` | yes | same caller ftsFixupAiMap |
| 0x1f9d70 | 0x1f7730 `ZAnimLoad__8CMissionFv` | yes | same caller CMission::Open |
| 0x1fa610 | 0x1f7f50 `Open__8CMissionFPCci` | yes | same caller testLoad |
| 0x1fe950 | 0x1fc0a0 `insert__Q23std62__vector_imp<11CUIVariable,...>` | yes | same caller resize |
| 0x1ff1a0 | 0x1fcd90 `RefreshTeamValves__8CMissionFv` | yes | the prototype's 11 callers, plus two new |
| 0x1ff4f0 | 0x1fd0d0 `InitalizeTeamValves__8CMissionFv` | yes | same callers ReOpen_Load and Open |
| 0x206190 | 0x203af0 `SendHitMessage__FiiiffbUc` | yes | same caller ReportWeaponHitDamage |
| 0x206de0 | 0x204740 `UpdateLocalSeal__11CZSealStateFP10CZSealBody` | yes | the prototype's six callers, plus CMPExitState::Init |
| 0x209f70 | 0x206e20 `UninitBomb__11CZBombStateFv` | yes | same callers OnMissionComplete and CLoadState::Init |
| 0x20b430 | 0x207c40 `GetSOUPString__14CZPersonaStateFP10CZSealBodyi` | yes | same callers SetupCommandDisplay and PlayRemoteMsg |
| 0x20b560 | 0x207d70 `CheckStateSwitch__14CZPersonaStateFv` | yes | same callers UpdateLocalPersona and RemotePersonaDeletionCallback |
| 0x20e830 | 0x20acb0 `__ct__20CMissionObjectiveCamFv` | yes | same caller LoadObjectiveCams |
| 0x20e990 | 0x20adf0 `Set__11CMissionCamFPCcPCcPCcPCcPCcPCcPCc` | yes | same callers LoadMissionCams and CMissionObjectiveCam::Set |

Outside the list's uncertain rows (committed pairs in the owner files, found by the cross-check):

| release | map | finding |
|---|---|---|
| 0x1fbff0 | deviating, 0x1f9740 `HUDStartDefuseTimerTick__FP14_zanim_cmd_hdrPf` | wrong: it is the tick registered with "HUD_STOP_DEFUSE_TIMER" (with parse 0x1fc010); its body calls CZWeapon::ClearTimer, not hudStartDefuseTimer. New. HUDStartDefuseTimerTick is 0x1fc080 |
| 0x20b090 | deviating, 0x208810 `NumActiveSeals__14CZPersonaStateFv` | wrong: it counts the personas whose vote byte +0x2d3 is set (the byte 0x20b2c0 sets), and VoterPacketHandler prints its result as "Voting: You have %d votes against you.", where the prototype printed its own counter. The seal count of the prototype NumActiveSeals (team bit 1) is inline in 0x20ae80, which compares this count with half of it. New; NumActiveSeals is removed |

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner |
|---|---|---|---|---|---|
| 0x1fc080 | 0x1f9740 | the tick registered by AddCmd with "HUD_START_DEFUSE_TIMER" on both sides (CMission::Init / 0x1fbcd0); calls hudStartDefuseTimer | socom-release-check-fts | 2026-11-26 | |
| 0x1fc0b0 | 0x1f9760 | the parse registered by AddCmd with "HUD_START_DEFUSE_TIMER" on both sides | socom-release-check-fts | 2026-11-26 | |
| 0x1fbff0 | new | the tick registered with "HUD_STOP_DEFUSE_TIMER" (new command); calls CZWeapon::ClearTimer | socom-release-check-fts | 2026-11-26 | |
| 0x1fc310 | 0x1f9980 | the parse registered with "HUD_TRIGGER_MISSION_CAM" on both sides, with the paired Begin and Tick | socom-release-check-fts | 2026-11-26 | |
| 0x20ae80 | new | returns whether the votes (0x20b090) exceed half of the local player's team; UIHaveBeenBannedFromGame tail-calls it; the prototype NumActiveTerrorists/NumActiveSeals loops are inline in it | socom-release-check-fts | 2026-11-26 | |
| removed | 0x2088c0 | NumActiveTerrorists: its loop is inline in 0x20ae80; no release function has its body | socom-release-check-fts | 2026-11-26 | |
| 0x20b090 | new | counts the persona vote byte +0x2d3 set by 0x20b2c0; printed by VoterPacketHandler as the votes against you | socom-release-check-fts | 2026-11-26 | |
| removed | 0x208810 | NumActiveSeals: its loop (team bit 1) is inline in 0x20ae80; no release function has its body | socom-release-check-fts | 2026-11-26 | |
| 0x200c30 | - | owner: uses CNodeAction::m_actions; sits before SyncActionsMP | socom-release-check-fts | 2026-11-26 | src/gamez/zFTS/fts_action.cpp |
| 0x208da0 | - | owner: called only by `__sinit_fts_net_seal.cpp`; directly after the CRemoteGuyList destructor | socom-release-check-fts | 2026-11-26 | src/gamez/zFTS/fts_net_seal.cpp |
| 0x20d220 | - | owner: reads `g_pCurrentConfig`, an unnamed-namespace global of fts_controller.cpp; directly before SetButtonState | socom-release-check-fts | 2026-11-26 | src/gamez/zFTS/fts_controller.cpp |

Rows that change together: the four defuse-timer rows (0x1fbff0, 0x1fc080, 0x1fc0b0 and the
removed 0x1f9760); the four voting rows (0x20ae80, 0x20b090 and the removed 0x2088c0, 0x208810).

## New and removed

New in the list (names are guesses unless the basis says otherwise; the prototype's naming
patterns are followed):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x1f7c80 | finds the ladder entry of a node | guess: `GetLadderByNode__11CLadderListFPQ23zdb5CNodeb` (between GetClosestLadder and GetLadderByIndex) |
| 0x1f7fa0, 0x1f7fb0 | trivial accessors used by CreateLadderTable | guess: out-of-line inline accessors (+8 address, +4 word) |
| 0x1f7fc0 | min/max box of eight points | guess: `CBBox::Build(const CPnt3D*)` (a header inline emitted here; zdb calls it too) |
| 0x1f84f0 | ends the mission: _OnMissionComplete, video clear, flash reset, death cam reset, push the next state | guess: `EndMission__8CMissionFv` (the prototype scheduled fadeToEndMissionTick for this; the release OnMissionComplete no longer does) |
| 0x1f88b0 | sends the local game update for a net game | guess: `UpdateNetGame__8CMissionFP9CZNetGame` (next to DestroyNetGame) |
| 0x1f9210 | is the player's controller outside states 2-5 | guess: `ftsReticuleAllowed__Fv` (caller BitmapReticule::HudTick) |
| 0x1f9710 | constructor of a 48-byte CMission member at +0xb4 | guess: the constructor of a mission parameter block; its type is unknown |
| 0x1fbcd0 | registers the HUD zAnim commands | guess: `HUDRegisterCmds__Fv` |
| 0x1fbe50, 0x1fbe80 | HUD_TRIGGER_POPUP tick and parse | `HUDTriggerPopupTick__FP14_zanim_cmd_hdrPf`, `HUDTriggerPopupParse__FP5_zrdr` (the command string and the file's pattern) |
| 0x1fbff0, 0x1fc010 | HUD_STOP_DEFUSE_TIMER tick and parse | `HUDStopDefuseTimerTick__FP14_zanim_cmd_hdrPf`, `HUDStopDefuseTimerParse__FP5_zrdr` (the same basis) |
| 0x200c30 | pauses or resumes all action animations | guess: `PauseActions__11CNodeActionFb` |
| 0x200f50 | animation-done callback of an action | guess: `OnAnimDone__11CNodeActionF...` (static; the stored callback) |
| 0x200f80 | the action has no running animation | guess: `IsReady__11CNodeActionFv` |
| 0x205e10 | handler of a new DME message (object index, short, byte, vector) for a seal body | guess: `<Name>PacketHandler__FiiiPv`; what the message carries is unknown (its receiver 0x287500 is empty) |
| 0x206dd0 | clears the remote guy list | guess: `ClearRemoteGuyList__11CZSealStateFv` |
| 0x208640, 0x208a60, 0x208a80, 0x208ad0, 0x208b70, 0x208d20, 0x208da0 | the std::vector instance behind m_RemoteGuyList: insert, swap, clear, destructor, reserve, allocator accessor, constructor | guess: `vector<...>` members for an 8-byte element (the element type is not named by anything here) |
| 0x20adc0 | grants voice to every persona that has a voice address | guess: `PermitAllVoice__14CZPersonaStateFv` |
| 0x20ae80 | have I been voted out | guess: `VotedOut__14CZPersonaStateFv` |
| 0x20b090 | counts the votes against the local player | guess: `NumVotesAgainst__14CZPersonaStateFv` |
| 0x20b140, 0x20b200 | get and set the persona byte +0x2d4 (a vote cast for that player) | guess: `GetVote__14CZPersonaStateFi`, `SetVote__14CZPersonaStateFib` |
| 0x20b2c0 | records a vote against the local player from a persona | guess: `SetVoteAgainstMe__14CZPersonaStateFib` |
| 0x20d220 | applies the current config's stick settings to the controller | guess: `ApplyConfig__13CCtrlrConfigsFP9CSealCtrl` |
| 0x20de70, 0x20de80, 0x20de90 | out-of-line inline helpers of the stick readers | guess: config byte lookup, signed byte read, pointer add |
| 0x20e060 | pressure of a mapped button | guess: `GetButtonPressure__13CCtrlrConfigsFUcRC4CPad` |
| 0x20e6a0 | adds a letter flag to the objective cam's mask (+0x50) | guess: `AddFlag__20CMissionObjectiveCamFPCc` |

Not new, though the map has them as new: 0x1fc080 (HUDStartDefuseTimerTick), 0x1fc0b0
(HUDStartDefuseTimerParse). New, though the map pairs them: 0x1fbff0, 0x20ae80, 0x20b090.

Really removed:

- `__ct__Q210Metrowerks17compile_assert<1>...`: the CUIVariable copy is now built by the out-of-line
  copy constructor 0x3bd630 (zUI), so insert no longer calls it.
- ftsSetPlayerCount and ftsSetSquirm: their only caller, process_arguments, is gone.
- NumActiveTerrorists and NumActiveSeals: their counts are inline in 0x20ae80; the vote rule moved
  from VoterPacketHandler into that function.
- Not removed, though the map has it: HUDStartDefuseTimerParse (0x1fc0b0).

Layouts, plainly shown by settled rows: CZSealState::m_RemoteGuyList is now a vector of 8-byte
entries (reserved 14 at start-up), where the prototype kept a list of pointers to 8-byte records;
the persona record (+0x1c of the network object) gained vote bytes at +0x2d3 and +0x2d4, keyed by
+0x2d1; CMission gained a 48-byte member at +0xb4.

On the prompt's context (mission loading, saving, multiplayer set-up): the new code in this list is
multiplayer voting (0x20ae80, 0x20b090, 0x20b140-0x20b2c0), voice (0x20adc0), a network message
(0x205e10), the remote guy list, ladders (0x1f7c80, 0x1f7fc0; the demo has no ladders), two HUD
script commands, the end-of-mission sequence (0x1f84f0) and controller config helpers. Nothing new
here touches saving.

## Still unsure

None of the list's rows. Open points:

- The names of the new functions are guesses, except the four HUD command handlers.
- 0x205e10's message: its sender is not identified (not needed for the pairing).

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| new | 36 | 34 | 2: 0x1fc080 is HUDStartDefuseTimerTick, 0x1fc0b0 is HUDStartDefuseTimerParse |
| removed | 4 | 3 | 1: HUDStartDefuseTimerParse is 0x1fc0b0 |
| unsure | 2 | 1 (HUDTriggerMissionCamParse) | 1: 0x20ae80 is new, NumActiveTerrorists is removed |

Owners: three new rows without an owner belong to fts_action.cpp (0x200c30), fts_net_seal.cpp
(0x208da0) and fts_controller.cpp (0x20d220).

The sample: 15 of 15 deviating rows are the same function on both sides.

The cross-check: 345 paired rows compared (callers and address-loaders through the map), 28
loaders' ordered pointer loads, 18 stored functions' table neighbours.
Differences looked at: 37 caller sets, 5 pointer sequences, 6 table neighbourhoods. Nearly all are
callers added in the release (new or grown functions), callers that moved (CHUD::Tick to new
0x3d6e70, TickFullScreenMap to new 0x3e5c60, the HUD command registrations from CMission::Init to
0x1fbcd0, the fade task from OnMissionComplete to 0x1f84f0), or neighbour slots of other classes;
one pointer is a constant (`lui 0x20` in zdb AddDecal is a flag, not ftsSetPlayer).
Pairs wrong: 2 (0x1fbff0 and 0x20b090; see above), plus 0x20ae80 among the list's unsure rows. The
caller check alone did not flag 0x20b090 (its callers still correspond); reading it next to
0x20ae80 did.

What misled it:

- The defuse-timer handlers: the release added HUD_STOP_DEFUSE_TIMER, whose 32-byte tick (one call,
  return 1) has the shape of the prototype's start tick and sits where it sat; position and shape
  won over the callee. The AddCmd registrations (string, parse, tick) decide every handler.
- The voting functions: the release keeps per-persona vote bytes and counts them with a loop of the
  same shape as NumActiveSeals; the new 0x20ae80 holds both team counts inline and kept the
  prototype's callers. Shape and caller pulled both to the old names.

What cost the most time: the voting group (four functions of one shape and two inline loops).
Suggestions:

- Pair zAnim command handlers by the string and slot of the `AddCmd` call that registers them, as
  the network handlers are paired by their registration.
- For a pair whose release side's result feeds a format string, show that string in the sheet.
