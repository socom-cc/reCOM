# New release functions outside a class: name proposals (second sheet)

Name proposals for the release functions (SCUS-971.34) that have no prototype counterpart and that the first sheet, [new-function-names.md](new-function-names.md), did not cover: every function of `build/release/unnamed/unnamed-membership.json` (627 unnamed new functions) that is not one of its 240 rows, 387 functions, including 0x260430, which the first sheet left out because its evidence names two classes. It continues the first sheet: its rows are numbered 241 to 627, so a row number names one function across both sheets. Written by the agent `socom-release-newnames-p2` on commit 15b82411 (the release program with its 9,199 function names, 5,585 signatures, 3,694 named globals and the value of gp set, so gp-relative globals show by name). Every function was decompiled again from the live release program (read-only); the prototype program was read for the library functions the comparison could not pair. Sources: the membership data, the release and prototype programs, the stage-2 checker notes under this folder (sections "New and removed"), the first sheet's rows for names of callees and callers, and the release image for table references and strings. By kind: member 80, static member 18, free function 65, compiler-made 56, library 168. By confidence: high 112, medium 129, low 146. Basis of the rows with a name: a library function identified by its behaviour, its own messages or the prototype's copy 94; an earlier note checked against the body 208; the body and its callers alone 9; no virtual-table slot names any of them (none of these functions sits in a release virtual table). The other 76 get a neutral `fn_<address>` name, most of them library internals whose behaviour is clear but whose library name is not known; the "what the body does" column still describes them.

**Update 2026-11-28.** A second agent checked the library pairs this sheet found ([library-pairs.md](library-pairs.md)): 55 rows are no longer proposals. Those functions are paired with their prototype counterparts and carry the prototype's names in the program; their confidence cell reads `done: carried as ...`. Nothing is left to decide for them. Row 0x3d4ea0 stays a new function.

Reading the rows: offsets are hexadecimal; `this` is the first argument; a "row N" below 241 is a row of the first sheet. A global whose data-map plate says `single-aligned` rests on one witness and is used as a hint only, and the rows say so where a name leans on one. Template instances of MSL containers are listed as compiler-made with the MSL class that holds the member (`__vector_imp`, `__vector_deleter`, `__list_deleter`, `compressed_pair_imp`); their element types are the notes' guesses where the body does not name them. The release links a rebuilt copy of the PTT voice library (its LPC-10 codec), so the comparison paired only a few of its functions (most as unsure): the rows for the others rest on the prototype's own functions, which carry the same constants, statics, argument counts and call graph.

## src/Apps/FTS/hud/hud_linemap.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 241 | 0x3eacc0 | free function |  | `fn_003eacc0` | empty (`jr ra; nop`) | hud.md: called once, at the end of CZNewHudMap::ZoomToCurrentObjective (row 6); an emptied hook; owner by position only | low |

## src/Apps/FTS/hud/hud_main.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 242 | 0x3dcf50 | free function |  | `hudToggleHelpWindows` | flips the cached HelpWindowsEnabled valve (0x48e8f0, set by hudInit) and runs its callbacks (CValve::MakeCallbacks) | hud.md proposed it; caller CZPauseTest::HandleSelectionInput; before hudInit | medium |
| 243 | 0x3dcfc0 | free function |  | `hudHelpWindowsEnabled` | true when that valve is missing or on | hud.md proposed it; callers CZPauseTest::ReInit, HandleSelectionInput, hudOpenHelpPopup (row 8) | medium |

## src/Apps/FTS/hud/hud_newhudmap.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 244 | 0x3e66b0 | free function | `@unnamed@hud_newhudmap_cpp@` | `SetupLegend` | builds the map legend: static row positions, the "NAV POINTS", "PRIMARY OBJECTIVE", "EXTRACTION POINT", "HOSTAGE/POW/TRAITOR" and new "ABLE's POSITION" / "BRAVO's POSITION" lines with their bitmaps | hud.md proposed it (next to SetupNorthIndicator); caller CZNewHudMap::InitMap | medium |
| 245 | 0x3e72e0 | compiler-made | (hud_newhudmap.cpp) | `__arraydtor` | __destroy_arr of the 9 CPlainBmp (0xa0 bytes) at 0x57bbf0 | hud.md: registered by __sinit_hud_newhudmap.cpp; the compiler's number suffix is not known | medium |
| 246 | 0x3e7300 | compiler-made | (hud_newhudmap.cpp) | `__arraydtor` | __destroy_arr of the 9 C2DString (0x8c bytes) of g_strNorthIndN | hud.md; the same | medium |

## src/Apps/FTS/hud/hud_scorepopup.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 247 | 0x420b30 | free function |  | `hudHelpPopupObjective` | (objective): finds the "HudObjective" popup (vector 0x58d7c0) of this mission (GetDatabase) for the objective's name (+0x20); unless shown, opens it (hudOpenHelpPopup, row 8) and marks it | hud.md proposed it; caller CZNewHudMap::SwitchToCompassMap | medium |
| 248 | 0x420c20 | free function |  | `hudHelpPopupAnimCmd` | (name): finds the "AnimCmd" popup (vector 0x58d7a0) of that name; unless shown, opens it and marks it | hud.md proposed it; caller HUDTriggerPopupTick (0x1fbe50) | medium |
| 249 | 0x4211b0 | free function |  | `hudResetHelpPopups` | clears the shown flags of the entries of the popup vectors 0x58d7a0, 0x58d7c0 and 0x58d7e0 | hud.md proposed it; callers CHUD::Init, CHUD::ReInit_Init | medium |
| 250 | 0x421290 | free function |  | `hudHelpPopupActionIcon` | (icon): offline only (theNetwork.m_bNetwork false): finds the "ActionIcon1stTime" popup (vector 0x58d780) of this mission that lists the icon; unless shown, opens it and marks it | hud.md proposed it; caller CActionTxtrMachine::Open | medium |
| 251 | 0x4213c0 | free function |  | `hudReadHelpPopupSettings` | (_zrdr*): reads TopMargin, LeftMargin, BottomMargin, PromptText, BackgroundOpacity, ForceOpenTime, OpeningSound, ClosingSound into the popup statics | hud.md proposed it; caller hudInit | medium |
| 252 | 0x421550 | free function |  | `hudGetHudPopups` | returns the function-local static CHudPopups (0x58d830), building it on first use (C2D constructor, the CHudPopups table, __register_global_object with ~CHudPopups row 9) | hud.md proposed it (next to hudGetScorePopupPtr); caller CCoreState::Tick | medium |
| 253 | 0x421620 | free function |  | `hudReadHelpPopup` | (_zrdr*): reads one popup entry (Trigger: ActionIcon1stTime, AnimCmd, ObjUnderRet1stTime ...; Type, Name, Mission, Icons, ObjName, Valve, WindowPos, WindowSize, TextSize, LineInterval, TextLines) and appends it to its trigger's vector | hud.md proposed it; caller hudInit, once per tag | medium |
| 254 | 0x421fc0 | compiler-made | `std::vector<T*>` (T unknown, a popup vector) | `end` | returns data (+8) + 4 * size (+4) | hud.md: a vector end() instance; caller hudReadHelpPopup 0x421620 | medium |

## src/Apps/FTS/main.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 255 | 0x142480 | compiler-made | `_zmalloc<sixteen>` | `_zmalloc` | template constructor (this, count): element size 16 at +0xc, count at +0x10, clears +0x14..+0x1c, calls init_page 0x1424c0; `__sinit_main.cpp` builds it with 12500 | small-1.md; the same body as the `_zmalloc<four>` / `<twelve>` constructors with 16; the template argument `sixteen` follows four / twelve and is a guess | medium |
| 256 | 0x1424c0 | compiler-made | `_zmalloc<sixteen>` | `init_page` | calloc(16, count) at main.cpp:106 into +0 / +4, links the blocks into a free list, raises the heap mark puRam0048d208, stores the end at +8 | small-1.md; the body of `_zmalloc<twelve>::init_page` with 16 | medium |
| 257 | 0x142560 | compiler-made | `_zmalloc<twenty>` | `_zmalloc` | the same constructor with element size 20 (0x14), calls 0x1425a0; built with 4700 | small-1.md; as 0x142480 | medium |
| 258 | 0x1425a0 | compiler-made | `_zmalloc<twenty>` | `init_page` | calloc(20, count) at main.cpp:106; the same free-list set-up in 20-byte steps | small-1.md; as 0x1424c0 | medium |
| 259 | 0x142cf0 | compiler-made | `_zmalloc<twenty>` | `acquire` | (this, size): when size equals +0xc pops a block off the free list (+4), counting in use (+0x14) and the peak (+0x18); with the list empty malloc(20) at main.cpp:136, counting +0x1c; caller std::allocator<char>::allocate (its size-20 branch) | small-1.md; the body of `_zmalloc<four>::acquire` with 20 | medium |
| 260 | 0x142d80 | compiler-made | `_zmalloc<sixteen>` | `acquire` | the same with malloc(16); caller std::allocator<char>::allocate (size-16 branch) | small-1.md; as 0x142cf0 | medium |

## src/gamez/zAI/ai_main.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 261 | 0x17d9a0 | member | `Rfloat` | `Rfloat` | constructor (min, max, this): stores min at +0 and max - min at +4, the layout Rfloat::operator float reads | zAI.md proposed `__ct__6RfloatFff`; callers AddNoise (three times), CAiSPursue::Tick, CTurret::AcquireTarget, CTurret::Tick | high |

## src/gamez/zAI/ai_maps.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 262 | 0x19b0c0 | member | `CAiMaps` | `GetAltitude` | (this, CAiMapLoc&, float* out): finds the map by index in the list, the cell through its scanline; when found, *out = altitude bits * scale (+0xb4) + base (+4) and returns true | zAI.md proposed `GetAltitude__7CAiMapsFRC9CAiMapLocPf` (an overload of the release GetAltitude); caller CAiSPathRecover::Tick | medium |

## src/gamez/zAI/ai_path.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 263 | 0x192e80 | member | `CAiPath::point` | `point` | constructor from a CAiMapLoc: copies the map index (6 bits), x and z bit fields, clears width, flags and angle, +8 = 0 | zAI.md; caller CAiPath::AddAvoidPoints (row 23) | medium |
| 264 | 0x192f70 | free function |  | `_avoid_walk_cb` | MAP_LINEWALK callback (closure, CAiMapLoc*): 1 when the cell is the closure's target; else tests CanTravelLine both ways and a distance limit (+0x14), keeps the location, returns 0 to stop | zAI.md: the callback AddAvoidPoints (row 23) passes to WalkLine; the name follows the file's `_<verb>_cell`-style statics and is a guess | low |

## src/gamez/zAnim/zanim_cmd_parse.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 265 | 0x1ab1b0 | free function |  | `zAnimLoadRemoveSatchels` | parser for "REMOVE_SATCHELS": calloc 0x14 at zanim_cmd_parse.cpp:0x1311, command id 0x50, reads LOCATION (3 reals, +4) and RADIUS (+0x10); frees and returns 0 on failure | zAnim.md: the release-only AddCmd("REMOVE_SATCHELS"); the file's zAnimLoad<Command> pattern (next zAnimLoadFireWeapon) | high |

## src/gamez/zAnim/zanim_cmd_tick.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 266 | 0x1b8b50 | free function |  | `zAnimRemoveSatchelsTick` | tick for REMOVE_SATCHELS: 0x3373a0(radius +0x10, location +4), returns 1 | zAnim.md; the <Command>Tick pattern (neighbours zAnimDebugTick, zAnimFireWeaponTick) | high |

## src/gamez/zAnim/zanim_menu.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 267 | 0x1d1050 | free function |  | `UIRefreshGameListInfo` | UI command: for the node id at +4 refreshes ZAnim, takes the node's first visual and its virtual +0x1c, then passes that object's +0x68 to CZOnlineLobby::RefreshGameInfo (0x341e40, row 69) on theLobby | zAnim.md: the release-only key "RefreshGameListInfo" in the handler table (0x44aa14); handlers outside the unnamed namespace are UI<Key> | high |
| 268 | 0x1d10f0 | free function |  | `UICheckTeamStatus` | UI command: returns 1, but 0 when the object at theMission +0x594 is missing, or when this console is not the session master (theNetwork.m_bSessionMaster) and that object's +0xa0 is 0; in the second case it also sets the object's +0xb1 | zAnim.md: key "CheckTeamStatus" (0x44aa44) | high |
| 269 | 0x1d1840 | free function |  | `UIFadeAllSounds` | UI command: calls 0x306430 (fades out every sound instance over 1.5 s), returns 1 | zAnim.md: key "FadeAllSounds" (0x44a954); next to UIRebootIOP and UIStopAllSounds | high |
| 270 | 0x1d21d0 | free function |  | `UIClearUIVar` | UI command: finds the UI variable named by the argument (CUIVarManager::Find) and clears it by type: list 4 to an empty list (CRdrEditor), string 3 to "", 2 and 1 to 0.0 with UpdateDependents | zAnim.md: key "ClearUIVar" (0x44aa20) | high |
| 271 | 0x1d2450 | free function |  | `UIPruneUIVarSpaces` | UI command: for a string UI variable (type 3) named by the argument (or INPUT_STRING's argument), copies it, strips trailing and leading spaces, stores it back | zAnim.md: key "PruneUIVarSpaces" (0x44a9d8) | high |
| 272 | 0x1d2ab0 | free function |  | `UIGetClanMessages` | UI command: 0x345b10(theLobby, 1), which requests MediusGetMyClanMessages; returns 1 | zAnim.md, zNetwork-a.md: key "GetClanMessages" | high |
| 273 | 0x1d2ae0 | free function |  | `UIGetUsagePolicy` | UI command: 0x349040(theLobby), which sends MediusGetPolicy; returns 1 | zAnim.md, zNetwork-a.md: key "GetUsagePolicy" | high |
| 274 | 0x1d2d20 | free function |  | `UIBackgroundMPEG` | UI command: by the argument string ("ON"-like DAT_00463ad8 or the other) restarts or halts the menu's background movie (CMenuState::RestartBackgroundMPEG / HaltBackgroundMPEG on theGame +0x7c); returns 1 | zAnim.md: key "BackgroundMPEG" (0x44a9b4) | high |
| 275 | 0x1d2e00 | free function |  | `UIAutoAim` | UI command: sets the global _AutoAim to 1 or 0 by the argument string; returns 1 | zAnim.md: key "AutoAim" (0x44a9c0) | high |
| 276 | 0x1d32d0 | free function |  | `UIPlayMPEGNoFade` | UI command: toggles a once-initialised static flag; on the first call of each pair sets the movie named by the argument on the cinematic state (0x48f0b0) and pushes it on theGame; returns the old flag | zAnim.md: key "PlayMPEGNoFade" (0x44a99c), next to UIPlayMPEG | high |
| 277 | 0x1d36b0 | free function |  | `UIMC_Changed` | UI command: 0x31e370(theMemCard, 1), the card poll | zAnim.md: key "MC_Changed" (0x44a9f0), between UIMC_ChDir and UIMC_Uninit | high |
| 278 | 0x1d69c0 | member | `CWrappedText` | `CWrappedText` | constructor: CRenderableString's constructor, then the CWrappedText tables, colour 0xff x4, C2DBitmap and the wrap fields | zAnim.md (`__ct__12CWrappedTextFv`): the tables it stores; callers CMenuStack::GetPopUp, CScrollSpec::CreateDisplayObj | high |
| 279 | 0x1d7db0 | free function | `@unnamed@zanim_menu_cpp@` | `OnDoAllSelCharsHaveWeapon` | UI command: splits the argument (a comma list of weapons, tokenizer 0x1d80b0) into a byte vector and tests the selected characters' weapon lists against it | zAnim.md proposed it: key "DoAllSelCharsHaveWeapon" (0x44a9fc); it sits among the unnamed namespace's On<Key> handlers | medium |
| 280 | 0x1d80b0 | member | local tokenizer of `OnDoAllSelCharsHaveWeapon` (class unnamed) | `Next` | (this = {text, pos, std::string token}): skips spaces and commas, clears the token, appends characters up to the next comma or the end | zAnim.md: a comma-list tokenizer step called only by 0x1d7db0; the class is not named anywhere, `Next` is a guess | low |
| 281 | 0x1d8170 | compiler-made | `Metrowerks::details::compressed_pair_imp<std::allocator<EQUIP_ITEM>,unsigned_int,1>` | `compressed_pair_imp` | template constructor: *this = second, returns this; the byte copy of the unsigned-int instance 0x1d6400 | zAnim.md; element type from the one-byte weapon-id vector of 0x1d7db0 (a guess) | medium |
| 282 | 0x1d82d0 | free function | `@unnamed@zanim_menu_cpp@` | `OnChooseDefaultEquipmentOnly` | UI command: for each character bit of the "UiCharSet" valve copies the default character type's weapon list into the custom type's and sets up its first two weapons again (SetupCharacterWeapon), then UpdateCharWeaponUiVars | key "ChooseDefaultEquipmentOnly" (0x44aa08), registered directly like the namespace's On<Key> handlers; zAnim.md proposed `ExecuteChooseDefaultEquipmentOnly` (beside ExecuteChooseDefaultEquipment, which the table does not hold) | medium |
| 283 | 0x1d91e0 | compiler-made | `std::__vector_imp<EQUIP_ITEM,std::allocator<EQUIP_ITEM>,1>` | `insert` | vector insert(pos, n, value) for one-byte elements: "vector::insert length error", grows the buffer (doubling), shifts and fills | zAnim.md; the message is MSL vector's; element type as 0x1d8170 (guess) | medium |
| 284 | 0x1d95b0 | compiler-made | `Metrowerks::details::compressed_pair_imp<std::allocator<EQUIP_ITEM>,unsigned_int,1>` | `swap` | swaps the words at *a and *b; byte copy of the neighbouring compressed_pair_imp::swap 0x1d91c0 | zAnim.md; caller 0x1d91e0 | medium |
| 285 | 0x1d9740 | compiler-made | `std::__vector_deleter<EQUIP_ITEM,std::allocator<EQUIP_ITEM>>` | `destroy` | the trivial element-destroy loop of the one-byte vector (walks the size at +4 down to 0, nothing to destroy), then size = 0 | zAnim.md; callers 0x1d91e0 and the vector destructor 0x1d9620 (row 30); the member name is a guess | low |

## src/gamez/zArchive/zar_main.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 286 | 0x1d9a70 | member | `zar::CKey` | `~CKey` | deleting destructor: frees the buffer at +8 (operator delete), deletes this when the flag > 0 | zArchive.md: the temporary key's destructor in NewKey, Insert, ~CZAR and CSaveManager::Save; next function zar::CKey::~CKey is the prototype's | medium |

## src/gamez/zCamera/camera.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 287 | 0x1e9e40 | free function |  | `StopHeartbeat` | stops and releases the playing heartbeat sound instance (static pCRam0048d498), clears it | small-2.md proposed it; caller CMission::ReOpen_Unload1 | medium |
| 288 | 0x1e9e80 | free function |  | `LoadHeartbeatSounds` | looks up SND_HEARTBEAT_SLOW_LOOP, _MEDIUM_LOOP, _FAST_LOOP into three statics, stops any playing instance | small-2.md proposed it; callers CMission::Open, CMission::ReOpen_Load | medium |

## src/gamez/zCharacter/char_type.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 289 | 0x24b6c0 | member | `CCharacterType` | `GetSound` | (this, index): the sound handle at +0x120 + 4 * index for an index 0 to 66 ('B'), else 0 | small-3.md proposed `GetSound__14CCharacterTypeCF15CHARACTER_SOUND`; caller CSealCtrlAi::OnStunDamage, which looked the sound up by name in the prototype | medium |
| 290 | 0x24edd0 | static member | `CCharacterType` | `ResetAll` | walks CCharacterType::m_char_list; for each type whose +0 is set clears +0 and +0x18 (the first time also an empty loop over m_gear_list) | small-3.md proposed it; caller CMission::Close after CleanupTemporary; the name is a guess | medium |

## src/gamez/zEntity/ent_main.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 291 | 0x1f1310 | compiler-made | `std` | `remove_if<std::list<CEntity*>::generic_iterator<0>, bool (*)(CEntity*)>` | (out, first, last, pred): finds the first element the predicate accepts, then remove_copy_if 0x1f1470 over the rest; returns the new end | small-1.md: byte twin of the CSched_Task instance 0x30b740; caller CEntity::PurgeInvalid (row 45) | high |

## src/gamez/zFTS/fts_action.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 292 | 0x200c30 | static member | `CNodeAction` | `PauseActions` | (bool pause): walks CNodeAction::m_actions; with true pauses each action's running CZAnim (+0x10), with false resumes the paused ones | zFTS.md: the static list and its place before CNodeAction::SyncActionsMP; callers CZNewHudMap::SwitchToCompassMap and SwitchMapToFullScreen; the name is a guess | medium |

## src/gamez/zFTS/fts_controller.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 293 | 0x20d220 | static member | `CCtrlrConfigs` | `ApplyConfig` | (CSealCtrl*): reads g_pCurrentConfig's selector (+0xb); by the controller's byte at that index (1 or 3) takes setting +7 or +8 and sets the controller's flags +0x1c9 (== 1) and +0x1f1 (== 2) | zFTS.md proposed `ApplyConfig__13CCtrlrConfigsFP9CSealCtrl`; caller CSealCtrl::PreTick; before CCtrlrConfigs::SetButtonState. its first argument is the controller, so it is a static or a free function of fts_controller.cpp | low |

## src/gamez/zFTS/fts_mission.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 294 | 0x1f7fa0 | member | unknown (ladder table element) | `fn_001f7fa0` | returns this + 8 (`jr ra; addiu v0,a0,8`), an out-of-line inline accessor | zFTS.md; the only caller CMission::CreateLadderTable; nothing names the field | low |
| 295 | 0x1f7fb0 | member | unknown (ladder table element) | `fn_001f7fb0` | returns the word at +4 | zFTS.md; the same caller | low |
| 296 | 0x1f7fc0 | member | `CBBox` | `Build` | (this = min/max box, const CPnt3D pts[8]): starts min and max at the first point and widens them over the other seven | zFTS.md guessed `CBBox::Build(const CPnt3D*)`; callers CMission::CreateLadderTable (after its 8-point Transform) and zdb::CGrid::gridAddNodeToGrids; CBBox8::Build (0x1f8190) follows it | medium |
| 297 | 0x1f9210 | free function |  | `ftsReticuleAllowed` | returns 0 when the player has no controller or its menu state is 2, 3, 4 or 5 (CSealCtrl::MenuStateIs, row 225), else 1 | zFTS.md proposed it; caller BitmapReticule::HudTick; between CMission::Tick and _OnMissionComplete, next to the file's fts* functions | medium |
| 298 | 0x1fbcd0 | free function |  | `HUDRegisterCommands` | registers the eight HUD zAnim commands (HUD_ON, HUD_OFF, HUD_LETTERBOX_ON / _OFF, HUD_TRIGGER_MISSION_CAM, HUD_START_DEFUSE_TIMER, HUD_STOP_DEFUSE_TIMER, HUD_TRIGGER_POPUP) with their parse and tick functions | zFTS.md: what CMission::Init (its only caller) did inline in the prototype; the HUD<…> prefix of the functions it registers; the name is a guess | medium |
| 299 | 0x1fbe50 | free function |  | `HUDTriggerPopupTick` | tick of HUD_TRIGGER_POPUP: the name of the command's index (+4) from ZAnim, then hud 0x420c20 (matches it against the "AnimCmd" popups); returns 1 | zFTS.md proposed it: registered by 0x1fbcd0 under that string; the file's HUD<Command>Tick pattern | high |
| 300 | 0x1fbe80 | free function |  | `HUDTriggerPopupParse` | parse of HUD_TRIGGER_POPUP: for a list with a string argument, calloc 8 at fts_mission.cpp:0x466, command id 0x20, stores ZAnim AddName of the string at +4 | zFTS.md proposed it; the HUD<Command>Parse pattern | high |
| 301 | 0x1fbff0 | free function |  | `HUDStopDefuseTimerTick` | tick of HUD_STOP_DEFUSE_TIMER: CZWeapon::ClearTimer, returns 1 | zFTS.md: registered with that string (parse 0x1fc010); the map's pairing with HUDStartDefuseTimerTick was wrong (the start tick is 0x1fc080) | high |
| 302 | 0x1fc010 | free function |  | `HUDStopDefuseTimerParse` | parse of HUD_STOP_DEFUSE_TIMER: calloc 4 at fts_mission.cpp:0x443, command id 0x10, no arguments | zFTS.md; the HUD<Command>Parse pattern | high |

## src/gamez/zFTS/fts_net_persona.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 303 | 0x20adc0 | static member | `CZPersonaState` | `PermitAllVoice` | for every persona in m_PersonaList whose network object is a player ('P') with a voice address (+0x2ac) calls CZNetVoice::ServerPermit on theVoice | zFTS.md proposed it; caller zDoClientLeavesCallback; next to ClearPersonaList | medium |
| 304 | 0x20ae80 | static member | `CZPersonaState` | `IsVotedOut` | counts the personas of the local player's team (terrorist bit 0x100, else seal bit 1) and returns whether the votes against the player (0x20b090) exceed half of them | zFTS.md (it replaced the prototype's NumActiveTerrorists / NumActiveSeals loops); callers VoterPacketHandler and UIHaveBeenBannedFromGame (through its thunk 0x1d2780); the name is a guess | medium |
| 305 | 0x20b090 | static member | `CZPersonaState` | `NumVotesAgainst` | counts the personas whose vote byte +0x2d3 is set | zFTS.md: VoterPacketHandler prints it as "Voting: You have %d votes against you."; the map's pairing with NumActiveSeals was wrong | medium |
| 306 | 0x20b140 | static member | `CZPersonaState` | `GetVote` | (id): byte +0x2d4 of the persona whose id byte +0x2d1 is id, else 0 | zFTS.md proposed it; callers OrdersMenu::RefreshContext, OrdersMenu::ScrollForward | medium |
| 307 | 0x20b200 | static member | `CZPersonaState` | `SetVote` | (id, value): stores value in byte +0x2d4 of that persona | zFTS.md proposed it; caller SendVoteMessage | medium |
| 308 | 0x20b2c0 | static member | `CZPersonaState` | `SetVotedAgainst` | (id, value): stores value in byte +0x2d3 (a vote against the local player) of that persona | zFTS.md: caller VoterPacketHandler, which the counter 0x20b090 reads back; the name is a guess | medium |

## src/gamez/zFTS/fts_net_seal.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 309 | 0x208640 | compiler-made | `std::__vector_imp<T,std::allocator<T>,0>` (T 8 bytes, the element of CZSealState's m_RemoteGuyList) | `insert` | vector insert(pos, n, value) for 8-byte elements ("vector::insert length error"), grows, moves and fills | zFTS.md; caller CZSealState::RemoteSealCreationCallback; the element type is not named | medium |
| 310 | 0x208a60 | compiler-made | `Metrowerks::details::compressed_pair_imp<…>` (same vector) | `swap` | swaps the words at *a and *b | zFTS.md (std::swap of a pointer); callers the insert 0x208640 and reserve 0x208b70 | medium |
| 311 | 0x208a80 | compiler-made | `std::__vector_deleter<T,std::allocator<T>>` (same vector) | `clear` | walks the 8-byte elements (nothing to destroy), size (+4) = 0 | zFTS.md; callers RemoteSealUpdateCallback, UnloadRemoteGuyList, 0x206dd0 | medium |
| 312 | 0x208b70 | compiler-made | `std::__vector_imp<T,std::allocator<T>,0>` (same vector) | `reserve` | reserve(n): "vector::reserve length error", operator new(n * 8) ("Memory allocation failure"), copies the elements, frees the old buffer | zFTS.md; caller __sinit_fts_net_seal.cpp with 14 | medium |
| 313 | 0x208d20 | compiler-made | `Metrowerks::details::compressed_pair_imp<…>` (same vector) | `first` | returns this (`jr ra; move v0,a0`): the allocator accessor | zFTS.md; caller the reserve 0x208b70 | medium |
| 314 | 0x208da0 | compiler-made | `std::vector<T,std::allocator<T>>` (same vector) | `vector` | constructor: clears the three words | zFTS.md; caller __sinit_fts_net_seal.cpp, for m_RemoteGuyList | medium |

## src/gamez/zFTS/fts_remote.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 315 | 0x205e10 | free function |  | `fn_00205e10` | DME message handler (fiii, packet in a3): for net game type 3 (theMission +0x594, +0xeb) turns three signed bytes into a vector and passes the body of the object index, a short and a byte to CZSealBody 0x287500 (empty, row 147); returns 8 | zFTS.md: registered by DMERegister between PushBlend and ActionAnim; the message is not identified, so no <Name>PacketHandler can be given | low |

## src/gamez/zMPEG/audiodec.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 316 | 0x350c20 | free function |  | `iopGetArea` | (int* p0, int* n0, int* p1, int* n1, AudioDec*, int pos): from the IOP play position computes the two IOP destination areas of the next transfer in 1024-byte units (nothing when the position is within 1024 bytes) | zMPEG.md: the SDK audio-decoder sample's static of that name; called only by audioDecSendToIOP, which had it inline | medium |

## src/gamez/zMPEG/strfile.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 317 | 0x3520d0 | free function |  | `fn_003520d0` | (tags, image, a, b, c): setLoadImageTagsYX(tags, image, 0, a, b, c) | zMPEG.md: a fill variant of setLoadImageTags used once by startPss to load the black block over the frame; no sample name is known for it | low |

## src/gamez/zNetwork/zNetCnf.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 318 | 0x403e30 | static member | `CNetCnf` | `GetInterfaceList` | (out records, max): sceInetGetInterfaceList on CNetCnf's libnet buffers; for each interface (up to max) clears a 0x240-byte record and reads three interface values (sceInetInterfaceControl 8, 2, 3); returns the count | zNetwork-b.md (it took over what CSMAddDev::GetHWAddr did); the statics libnetCd / libnetBuffer of CNetCnf; caller UINetGetInterfaceList | medium |
| 319 | 0x403f80 | static member | `CNetCnf` | `PollStatus` | when ezNetCtl was started (0x5803c4 > 0): ezNetCtlGetStatus; status 3 returns 1; status 5 calls the lobby's message callback (theLobby +0x58) with "MP_MEDIUS_ERROR"; else 0 | zNetwork-a.md (an ezNetCtl status poll; zNetCnf.cpp by position); caller CZNetwork::zNetUpdate; the class and name are guesses (no `this`) | low |
| 320 | 0x404010 | static member | `CNetCnf` | `Close` | when ezNetCtl was started: ezNetCtlDownInterface(0), clears the started count, 0x432070 (exitEzNetCtl in zNetwork-a.md); returns whether it was started | zNetwork-a.md; caller CZNetwork::zNetClose; before CNetCnf::InitFromCombo; the class and name are guesses | low |

## src/gamez/zNetwork/zNetMedius.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 321 | 0x33d270 | member | `CZOnlineLobby` | `GetMediusWorldID` | returns the zNetMedius.cpp static MediusWorldID (gp) | zNetwork-c.md; callers CZNetVoice::IAmNewSessionMaster, Init, WorkerThread pass theLobby in a0 and hand the result to PTTServer_Start; the class rests on that a0 only (it may be a free getter) | medium |
| 322 | 0x33ff70 | compiler-made | `Metrowerks::details::compressed_pair_imp<std::allocator<MediusChatFwdMessage>,…>` (the chat vector) | `first` | returns its argument (`jr ra; move v0,a0`) | zNetwork-a.md: called on the chat vector (+0x1c) by cbFilterChat and cbChatMessage before the insert that drops the oldest message; the element type is the note's guess | low |
| 323 | 0x345b10 | member | `CZOnlineLobby` | `GetClanMessages` | (this, bool show): optionally sets uiv_MediusMOTD to "Retrieving messages from server...", builds the request (session key, StoredClanInfo +0x1c, start 1, count 999) and sends MediusGetMyClanMessages with callback cbGetMyClanMessages | zNetwork-a.md; the only caller UIGetClanMessages (0x1d2ab0) passes theLobby; between cbSendClanMessage and cbGetMyClanMessages | medium |
| 324 | 0x349040 | member | `CZOnlineLobby` | `GetUsagePolicy` | (this): when +0x81 is set, the UI variables UsagePolicy ("Retrieving Usage Policy.....") and TempUsagePolicy, then MediusGetPolicy with callback cbGetPolicyRequest | zNetwork-a.md (the request moved out of LobbyActiveStateHandler); caller UIGetUsagePolicy (0x1d2ae0) with theLobby | medium |
| 325 | 0x34a3b0 | static member | `BriefingRoom` | `delstale` | remove_if predicate (RoomGame*): a persistent game (its virtual +8 true) gets id (+0x1c) -1 and stays; a transient one flagged at +0x208 is deleted and removed | zNetwork-a.md proposed it (beside deltrans; GetGameList sets +0x208 on every game before MediusGetGames) | medium |
| 326 | 0x34a7b0 | free function |  | `RequestGameInfo` | (C2D*, RoomGame*, int seconds): for a game with an id whose stamp (+0x204) is older than the interval (zVid +0x20 clock) and that passes 0x3aaa20, sends MediusGetGameInfo (cbGameInfo) and MediusGetWorldSecurityLevel (cbGameSecurityCheck) and restamps it | zNetwork-a.md proposed it (the prototype cbGameList did this inline); callers cbGameList (twice), GetGameList, CZOnlineLobby::RefreshGameInfo (row 69) | medium |

## src/gamez/zParticle/zparticle_buf.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 327 | 0x2399f0 | static member | `Particle` | `Flush` | builds an 11-quadword scratchpad packet (DMA tag 0x1000000a, then ten VIF FLUSH 0x11000000 codes) and sends it with zSysFifoKick | small-3.md proposed it; caller Particle::Draw | medium |
| 328 | 0x239b10 | static member | `Particle` | `SetLensTint` | (bool, const CPnt3D&): stores the flag in a gp byte (0x48d880), the colour * 0.33 in three statics (0x518d10) and 90.9 in 0x518d1c | small-3.md proposed it; callers CZKit::Apply_LensEffects (twice), CZKit::Init | low |

## src/gamez/zParticle/zparticle_instance.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 329 | 0x239e80 | member | `Particle::Destruction_Instance` | `AddVisual` | (this, CVisual*): adds the visual to the instance's node (+0x44), sets bit 7 of the node's +0x5c when the visual is transparent and not bump-mapped, copies +0x6c to the node's +0x9c, calls the node's virtual +0x34 (SetActive) with 1 | small-3.md; callers Particle::Create3Sided and CreateVisuals; first function of zparticle_instance.cpp, before Destruction_Instance::Tick | medium |

## src/gamez/zRender/zrndr_pipe.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 330 | 0x249f10 | compiler-made | unknown (a CGSTexBuffer member's type) | `fn_00249f10` | returns its argument (`jr ra; move v0,a0`); callers pass a CGSTexBuffer's +0x1c and InterruptFromVIF1 reads the word it returns | small-3.md: an out-of-line header inline (a reference accessor); callers InterruptFromVIF1, zdb::CTexManager::DestroyBuffers; nothing names the member | low |

## src/gamez/zSeal/seal.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 331 | 0x252a10 | member | `CCompassAnchor` | `GetCurrentPoint` | (this, CPnt3D* out): with a current point index (+0x18, not -1) copies that point of the vector at +0x28 out, notes the index in +0x1c and returns true; false without one | zSeal-f.md proposed it; caller MapCompass::Tick | medium |
| 332 | 0x252aa0 | member | `CCompassAnchor` | `AddPoint` | (this, const CPnt3D&): returns the index of an equal point in the CPnt3D vector at +0x20, else appends it (vector insert) and returns the new last index | zSeal-f.md proposed it; caller CZSealBody::CreateHostageAnchor (row 223) four times | medium |

## src/gamez/zSeal/seal_ai.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 333 | 0x25fa70 | free function |  | `_check_goto_cell` | MAP_FOREACH-style callback (closure, cell): finds the cell of the closure's location (+0xc) on its map (dummy_cell fallback), tests it and records it for the search | zSeal-b.md: a helper of CSealCtrlAi::FindDeployLoc (0x25f260, row 91) only; its address is taken, no direct caller; the name is a guess | low |
| 334 | 0x260040 | member | unknown (a new AI tracker record, seal_ai.cpp) | `GetElapsed` | (this): 0 when the level (+8) is 0, else the mission clock (theMission +0x60) minus the start time (+0) | zSeal-b.md, zSeal-f.md describe the record (start time, value, level, flag, location, seal, byte); caller CAiSPathRecover::Tick; class and name are guesses | low |
| 335 | 0x260070 | member | unknown (same record) | `Update` | (dt, this, CSealCtrlAi*, level): stamps the frame (zVid +0x10); same level: value += dt, flag from the controller's +0x3b8, returns 2; level 0: value -= dt * 0.5, at 0 resets and returns 1; a higher level: takes it, restarts the clock, returns 1 | zSeal-b.md, zSeal-f.md (update by priority 1-4); callers CSealCtrlAi::PostTick and the three below | low |
| 336 | 0x260160 | member | unknown (same record) | `UpdateCell` | (dt, this, ctrl, CAiMapLoc*): Update at level 1; when still level 1 and the map cell changed restarts the record and keeps the new cell (+0x14) | zSeal-b.md (level-1 update by map cell); callers CSealCtrlAi::PathFollowTick, CZSealBody::PostComputeNextPosition | low |
| 337 | 0x260270 | member | unknown (same record) | `UpdatePos` | (this, dt, const CPnt3D*): Update at level 2; on a change stores the point at +0x20 and its map location (AiMaps GetLocation) at +0x14 | zSeal-b.md (level-2 update); caller CZSealBody::PostComputeNextPosition | low |
| 338 | 0x2602e0 | member | unknown (same record) | `UpdateSeal` | (dt, this, ctrl, CZSealBody* other, bool): when CAiSAvoid::ShouldAvoid (0x2fa470, row 132) holds for the other seal, Update at level 4 and keeps the other seal (+0x18), its map location (+0x14) and the flag (+0x1c) | zSeal-b.md (level-4 update); callers CSealCtrlAi::PathFollowTick, CZSealBody::CollidePlayers | low |
| 339 | 0x260410 | member | unknown (same record) | `Reset` | level, value, seal and byte = 0, start time = the mission clock | zSeal-b.md, zSeal-f.md; callers CAiSAvoid::OnSignal, CAiSPathRecover::Tick | medium |
| 340 | 0x260430 | member | `CSealCtrlAi` | `LookAroundTick` | (this): for an entity index inside the static range record (0x51ff40) and with neither AI state 10 nor 4 (FindAiState), picks a look direction from the map (GetClosestDir, CountMapVisDir) and sets it with SetLookDirW / SetLookTimer | zSeal-b.md proposed it; caller CSealCtrlAi::SensorPreTick. The first sheet left it out because the evidence names CSealCtrlAi and CSealCtrl: the body casts `this` to CSealCtrl and calls CSealCtrlAi::FindAiState on it, so it is a CSealCtrlAi member (a CSealCtrl subclass) | medium |
| 341 | 0x260860 | member | unknown (a 5-word range record, seal_ai.cpp) | `Init` | (this, base, len, limit): base, base + len, len, limit, and the overflow past the limit (or len when len >= limit) | zSeal-b.md; callers __sinit_seal_ai.cpp (the static record 0x51ff40), CSealCtrlAi::PreTick, PostTick, LookAroundTick 0x260430; the note's "constructor" fits its __sinit use, but it is also called on a live record, so Init | low |
| 342 | 0x26c890 | member | `CSealCtrlAi` | `SetTarget` | (this, CEntity*): finds the entity in the body's target list (m_entity +0xcc, CTargetList::FindTarget) and, when present, calls this's virtual +0xa0 (SetTarget(CTarget*)) | zSeal-c.md proposed the overload `SetTarget__11CSealCtrlAiFP7CEntity`; callers CAiSGoto::Tick, CAiSRush::Tick; next to CSealCtrlAi::SetTarget | medium |
| 343 | 0x26eb20 | free function |  | `FindSealAtLoc` | (CZSealBody*, CAiMapLoc*): the first live seal (type 2, alive bit, not down) in the body's target list (+0xd0 count, +0xd4 data, 0x28 per entry) whose map cell is the given one, else 0 | zSeal-c.md proposed it; callers CSealCtrlAi::PathFollowTick, CSealCtrlAi::LookAhead (row 112) | low |
| 344 | 0x26ecb0 | free function |  | `FindSealInRange` | (CZSealBody*, float* range, mask): squares *range, returns the first live seal in the target list within it whose side flags (+0xc4) match the mask, else 0 | zSeal-c.md proposed it; caller CAiSBreach::Tick | low |
| 345 | 0x26ee30 | member | `CSealCtrlAi` | `FindEnemyNear` | (radius, this, const CPnt3D*): the first live seal of another side (+0xc4 masks disjoint) in the body's target list within the radius of the point, skipping when the AI itself is alive and of type 3 | zSeal-c.md proposed it; caller CAiSGoto::Tick | low |
| 346 | 0x276ca0 | compiler-made | `std::__list_deleter<A,std::allocator<A>>` (A: a 12-byte timed callback of CAiSAnimate) | `~__list_deleter` | destructor: erase(first, last) of the whole list (0x276f90), deletes when the flag > 0 | zSeal-d.md; caller CAiSAnimate::~CAiSAnimate for its list at +0x30 | medium |
| 347 | 0x276d10 | compiler-made | `std::__list_deleter<B,std::allocator<B>>` (B: a second new element type) | `~__list_deleter` | the same for the list at +0x3c, with erase 0x277240 | zSeal-d.md; caller CAiSAnimate::~CAiSAnimate | medium |
| 348 | 0x276f90 | compiler-made | `std::__list_deleter<A,std::allocator<A>>` | `erase` | erase(first, last): unlinks the range, deletes each node, decrements the size; returns last | zSeal-d.md (byte copy of the prototype's list<CPnt3D> erase, which the release no longer has); caller 0x276ca0 | medium |
| 349 | 0x277040 | compiler-made | `std::__list_deleter<A,std::allocator<A>>` | `erase` | erase(it): unlinks and deletes one node, decrements the size, returns the next | zSeal-d.md; caller CAiSAnimate::Tick (list at +0x30) | medium |
| 350 | 0x2770c0 | compiler-made | `std::__list_deleter<A,std::allocator<A>>` | `insert` | insert(pos, value): operator new(0x14), copies the 12-byte element (float, function, argument), links it before pos, size + 1 | zSeal-d.md; caller CAiSGrenade::Tick (three times) | medium |
| 351 | 0x277210 | compiler-made | `Metrowerks::details::compressed_pair_imp<…>` (list<A>) | `first` | returns this | zSeal-d.md: the `first` accessor where the CPnt3D insert called `first`; caller 0x2770c0 | medium |
| 352 | 0x277220 | compiler-made | `Metrowerks::details::compressed_pair_imp<…>` (list<A>) | `second` | returns this + 4 | zSeal-d.md (the `second` accessor by position); caller the list<A> insert 0x2770c0 | medium |
| 353 | 0x277230 | compiler-made | `Metrowerks::details::compressed_pair_imp<…>` (list<A>) | `compressed_pair_imp` | copy constructor: *this = *src, returns this | zSeal-d.md; caller 0x2770c0 | medium |
| 354 | 0x277240 | compiler-made | `std::__list_deleter<B,std::allocator<B>>` (B: 16 bytes, two floats, a function and its argument) | `erase` | erase(first, last), the same body as 0x276f90 | zSeal-d.md; caller the list<B> destructor 0x276d10 | medium |
| 355 | 0x2772f0 | compiler-made | `std::__list_deleter<B,std::allocator<B>>` | `insert` | insert(pos, value): operator new(0x18), copies the 16-byte element, links it, size + 1 | zSeal-d.md; caller CAiSGrenade::Tick | medium |
| 356 | 0x277450 | compiler-made | `Metrowerks::details::compressed_pair_imp<…>` (list<B>) | `first` | returns this | zSeal-d.md; caller 0x2772f0 | medium |
| 357 | 0x277460 | compiler-made | `Metrowerks::details::compressed_pair_imp<…>` (list<B>) | `second` | returns this + 4 | zSeal-d.md; caller 0x2772f0 | medium |
| 358 | 0x277470 | compiler-made | `Metrowerks::details::compressed_pair_imp<…>` (list<B>) | `compressed_pair_imp` | copy constructor: *this = *src | zSeal-d.md; caller 0x2772f0 | medium |

## src/gamez/zSeal/seal_aievent.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 359 | 0x2f2f30 | compiler-made | `std::__vector_imp<CAiMap::scanline,std::allocator<CAiMap::scanline>,0>` | `operator[]` | returns data (+8) + index * 12 | zSeal-e.md: the non-const operator[] of the scanline vector (the prototype had only the const one, 0x197020); caller CSealCtrlAi::HandleEvent on the map +0x118 | medium |
| 360 | 0x2f2f50 | member | `CAiMap` | `IsValidLoc` | (this, const CAiMapLoc&): z below +0x1c and x below +0x18 | zSeal-e.md proposed it (an inline emitted out of line); caller CSealCtrlAi::HandleEvent | medium |

## src/gamez/zSeal/seal_aifollow.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 361 | 0x2f6fc0 | free function |  | `InFireCone` | (dist, width, scale, CPnt3D* …): builds a wedge in front of and beside a direction (side vector (z, 0, -x), Scale, Add) and tests the points with PointInWedgeXZ (0x2f7290, row 118) | zSeal-c.md: called only by CSealCtrlAi::CheckFollowFireLane (0x2f63c0, row 117), which calls it the cone test; the name is a guess | low |

## src/gamez/zSeal/seal_aistate.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 362 | 0x2f09f0 | compiler-made | `std` | `remove_if<std::list<CAiState*>::generic_iterator<0>, bool (*)(CAiState*)>` | (out, first, last, pred): finds the first element the predicate accepts, then remove_copy_if 0x2f0b20 over the rest | zSeal-e.md; byte twin of CEntity's 0x1f1310; caller CSealCtrlAi::StateTick (predicate 0x2ee9e0, then erase) | high |
| 363 | 0x2f0ae0 | compiler-made | `std::__list_deleter<A,std::allocator<A>>` (CAiSAnimate's list at +0x30) | `__list_deleter` | constructor: size 0, both links to the end node | zSeal-e.md: CAiState::Create builds the CAiSAnimate list at +0x30 with it (the twin 0x2f0b00 builds +0x3c) | medium |
| 364 | 0x2f0b00 | compiler-made | `std::__list_deleter<B,std::allocator<B>>` (list at +0x3c) | `__list_deleter` | the same constructor | zSeal-e.md; the two twins are told apart by their call sites in CAiState::Create | medium |
| 365 | 0x2f0b20 | compiler-made | `std` | `remove_copy_if<std::list<CAiState*>::generic_iterator<0>, ..., bool (*)(CAiState*)>` | copies the elements the predicate rejects to the output iterator; returns the output end | zSeal-e.md: twin of the named remove_copy_if over list<CSched_Task*> (0x30b830); caller 0x2f09f0 | high |

## src/gamez/zSeal/seal_anim.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 366 | 0x277ec0 | member | `CZSealBody` | `BlendPartPoses` | CBody::BlendPose (0x1e3c20, row 35) of the body (+0xfa8) toward +0x110 for each body part held at +0x26c ... (the part index at part +0x24) | zSeal-e.md: a sibling of SavePartPoses (0x277ce0, row 133), the same part list; caller SmoothBlendWeights (0x2780f0, row 134); the name is a guess | medium |

## src/gamez/zSeal/seal_body.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 367 | 0x27aac0 | free function |  | `StabBuddyCallback` | `j CZSealBody::StabBuddy` (a0, a1 passed on); the program shows it as a thunk under StabBuddy's name | xcheck-1.md, zSeal-b.md: the callback AlignToStabBuddy (0x27a890, row 138) passes, as RestrainBuddyCallback (0x27a650, row 137) is for RestrainBuddy; the prototype's PickupBuddyCallback__FPvPv is free | medium |

## src/gamez/zSeal/seal_env.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 368 | 0x2a5000 | member | `CZSealBody` | `IsClimbing` | true when the current anim (+0x46c) is the base anim of ClimbCrate, ClimbMedium, Stand2Hang, ClimbOver, StepUp or Stand2Ladder | zSeal-a.md proposed it; caller CZKit::Reload; next to CZSealBody::IsChangingWeapons | medium |
| 369 | 0x2b1a30 | free function |  | `AccumulateWorldBounds` | (zdb::CNode*, bounds): for an active visible node multiplies the matrix stack by its matrix, recurses into the active children, transforms the node's box corners and widens the bounds | zSeal-a.md proposed it; recursive, called by itself and 0x2b1d10 | low |
| 370 | 0x2b1d10 | free function |  | `GetWorldBounds` | (node, bounds): pushes the identity on the matrix stack (CStack m_top / m_pointer), AccumulateWorldBounds, pops; returns the bounds | zSeal-a.md proposed it; caller zdb::CRenderMap::Update | low |

## src/gamez/zSeal/seal_kit.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 371 | 0x2bf820 | static member | `CZKit` | `GetLaseDelay` | returns the float the program names CZKit::m_lase_delay (0x48cb10, 16.0) | zSeal-a.md guessed GetDeployRange; the global's name rests on one witness (single-aligned), but the prototype's m_lase_delay holds the same 16.0; callers CAiSDeploy::Tick, CSealCtrlAi::OnCommand; between CZKit::SetCurItemState and sealSaveFireModes | medium |

## src/gamez/zSeal/seal_sensors.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 372 | 0x2c0cc0 | member | `CZSealBody` | `GetConcealment` | (this, bool force): unless forced, the value cached at +0x384 for this frame (stamp +0x388, zVid +0x10); else samples cover around the cell (0x2c0e40) and the world's light at the position twice (0x231930), mixes them with three mission factors (theMission +0xd0..+0xd8), clamps and caches | zSeal-c.md proposed CSealCtrl::GetConcealment; the one call site in CSealCtrl::ComputeVisibility passes a CZSealBody, so the class is CZSealBody; the name is a guess | low |
| 373 | 0x2c0e40 | free function |  | `SampleCellCover` | (const CAiMapLoc*, float*, float*): averages two cell properties over the cell and its eight neighbours (CAiMap::neighbor, dummy_cell fallback) | zSeal-c.md proposed it; caller 0x2c0cc0 | low |
| 374 | 0x2c4600 | member | unknown (a ring record of CSealCtrlAi::PostTick) | `GetIndex` | (this, index): index -1 means the current one (+8); returns (start + index) mod size (+0xc), 0 for size 0 | zSeal-c.md (a ring-buffer index helper); caller CSealCtrlAi::PostTick | low |
| 375 | 0x2c52c0 | compiler-made | `std::__list_deleter<R,std::allocator<R>>::generic_iterator<0>` (R: the record 0x2c5370 fills) | `generic_iterator` | iterator constructor: *this = node, returns this | zSeal-c.md: one of 12 instances byte-equal to MSL __list_deleter members; caller CSealCtrlAi::PreTick; the element type is a guess | medium |
| 376 | 0x2c52d0 | compiler-made | `std::__list_deleter<R,std::allocator<R>>::generic_iterator<1>` | `generic_iterator` | the same constructor (second iterator kind) | zSeal-c.md; caller CSealCtrlAi::PreTick; which of the two is const is not told by the bytes | low |
| 377 | 0x2c52e0 | compiler-made | `Metrowerks::details::compressed_pair_imp<…>` (list<R>) | `first` | returns this | zSeal-c.md; caller CSealCtrlAi::PreTick | medium |
| 378 | 0x2c52f0 | compiler-made | `std::__list_deleter<R,std::allocator<R>>` | `tail` | returns this + 4 (the end node) | zSeal-c.md names `tail` among the instances; caller CSealCtrlAi::PreTick | medium |
| 379 | 0x2c5300 | compiler-made | `std::__list_deleter<R,std::allocator<R>>` | `~__list_deleter` | destructor: erase(first, last) 0x2c53b0, deletes when the flag > 0 | zSeal-c.md; caller CSealCtrlAi::PreTick (its local list) | medium |
| 380 | 0x2c5370 | member | unknown (record R of CSealCtrlAi::PreTick) | `Init` | (a, b, c, this, const CPnt3D*): +0x14 = a, +0xc = b, +0x10 = c; with a point copies it to +0x18 and sets +9, else clears +9 | zSeal-c.md (the constructor of the new list's elements, a guess); caller PreTick (twice); the store into a live node rather than new memory makes Init likelier | low |
| 381 | 0x2c53b0 | compiler-made | `std::__list_deleter<R,std::allocator<R>>` | `erase` | erase(first, last): unlinks, deletes each node, size - 1 per node | zSeal-c.md; caller 0x2c5300 | medium |
| 382 | 0x2c5460 | compiler-made | `std::__list_deleter<R,std::allocator<R>>` | `erase` | erase(it): unlinks and deletes one node, returns the next | zSeal-c.md; caller CSealCtrlAi::PreTick | medium |
| 383 | 0x2c54e0 | compiler-made | `std::__list_deleter<R,std::allocator<R>>` | `insert` | node insert: operator new(0x10) ("Memory allocation failure"), copies an 8-byte value, links it before pos, size + 1 | zSeal-c.md; caller CSealCtrlAi::PreTick; the 8-byte payload says the element is 8 bytes (a pointer pair), not the record itself | medium |
| 384 | 0x2c5630 | compiler-made | `Metrowerks::details::compressed_pair_imp<…>` (list<R>) | `first` | returns this | zSeal-c.md; caller 0x2c54e0 | medium |
| 385 | 0x2c5640 | compiler-made | `Metrowerks::details::compressed_pair_imp<…>` (list<R>) | `second` | returns this + 4 | zSeal-c.md; caller 0x2c54e0 | medium |
| 386 | 0x2c5650 | compiler-made | `Metrowerks::details::compressed_pair_imp<…>` (list<R>) | `compressed_pair_imp` | copy constructor: *this = *src | zSeal-c.md; caller 0x2c54e0 | medium |
| 387 | 0x2c5660 | compiler-made | `std::__list_deleter<R,std::allocator<R>>` | `__list_deleter` | constructor: size 0, both links to the end node (+4) | zSeal-c.md; caller CSealCtrlAi::PreTick | medium |

## src/gamez/zSeal/seal_unit.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 388 | 0x2e5150 | member | `CSealUnit` | `PlayUnitResponse` | (this, sound): picks a member through the leader and tail lists (+0x40, +0x58, GetSealCtrlAi of each) and has it play the sound (CSealCtrlAi virtual +0x24) | zSeal-a.md proposed `CSealUnit::PlayUnitResponse(CHARACTER_SOUND)`; callers CSealUnit::IssueCommand, OrdersMenu::HandleRecoCmd, CSealCtrlAi::SetTarget | low |
| 389 | 0x2e6620 | free function |  | `SetupActionCommand` | (body, …, CNodeAction*, command): clears the command's flags, calls its virtual +8 with 4, stores the action; finds the AiMaps action by id (+0x2c), takes the cell centre + 9 up and 5 along the action direction (sign by the side the body is on) as the command's point (+0x24) | zSeal-a.md proposed it; caller CSealUnit::IssueCommand | low |
| 390 | 0x2e6880 | free function |  | `CanDeployAtAction` | (…, body, CNodeAction*, command): unless the AI is in state 10, command 0x14 is always allowed, 0x13 and 0x12 need CanDeploy of GRENADE / FLASHBANG; then the AiMaps action of the node must fit | zSeal-a.md proposed it; caller CSealCtrlAi::AllowCommand; xcheck-3.md: it replaced ItemHasAmmo / HasItem calls | low |
| 391 | 0x2e6b70 | free function |  | `CanUseAction` | (dist, body, CNodeAction*): false for fewer than 2 users, a busy action (+0x20) or a distance under 0.5; needs a ready controller; for an action of type 1 in state 0, true when the body faces its direction (GetClosestDir, CAiMap::GetDirDot row 20 > 0) | the body; callers CAiSAction::Tick, CSealCtrl::OnActionButton; xcheck-3.md: a new helper where ItemHasAmmo / HasItem were called; the name is a guess | low |

## src/gamez/zSystem/zsys_init.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 392 | 0x30be90 | free function |  | `zSysSetTimerRate` | zSys.timerTicksPerSecond = the float at zVid +0x54 as an integer, zSys.timerScale = 1 / that | small-1.md guessed `zSysSetFrameRate`; the globals it writes now show as zSys.timerTicksPerSecond / timerScale, hence Timer; caller zvid_SetVideoMode | low |
| 393 | 0x30c310 | free function |  | `zSysShutdown` | CIOPManager::RebootIOP(&theIOPManager, 5), then HeadsetAudioShutdown 0x30ad00 | small-1.md proposed it; callers Reboot (0x1416d0, row 17) and slot 2 of CShutdownState / CRebootState (0x432780, 0x43d480); between zSysLoadIRX and zSysPostInit | medium |

## src/gamez/zSystem/zsys_spr.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 394 | 0x30d120 | free function |  | `zSysFifoSetMenuMode` | stores its bool in the static 0x48e404 that zSysFifoKick reads | small-1.md proposed it; callers CMenuState::Init (true), CMenuState::UnInit (false); between zSysFifoKick and zSysFifoEnd | low |

## src/gamez/zTexture/ztex_manager.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 395 | 0x3112a0 | member | `zdb::CTexture` | `UpdateTextureSelects` | (this, a, tbp): sets the texture's TBP in its GS register word (+0x50), MIPUpdateTextureSelects for each mip (+0x64, count +0x60), the palette CBP (+0x1c); writes the word back (also uncached) when changed; returns tbp + the size (+0x2e) | small-2.md proposed it (the per-texture block of the prototype CGSTexBuffer::UpdateTextureSelects, its only caller) | medium |
| 396 | 0x3129b0 | member | `zdb::CGSTexBuffer` | `ReserveChain` | (this, n): clears the vector at +0x1c, then inserts up to n entries when it is smaller | small-2.md proposed it; caller LoadWorld (twice) | low |

## src/gamez/zTwoD/ztwod_font.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 397 | 0x316940 | compiler-made | `std::__vector_imp<C2DFontEntry,std::allocator<C2DFontEntry>,0>` | `reserve` | reserve(n): "vector::reserve length error", operator new(n * 40), C2DFontEntry copy constructor for each element, swap, clear and free of the old buffer | small-2.md: the MSL instance (its string and the element type of its copy constructor); caller C2DFont::Load | high |

## src/gamez/zUI/zui.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 398 | 0x39fe90 | free function |  | `LoadTtySound` | g_pTtySound (zui.cpp) = CSnd::GetSoundByName of the name at theGame +0x90's +0xc | zUI.md proposed it (the global PlayCountSound plays; not CGameMenu::AddNode, as the map had it); callers CMenuState::Init and the IOP reboot handler | medium |

## src/gamez/zUI/zui_spec.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 399 | 0x3b8bf0 | member | `CWrapSpec` | `CWrapSpec` | constructor from a reader: the CDlgObjSpec, CTextSpec and CWrapSpec tables, UIVAR, WIDTH, SPACING, HEIGHT and the new UP_ARROW / DOWN_ARROW (TEXTURE, SIZE, OFFSET) | zUI.md proposed `__ct__9CWrapSpecFP5_zrdr`: the tables it stores; caller GetControlSpec, which built it inline in the prototype | high |

## src/gamez/zUI/zui_tuner.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 400 | 0x3c08d0 | free function |  | `UpdateSystemTuners` | for each of the ten system-tuner globals (__pSoundTuner ... _pDialogTuner) that is set, calls its virtual +0xc (UpdateUIVar) with its variable (+4) | zUI.md: the globals InitSystemTuners writes and UninitSystemTuners clears; caller UIStoreOptions; the name is a guess in that family | medium |

## src/gamez/zVideo/zvid_init.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 401 | 0x31f630 | free function |  | `zVid_SetOffset` | (x, y, w, h): writes two GS register words of the static packet 0x44bc60 (uncached): an offset pair from (x, y) round 2048 in 12.4 and a second pair from (640 - w, 448 - h) | small-1.md proposed it; callers CCinematicState::Init and UnInit | low |
| 402 | 0x31f6c0 | free function |  | `zVid_SetScissorRect` | (a, b, c, d): packs the four values * 16 into the two packet words before (0x44bc50, 0x44bc70) | small-1.md proposed it; the same callers | low |

## src/gamez/zVisual/vis_bands.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 403 | 0x327df0 | member | `zdb::CVisData` | `SearchBatch` | steps the packets: a type 9 stores its matrix word (+0x18) at +0x54, a type 10 loads its batch counts (+8, +0xc) and data (+0x1c, +0x2c) and searches it (SearchBatchVertex 0x327d00, row 206); 0 at the end | zVisual.md; caller the decal builder's group opener 0x32b4c0; name in the family of rows 206-208 | low |
| 404 | 0x327eb0 | member | `zdb::CVisData` | `ResumeAfter` | (this, const CVisData& other): continues the walk just after the position the other walk saved (+0x58 packet, +0x5c index; packet count from +4) | zVisual.md; caller 0x32b4c0 | low |
| 405 | 0x327ee0 | member | `zdb::CVisData` | `NextMeshVertex` | (this, bool* crossed): steps one index like NextVertex; past the batch sets *crossed and searches on with SearchMeshVertex 0x3280c0 | zVisual.md (like NextVertex, with the new search); caller 0x325fb0; name in the family of SelectMeshVertex (row 208) | medium |
| 406 | 0x3280c0 | member | `zdb::CVisData` | `SearchMeshVertex` | outer search of the mesh walk: type 9 packets whose +0x18 equals the id at +0x54, then a type 10 batch of mode 2; saves the position at +0x58 / +0x5c and searches inside (0x327fc0, row 207); Clear and 0 at the end | zVisual.md: the counterpart of SearchVertex; callers NextMeshVertex 0x327ee0, SelectMeshVertex 0x328290 | medium |

## src/gamez/zVisual/vis_decal.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 407 | 0x32aad0 | member | `zdb::CMeshDecal` | `AddDecal` | (life, this, n, builder …): stores life (+0), the mesh (+8) and the texture-select qword (+0x20); counts the builder's groups and indices, mallocs the chain (vis_decal.cpp:809) and writes the VIF chain | zVisual.md (the CMeshDecal chain builder); caller AttachMeshDecal 0x325ea0, as CVisual::AttachDecal calls CDecal::AddDecal | medium |
| 408 | 0x32b4c0 | free function |  | `DecalBuilderAddGroup` | opens a group in the decal builder (global 0x48e544; count +0x2e4c, centre = CPnt3D::zero, tag -1), pushes the indices into the group's two vectors, then walks the batch (ResumeAfter, SearchBatch) | zVisual.md (a static helper, name unknown); caller 0x325fb0; the name is a guess | low |
| 409 | 0x32b7d0 | member | `zdb::CMeshDecalPool` | `Get` | (this, bool): when below the limit takes the next free decal (RTArray<CMeshDecal>::GetNext 0x32c600, row 209), counts it in use and the overflow | zVisual.md: masked bytes of CDecalPool::Get; caller passes the CMeshDecal pools; it sits between CMeshDecal::PutTempDecal and CMeshDecalPool::Init | high |
| 410 | 0x32b8c0 | free function |  | `DecalBuilderPushIndex` | appends one index to the builder's vector at +0 (vector_pod<unsigned int>::insert) | zVisual.md; caller 0x325fb0; the name is a guess | low |
| 411 | 0x32b910 | free function |  | `DestroyDecalBuilder` | clears the builder's counts, destroys its 296 groups (__destroy_arr, 40 bytes, 0x32b990) and its vector, deletes it, clears the global 0x48e544 | zVisual.md; caller 0x325fb0; the name is a guess | low |
| 412 | 0x32b990 | member | unknown (the 40-byte decal-builder group) | `~(group)` | destructor: size of the vector at +0x1c = 0, both vector_pod<unsigned int> (+0x1c, +0x10) destroyed, deletes when the flag > 0 | zVisual.md: passed to __destroy_arr / __construct_array by 0x32b910 and 0x32ba40; the type has no name | low |
| 413 | 0x32ba20 | free function |  | `ResetDecalBuilder` | group count (+0x2e4c) and vector size (+4) of the builder = 0 | zVisual.md; caller 0x325fb0; the name is a guess | low |
| 414 | 0x32ba40 | free function |  | `CreateDecalBuilder` | operator new(0x2e50), vector_pod constructor, __construct_array of 296 groups of 40 bytes (0x32bab0 / 0x32b990), reserve 296, group count 0; stores it in the global 0x48e544 | zVisual.md; caller zdb::CMesh::ApplyDecalRender 0x325fb0; the name is a guess | low |
| 415 | 0x32bab0 | member | unknown (the 40-byte decal-builder group) | `(group)` | constructor: two empty vector_pod<unsigned int> (+0x10, +0x1c), centre = CPnt3D::zero, shorts 0 and -1 at +0xc / +0xe | zVisual.md; passed to __construct_array by 0x32ba40; the type has no name | low |
| 416 | 0x32bf00 | member | `zdb::CDecalPool` | `RemoveAll` | while the in-use count (+0xc) is not 0: oldest used decal of CDecal::m_tempPool's array back (GetOldestUsed, PutBack, CVisual::RemoveDecal); then DereferenceDecals on every visual still holding one of this pool's array (+0x10) | zVisual.md proposed `RemoveAll__Q23zdb10CDecalPoolFv` (RecycleTick's loop to the end); caller zdb::CWorld::RemoveDecals on both CDecal pools. The first loop uses m_tempPool's array whatever `this` is: see the end of the sheet | medium |

## src/gamez/zVisual/vis_mesh.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 417 | 0x325ea0 | member | `zdb::CMesh` | `AttachMeshDecal` | (life, this, …): takes a CMeshDecal from CMeshDecal::m_permPool (life < 0) or m_tempPool (CMeshDecalPool::Get 0x32b7d0), links it at the end of the mesh's decal list (+0x6c), builds it (CMeshDecal::AddDecal 0x32aad0), FlushCache | zVisual.md: the mesh counterpart of CVisual::AttachDecal (which calls CDecal::AddDecal); next to CMesh::RemoveMeshDecal; caller 0x325fb0 (twice) | medium |
| 418 | 0x325fb0 | member | `zdb::CMesh` | `ApplyDecalRender` | walks the mesh's vertex data (CVisData mesh walk 0x328290 / 0x327ee0), tests each triangle against the decal (Sub, outer product, Normalize, UVCompare, fabsf), fills the decal builder (0x32ba40 ... 0x32b910) and attaches each batch (0x325ea0) | zVisual.md: the mesh counterpart of CVisual::ApplyDecalRender; caller 0x3264b0; the class of its first argument is not checked | low |
| 419 | 0x3264b0 | member | `zdb::CMesh` | `ApplyDecal` | builds the model and inverse matrices (sceVu0UnitMatrix, MulMatrix, CopyMatrix, Vu0MatrixInverseWithUniformScale) and calls 0x325fb0 | zVisual.md, zNode.md: caller zdb::CNode::ApplyDecal with the sub-mesh's mesh (+0x6c) and matrix id (+0x68), as CVisual::ApplyDecal for other visuals | low |

## src/gamez/zWeapon/zwep_explosive.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 420 | 0x32e400 | member | `PlacedExplosive` | `SetAttachNode` | (this, node, const CMatrix*): node at +0xbc, the matrix (identity when NULL) copied to +0xd0; PostTick rebuilds the instance matrix from them | zWeapon.md (a PlacedExplosive method read by PostTick); caller CZKit::HandleRemotePlaceExplosive; before PlacedExplosive::PreTick; the name is a guess | low |
| 421 | 0x32e430 | member | `PlacedExplosive` | `SetPlacedOnNode` | (this, node): stores the node at +0xc0, which PostTick walks up for ids 151 / 153 | zWeapon.md proposed `SetPlacedOnNode__15PlacedExplosiveFPQ23zdb5CNode`; the same caller, right after 0x32e400 | low |

## src/gamez/zWeapon/zwep_ftsweapon.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 422 | 0x32eac0 | member | `CTargetMods` | `SetKickEndScale` | (value, this): the float at +0x50 | zWeapon.md proposed it: ZWepReader::Read stores the "KES(%d)" value with it; the release CTargetMods constructor sets +0x50 = 1.0 | medium |
| 423 | 0x32ead0 | member | `CTargetMods` | `SetKickCount` | (this, value): the int at +0x4c | zWeapon.md: Read, after "KC(%d)"; the constructor sets 3 | medium |
| 424 | 0x32eae0 | member | `CTargetMods` | `GetKickEndScale` | returns the float at +0x50 | zWeapon.md; caller CZKit::Recoil | medium |
| 425 | 0x32eaf0 | member | `CTargetMods` | `GetKickCount` | returns the int at +0x4c | zWeapon.md; caller CZKit::Recoil | medium |
| 426 | 0x32eb20 | member | `CZFTSWeapon` | `IsGrenadeLauncherGrenade` | true for the weapon id (+0x60) 176 to 179 (GL_HE ... GL_FRAG in the prototype's enum) | zWeapon.md proposed it; caller CZKit::FindNextGrenadeLauncherAmmo; before CZFTSWeapon::IsGrenadeLauncherAmmo | medium |

## src/gamez/zWeapon/zwep_projectile.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 427 | 0x3304b0 | member | `CZProjectile` | `SetAnimFired` | (this, bool): bit 3 of +4 (DoMiss now tests it) | zWeapon.md proposed it; caller zAnimFireWeaponTick, after Fire | low |
| 428 | 0x3304d0 | member | `CZProjectile` | `SetLaunch` | (this, const CPnt3D* pos, const CPnt3D* vel): position (+0x4c) and frame start (+0x40), the node's position; with no velocity mode 2 and a zero velocity, else mode 1 and the velocity (+0x58); clears bit 0 of +4, +0xa0 = -1 | zSeal-e.md: what the "Return throw grenade" callbacks 0x264250 and 0x2644e0 hand the velocity to; the name is a guess | low |
| 429 | 0x3305c0 | member | `CZProjectile` | `SetPos` | (this, const CPnt3D*): position and frame start, and the node's position | zWeapon.md (sets the position only); caller the throw callback 0x2643a0; the name is a guess | low |
| 430 | 0x330620 | member | `CZProjectile` | `SetPosStill` | (this, const CPnt3D*): the same and a zero velocity | zWeapon.md; caller the throw callback 0x264440; the name is a guess | low |

## src/gamez/zWeapon/zwep_projectilelist.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 431 | 0x334440 | member | `CZProjectileList` | `GetNumActiveExplosives` | (this, owner): counts the owner's (+0xa4) placed (list +0xc) and active (array +0, flags +0x10) projectiles whose weapon type is 120, 150 or 170; -1 without an array | zWeapon.md proposed it (next to GetNumRemoteExplosives(int)); caller CZKit::WillFireWeapon | medium |
| 432 | 0x334620 | member | `CZProjectileList` | `Dump` | walks the placed list and the active array calling only CZWeapon::GetName (the output is compiled out) | zWeapon.md proposed it; caller CMission::Close | low |
| 433 | 0x334730 | member | `CZProjectileList` | `RemoveSatchels` | (radius, this, const CPnt3D*): every placed explosive whose weapon is SATCHEL_CHARGE within the radius of the point: state 3, ReportGrenadeStatus, CPickup::Destroy, destroyed and erased (as RemoveExplosive does) | zWeapon.md; reached only from the REMOVE_SATCHELS tick (0x1b8b50 through 0x3373a0); the name follows the command | medium |
| 434 | 0x336e70 | member | `CZAmmoPickupInstance` | `GetOwner` | returns the word at +0x24 | zWeapon.md proposed it (the meaning of +0x24 is unknown); caller CPickup::Destroy | low |
| 435 | 0x336e80 | member | `CZAmmoPickupInstance` | `SetOwner` | stores the word at +0x24 | zWeapon.md; caller CZSealBody::DropAmmo | low |
| 436 | 0x336f40 | member | `CZAmmoPickupInstance` | `ClearEntry` | (this, i): when i is below the number of used entries, zeroes entry i of the three parallel vectors (+0x8, +0x14, +0x20) | zWeapon.md; caller CZSealBody::HandlePickupAck | low |
| 437 | 0x337020 | member | `CZAmmoPickupInstance` | `GetNumEntries` | counts the entries with a non-zero count (vector +0x20, size +0x1c) | zWeapon.md; seven callers (CPickup::CleanupAmmoPickup, CZKit::PickupAmmo, CZSealBody ammo functions) | medium |
| 438 | 0x337060 | member | `CZAmmoPickupInstance` | `GetEntry` | (this, i, out item, out ammo, out count): copies entry i out of the three vectors; returns whether it exists | zWeapon.md; the same seven callers | medium |
| 439 | 0x337180 | member | `CZAmmoPickupInstance` | `SetEntry` | (this, i, item, ammo, count): writes entry i | zWeapon.md; caller CZKit::PickupAmmo | medium |

## src/gamez/zWeapon/zwep_weapon.cpp

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 440 | 0x3373a0 | static member | `CZWeapon` | `RemoveSatchels` | `j 0x334730` with CZWeapon::m_pProjectilelist: CZProjectileList::RemoveSatchels on the weapons module's list | zWeapon.md (a CZWeapon static wrapper); caller zAnimRemoveSatchelsTick (0x1b8b50); before CZWeapon::TimerCleared | medium |

## (no owner file)

| # | address | kind | class or library | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 441 | 0x1439f0 | library | Metrowerks runtime | `__ptmf_cmpr` | (a, b): returns whether any of the three words of two pointer-to-member records differ (*a != *b, or a[1] != b[1], or a[2] != b[2]) | library identification: the runtime's pointer-to-member compare, the three-word ptmf record of `__ptmf_scall` just before it; caller SetFinalTeamTotalsUiVar | high |
| 442 | 0x15d124 | library | SCE libkernel | `fn_0015d124` | no function in the program (stage3-starts.md withheld the start): one `jr ra` whose delay slot is the first instruction of sceSifInitRpc 0x15d128, an empty void function | stage3-starts.md; the bytes (03e00008 at 0x15d124); nothing names it | low |
| 443 | 0x16f008 | library | SCE libcdvd | `sceCdStInit` | clears the stream-open flag DAT_00446e70 and calls 0x16f380 with its own (bufmax, bankmax, buffer) and command 5, mode 0x494d18 | library identification: command 5 is the CD stream init command and the family's strings name sceCdStRead / Pause / Resume / Stat; caller strFileOpen; zMPEG.md called it the stream client init | high |
| 444 | 0x16f038 | library | SCE libcdvd | `sceCdStStart` | sets the open flag, 0x16f380(lsn, 0, 0, 1, mode): command 1, stream start | library identification (command 1); caller strFileOpen; zMPEG.md "open" | high |
| 445 | 0x16f070 | library | SCE libcdvd | `sceCdStSeekF` | 0x16f380(lsn, 0, 0, 9, 0x494d18): command 9 | library identification (command 9, the fast seek); no caller | medium |
| 446 | 0x16f0a0 | library | SCE libcdvd | `sceCdStSeek` | 0x16f380(lsn, 0, 0, 4, 0x494d18): command 4 | library identification (command 4); caller strFileRewind; zMPEG.md "seek" | high |
| 447 | 0x16f0d0 | library | SCE libcdvd | `sceCdStStop` | clears the open flag, 0x16f380(0, 0, 0, 3, 0x494d18): command 3 | library identification (command 3); caller strFileClose; zMPEG.md "close" | high |
| 448 | 0x16f108 | library | SCE libcdvd | `sceCdStRead` | (sectors, buf, mode, err*): prints "sceCdStRead call read size= %d mode= %d"; with the stream open writes back the D-cache and reads by command 2 once (mode 0) or in a loop until all sectors arrive; the error goes to *err | its own debug string; command 2; caller strFileRead | high |
| 449 | 0x16f290 | library | SCE libcdvd | `sceCdStPause` | clears the open flag, prints "sceCdStPause call", command 7 | its own debug string | high |
| 450 | 0x16f2e0 | library | SCE libcdvd | `sceCdStResume` | sets the open flag, prints "sceCdStResume call", command 8 | its own debug string | high |
| 451 | 0x16f338 | library | SCE libcdvd | `sceCdStStat` | prints "sceCdStStat call", command 6, returns its result | its own debug string | high |
| 452 | 0x16f380 | library | SCE libcdvd | `sceCdStream` | (lsn, sectors, buf, cmd, mode): `_sceCd_ncmd_prechk(0xf)`, copies the arguments and the 3-byte mode into _sceCd_ncmdsdata, writes it back, sends N-command 0xf ("call cdreadstm cmd"), returns the reply | library identification: the common worker of the nine St calls; `sceCdStream` is the open-source SDK's name for it, the original's debug text says "cdreadstm" | medium |
| 453 | 0x1a57d0 | member | `CAiMap` | `FindOpenCells` | (this, CAiMapLoc*, CAiMapLoc out[8], int steps[8], int max): when the start cell's soil is open (not 0, 8, 9 or 10) all eight steps are 0 and the locations the start; else for each of the eight directions (neighbor__6CAiMap offsets) steps through blocked cells up to max, keeping the step count and the first open location; returns 1 | the body alone; caller CAiSPathRecover::Tick (recovers a path from a blocked cell); unplaced between zVehicle and ai_mapwalk.cpp, next CAiMap::CountMapTravelDir; the name is a guess | low |
| 454 | 0x251770 | member | `CZSealBody` | `DeleteHostageAnchor` | CCompass::DeleteAnchor(this->+0xde0), then +0xde0 = 0 | zSeal-f.md, xcheck-1.md: with CreateHostageAnchor (0x2517a0, row 223) it replaced the removed CompassAnchor_Hostage; callers CAiSRescued::OnSignal, CRemoteCtrl::SetAiNetState, CSealCtrlAi::OnDeath; unplaced, next to CZSealBody::TickHeartbeat | high |
| 455 | 0x297cc0 | member | `CZSealBody` | `IsOnLadder` | (this, CLadderData*): true when the ladder is given, the body's ladder index (+0xf8a) is not the "none" value and CLadderList::GetLadderByIndex (theMission +0x590) of it is that ladder | zSeal-d.md proposed it; caller CSealCtrlAi::LadderClimbTick; unplaced between seal_dyn.cpp and seal_env.cpp | medium |
| 456 | 0x2b3a00 | member | `CZKit` | `SetSlot` | (this, index, value): stores value in entry index + 1 of the table at +0x82c (unchecked) | zSeal-b.md, zSeal-e.md (CZKit slot accessors); callers CZSealBody::PickupItem, RemotePickupItem; unplaced, before CZKit::ResetScreenOffsetXY | low |
| 457 | 0x2b3a20 | member | `CZKit` | `ClearSlot` | (this, index): entry index + 1 of the table at +0x82c = 0 when below the count +0x828 | as 0x2b3a00; callers DropItem, PickupItem, RemotePickupItem | low |
| 458 | 0x2b3a50 | member | `CZKit` | `GetSlot` | (this, index): entry index + 1 of the table, 0 when out of range | as 0x2b3a00; callers DropItem, RemotePickupItem | low |
| 459 | 0x2b3a80 | member | `CZKit` | `ClearSniperKick` | zeroes the two words +0x18 and +0x1c | zSeal-b.md (a zoom-offset reset), xcheck-3.md: DecrZoomState calls it where it called InitializeSniperKick; the class rests on the position before CZKit::ResetScreenOffsetXY; the name is a guess | low |
| 460 | 0x2e0c10 | member | `CSealUnit` | `IsTargetSeenByOther` | (this, CEntity* self, CEntity* target): for each member (list +0x40) other than self, whose AI controller (virtual +0x38) targets the entity (+0x574) with a valid target (CAiTarget::IsTargetValid, row 77) flagged at +0x598, returns 1; else 0 | the body; the member list +0x40 is CSealUnit's (rows 228, 229); callers CSealCtrl::SensorTick, CSealCtrlAi::OnSetTargetVisible; unplaced before seal_unit.cpp; the name is a guess | low |
| 461 | 0x301ad0 | library | 989snd | `snd_ContinueAllSoundsInGroup` | (groups): IOP command 0x17 with the 4-byte group mask, no wait | library identification: next to snd_ContinueSound / snd_PauseSound; CSndInstance::ResumeAllSounds calls it with -1 (all groups) where the prototype walked its instance list | medium |
| 462 | 0x301b00 | library | 989snd | `snd_PauseAllSoundsInGroup` | (groups): IOP command 0x16 with the group mask | library identification, as 0x301ad0; caller CSndInstance::PauseAllSounds | medium |
| 463 | 0x302220 | library | 989snd | `snd_StopSoundSystem` | flushes the queued sound commands (FlushCache loops), sends IOP command 1 and waits, clears gStreamingInited, waits until both RPC clients (gSLClientLoaderData, gSLClientData) are idle | library identification: the counterpart of snd_StartSoundSystem; caller the IOP reboot handler; between snd_BankLoad and snd_FlushSoundCommands | medium |
| 464 | 0x302820 | free function |  | `fn_00302820` | when the static flag 0x48e37c is set: clears it and, when the float 0x48e374 is 1e9, sets it to 0.01 | the body; caller CSndInstance::ReleaseSoundInstance; unplaced between 989snd and zsnd_csnd.cpp; nothing names the statics | low |
| 465 | 0x30ad00 | free function |  | `HeadsetAudioShutdown` | when the static flag 0x48e3d0 is set calls lgAud 0x3d6350 (row below, the library's shut-down); clears the flag | small-1.md (the headset-audio shutdown); callers CIOPManager::RebootIOP, zSysShutdown 0x30c310, 0x404800; unplaced after Headset::ftsGetHeadset; the name is a guess | low |
| 466 | 0x30ad30 | free function |  | `HeadsetAudioInit` | sets the flag 0x48e3d0, tail-calls lgAudInit | small-1.md; caller CIOPManager::RebootIOP (after the reboot); the pair of 0x30ad00 | low |
| 467 | 0x31eb20 | static member | `CVideo` | `ApplyBrightness` | when CVideo::m_brightness is not 0x80, sends a one-quadword scratchpad packet (tag 0x30000008, data 0x44bb00, 0x13000000 / 0x50000008) with zSysFifoKick | the body: it reads only CVideo::m_brightness; caller zSysFifoEnd; unplaced just before CVideo::Brightness; the name is a guess | low |
| 468 | 0x34fe20 | member | `CZNetVoice` | `CZNetVoice` | constructor: +0 = 1, the bytes +0xc..+0x1a cleared, +0xf = 1 | zMPEG.md: reached only from the stub `__sinit_zNetVoice.cpp` (0x4863a0), which passes the global the program names theVoice (0x545240); right after CZNetVoice::Init | high |
| 469 | 0x3bd630 | member | `CUIVariable` | `CUIVariable` | copy constructor (this, const CUIVariable&): clears two flag bits, an empty vector_pod reserved to 16, the name copied into the current string table (CSTable::CreateString), byte +0x18 copied | zFTS.md: the out-of-line CUIVariable copy constructor that insert<CUIVariable> now calls; unplaced after CUIVariable::Destroy | high |
| 470 | 0x3d0430 | library | Medius | `fn_003d0430` | returns 0x2c: the size of the request | the Request/ResponseHandler pattern of its neighbours (8-byte request handler, 48-byte response handler); it serves the request sent by 0x3d4ea0 (message 0x40, 0x2c bytes, callback slot 0x44c314), which is not identified | low |
| 471 | 0x3d0438 | library | Medius | `fn_003d0438` | calls the callback stored at 0x44c314 when set, returns 0x44 | as 0x3d0430: the response handler of the same request | low |
| 472 | 0x3d2068 | library | Medius | `MediusGetVersion` | strncpy(buf, "Medius Client Library Version 1.40.PRE8", 0x28), returns 0 | its string; between MediusGetBuildTimeStamp and MediusVersionServer; caller AuxInitNetwork; the exact SDK name is not known | low |
| 473 | 0x3d41ac | library | Medius | `MediusCreateMessageID` | (sessionKey, callback, out id): terminates the 17- and 21-byte strings, iCreateAndAllocateMessageID with the counter 0x44c324, which wraps after 999 | library identification: the prototype's MediusCreateMessageID (0x3b4cb0) has the same body with a wrap at 0x200; the map paired that name with 0x3d4ea0 instead (see the end of the sheet) | done: carried as `MediusCreateMessageID` |
| 474 | 0x3d6350 | library | lgAud | `lgAudPrepareForReboot` | WaitSema, RPC call 0x14 to the lgAud server (cdUA, devRpcData), updates devicechanged, SignalSema; on failure prints "lgAudPrepareForReboot: rpc call f…" and returns 0x80000000 | its own debug string; caller HeadsetAudioShutdown 0x30ad00 | high |
| 475 | 0x407718 | library | Medius (rt_comm_platform2) | `fn_00407718` | lists the inet interfaces (gSifMClientData, gNetBuf) and, with an rt_time timer, polls interface control 8 until an interface's flags have both low bits set; 1 on a control error | its neighbours rt_comm_platform2_display_state / _get_local_ip_from_stack; caller rt_comm_platform2_startup; the library's name for it is not known | low |
| 476 | 0x409f20 | library | RSA (lint) | `fn_00409f20` | (lint, bits): keeps the low `bits` bits of a 32-word big integer (masks the top word, zeroes the words above) | between lintPrime and lintGetBits; caller 0x409f70; not identified | low |
| 477 | 0x409f70 | library | RSA (lint) | `fn_00409f70` | (out, base, mod, exp): a modular exponentiation over 32-word integers (lintGetBits of the exponent and modulus, lintGetBit loop, the compare, shift, add and subtract helpers below) | callers LucasTest, RSADecryptBlock, lintIsbSPRP; not identified | low |
| 478 | 0x40a618 | library | RSA (lint) | `fn_0040a618` | (a, b): 1 when a > b, comparing the 32 words from the top | between lintGetBits and lintAddIP; callers 0x40bd9c, RSAGenerateKeyPair; not identified | low |
| 479 | 0x40a68c | library | RSA (lint) | `fn_0040a68c` | (a, b): 1 when a < b | as 0x40a618 | low |
| 480 | 0x40a700 | library | RSA (lint) | `fn_0040a700` | (a, b): 1 when a <= b | as 0x40a618; no caller | low |
| 481 | 0x40a780 | library | RSA (lint) | `fn_0040a780` | (a, b): 1 when a >= b | as 0x40a618; callers 0x409f70, QRMOD, QUO | low |
| 482 | 0x40a800 | library | RSA (lint) | `fn_0040a800` | (lint, bits): shifts a 32-word integer right by `bits` in place | callers 0x409f70, LucasTest, QRMOD, QUO, lintIsbSPRP; not identified | low |
| 483 | 0x40a940 | library | RSA (lint) | `fn_0040a940` | (lint, bits): shifts it left by `bits` in place | callers 0x409f70, QRMOD, QUO; not identified | low |
| 484 | 0x40ab28 | library | RSA (lint) | `fn_0040ab28` | (a, b, bits): a += b over the words needed for `bits`, with carry | after lintAddIP; caller 0x409f70; not identified | low |
| 485 | 0x40ac54 | library | RSA (lint) | `fn_0040ac54` | (a, b, bits): a -= b over the same words, with borrow | after lintSubIP; caller 0x409f70; not identified | low |
| 486 | 0x40b124 | library | RSA (lint) | `fn_0040b124` | (out, a, b): multiplies two big integers word by word into a double-length temporary (lintGetBits of both) and stores the result | between MODIP and XMOD; callers 0x409f70, 0x40bd9c, RSAGenerateKeyPair; not identified | low |
| 487 | 0x40b4c8 | library | RSA (lint) | `fn_0040b4c8` | (out): copies a 128-byte constant (0x44c908) and, once (flag 0x454988), initialises a static; builds a random or fixed starting integer | between XMOD and RCInitialize; caller 0x40bd9c; not identified | low |
| 488 | 0x40bd9c | library | RSA (lint) | `fn_0040bd9c` | (pub, priv): key-pair generation: candidate from 0x40b4c8, compares, multiplies and tests in a loop | between RSAGenerateKeyPair and RSADecryptBlock; caller 0x40e71c; a second key-pair generator, not identified | low |
| 489 | 0x40c1dc | library | RSA | `fn_0040c1dc` | (a, b, c): RSADecryptBlock(a, the built-in key 0x454990, b, c) | no caller; not identified | low |
| 490 | 0x40e71c | library | Medius (KM) | `fn_0040e71c` | (pub, priv): InitializePRNG, then the key-pair generator 0x40bd9c | between KM_GenerateRSAKeyPair and KM_CreateRandomRCKey; no caller; not identified | low |
| 491 | 0x40ebf0 | library | Medius (KM) | `fn_0040ebf0` | caches in 0x454a3c whether KM_GetLocalPublicKey(0, 0) succeeds (1) or not (2), returns it | between KM_Decrypt and rt_msg_client_get_version_string_ptr; callers rt_msg_client_process_message, rt_msg_client_tcp_aggregate_msg; not identified | low |
| 492 | 0x40fa90 | library | Medius (rt_msg_client) | `fn_0040fa90` | returns 3 | one of three identical stubs between rt_msg_client_udp_clear_target and rt_msg_client_ishutdown; no caller | low |
| 493 | 0x40fa98 | library | Medius (rt_msg_client) | `fn_0040fa98` | returns 3 | as 0x40fa90 | low |
| 494 | 0x40faa0 | library | Medius (rt_msg_client) | `fn_0040faa0` | returns 3 | as 0x40fa90 | low |
| 495 | 0x411240 | library | Medius (rt_msg_client) | `fn_00411240` | (connection): writes KM_GetSoftwareID into the connect message, signs it (KM_Encrypt, else KM_GetSoftwareKeyPair and KM_DigiSign; zeroes the signature when encryption is off) and queues it with rt_msg_client_store_msg_in_send_buf | between rt_msg_client_store_connect_msg_in_send_buf (a caller) and rt_msg_client_send_disconnect; caller also rt_msg_client_update_connection; not identified | low |
| 496 | 0x416f30 | library | Medius (DME) | `fn_00416f30` | calls 0x416f70 for the indices 0 to 3 until one fails | between NetClientLeaves and DmeToRtMsgConnectionIndex; no caller; not identified | low |
| 497 | 0x416f70 | library | Medius (DME) | `fn_00416f70` | (i): for i < 4 clears the 256 entries of row i (0x416fc8); 0x17 for a bad index | callers 0x416f30, NetJoin; not identified | low |
| 498 | 0x416fc8 | library | Medius (DME) | `fn_00416fc8` | (i, j): clears entry [i][j] of the 4 x 256 word table 0x586c28; 0x17 when out of range | callers 0x416f70, NetClientLeaves; not identified | low |
| 499 | 0x417000 | library | Medius (DME) | `fn_00417000` | (i, j, value): stores value in entry [i][j] of the 4 x 256 table 0x586c28; 0x17 when out of range | the setter of the table of 0x416fc8; callers NetJoin, RequestClientJoinPacketHandler, 0x41d5b8; not identified | low |
| 500 | 0x417038 | library | Medius (DME) | `fn_00417038` | (i, j, out): reads entry [i][j] into *out; 0x17 when out of range or out is NULL | the getter of the same table; callers 0x417080, 0x4171c8, 0x417280; not identified | low |
| 501 | 0x417080 | library | Medius (DME) | `fn_00417080` | (i, out a, out b, out c, out d): clears the four outputs, then walks row i (0x417038) and gathers counts and values of the set entries | callers NetClientLeaves, RequestClientJoinPacketHandler; not identified | low |
| 502 | 0x4171c8 | library | Medius (DME) | `fn_004171c8` | (i, client): for each set entry j of row i sends DME message 0x50 (8 bytes: j and the value) to the client | caller RequestClientJoinPacketHandler; not identified | low |
| 503 | 0x417280 | library | Medius (DME) | `fn_00417280` | (i, j): sends entry [i][j] as DME message 0x50 to every other present client (NetGetClient, skipping j and this console's MyClientIndexList entry) | caller RequestClientJoinPacketHandler; not identified | low |
| 504 | 0x41d5b8 | library | Medius (DME) | `fn_0041d5b8` | DME packet handler (i, …, j, packet): stores the packet's value in entry [i][packet[0]] (0x417000); returns 8 | between ReceiveEnablePacketHandler and ClientConnectsPacketHandler; the receiver of message 0x50; the library's name is not known | low |
| 505 | 0x423fa0 | library | newlib | `__sfmoreglue` | (reent, n): _malloc_r(n * 0x58 + 0xc); glue next 0, count n, the FILE array after it cleared | library identification: findfp.c, between std and __sfp (sizeof(FILE) 0x58); caller __sfp 0x424018 | done: carried as `__sfmoreglue` |
| 506 | 0x424018 | library | newlib | `__sfp` | (reent): runs __sinit when not done, walks the glue lists for a FILE with no flags, initialises it (file -1, the reent, buffers cleared), adds more glue (__sfmoreglue) when all are used | library identification: findfp.c's __sfp, before _cleanup_r | done: carried as `__sfp` |
| 507 | 0x424130 | library | newlib | `_cleanup` | _cleanup_r(_impure_ptr) | library identification: findfp.c, between _cleanup_r and __sinit | done: carried as `_cleanup` |
| 508 | 0x425300 | library | newlib | `_setlocale_r` | (reent, category, locale): a locale other than "C" or "" gives NULL; else stores locale and category in the reent (+0x34, +0x30) and returns "C" | library identification: locale.c, before _localeconv_r | done: carried as `_setlocale_r` |
| 509 | 0x4253a0 | library | newlib | `setlocale` | _setlocale_r(_impure_ptr, category, locale) | library identification: locale.c, between _localeconv_r and localeconv | done: carried as `setlocale` |
| 510 | 0x426618 | library | newlib (SCE) | `__malloc_lock` | takes the allocator semaphore (__sce_sema_id) unless this thread holds it (GetThreadId), counts the depth | library identification: the lock every malloc-family function calls first (_malloc_r, _free_r, _realloc_r, _memalign_r, calloc ...) | done: carried as `__malloc_lock` |
| 511 | 0x426698 | library | newlib (SCE) | `__malloc_unlock` | decrements the depth; at 0 clears the owner and signals the semaphore | library identification: the matching unlock | done: carried as `__malloc_unlock` |
| 512 | 0x427690 | library | newlib | `_mprec_log10` | (n): 10^n: __mprec_tens[n] for n < 24, else a loop of * 10 | library identification: mprec.c's _mprec_log10 (the __mprec_tens table); no caller | done: carried as `_mprec_log10` |
| 513 | 0x427700 | library | newlib | `_printf_r` | (reent, fmt, ...): _vfprintf_r(reent, reent's stdout (+8), fmt, args) | library identification: printf.c's reentrant printf, just before printf | done: carried as `_printf_r` |
| 514 | 0x428b38 | library | newlib (MIPS) | `setjmp` | stores s0-s7, fp, sp, ra (128-bit registers) into the buffer, returns 0 | library identification: the register save; caller tickPss, the target of errorCallback's longjmp (zMPEG.md) | high |
| 515 | 0x428b90 | library | newlib (MIPS) | `longjmp` | (buf, value): restores the registers and returns value, or 1 for 0 | library identification; zMPEG.md: errorCallback now longjmps (jmpbuf, 1) back into tickPss | high |
| 516 | 0x428c68 | library | newlib | `_signal_r` | (reent, sig, func): for sig < 32 sets up the table (_init_signal_r) when missing, stores func and returns the old one; else errno EINVAL (0x16) and -1 | library identification: signal.c, between _init_signal_r and _raise_r | done: carried as `_signal_r` |
| 517 | 0x428dc0 | library | newlib | `__sigtramp_r` | (reent, sig): 1 for no handler, 2 for SIG_IGN, 3 for SIG_ERR, else resets it and calls it, 0 | library identification: signal.c, between _raise_r and raise | done: carried as `__sigtramp_r` |
| 518 | 0x428e78 | library | newlib | `signal` | _signal_r(_impure_ptr, sig, func) | library identification: after raise | done: carried as `signal` |
| 519 | 0x428ea0 | library | newlib | `_init_signal` | _init_signal_r(_impure_ptr) | library identification: signal.c | done: carried as `_init_signal` |
| 520 | 0x428ec0 | library | newlib | `__sigtramp` | __sigtramp_r(_impure_ptr, sig) | library identification: signal.c, before _kill_r | done: carried as `__sigtramp` |
| 521 | 0x428f58 | library | newlib | `_sprintf_r` | (reent, str, fmt, ...): a string FILE (flags 0x208, size INT_MAX) and vfprintf, then the terminating 0 | library identification: sprintf.c, just before sprintf | done: carried as `_sprintf_r` |
| 522 | 0x42aeb8 | library | newlib | `strtof` | (s, end): (float) strtod(s, end) | library identification: strtod.c, right after strtod | done: carried as `strtodf` |
| 523 | 0x42ed20 | library | newlib | `_vsprintf_r` | (reent, str, fmt, va_list): the same string FILE and vfprintf, then 0 | library identification: vsprintf.c, after vsprintf | high |
| 524 | 0x42eff8 | library | SCE libinet | `fn_0042eff8` | (rpc, cmd, buf, in size, out size): rounds both sizes to 16 and checks them against the client's buffer size (+0x30) ("…" printed, -0x21f on overflow); else sceSifMCallRpc(rpc, cmd, 0, buf, in, buf, out) | the RPC helper every sceInet* function calls (26 callers); unplaced between newlib and sceInetName2Address; the library's own name is not known | low |
| 525 | 0x42f078 | library | SCE libinet | `fn_0042f078` | (rpc, buf, word index, src, size): copies size bytes into the RPC buffer at that word when they fit; -0x21f otherwise | helper of sceInetAddress2Name / 2String, sceInetControl, sceInetCreate, sceInetInterfaceControl and the SendTo below; not identified | low |
| 526 | 0x42f0d0 | library | SCE libinet | `fn_0042f0d0` | (rpc, dst, buf, word index, size): copies size bytes out of the RPC buffer | the reverse of 0x42f078; 9 callers; not identified | low |
| 527 | 0x42f128 | library | SCE libinet | `fn_0042f128` | (rpc, buf, word index, string): strcpy into the RPC buffer when it fits, returns the length + 1, else -0x21f | caller sceInetName2Address; not identified | low |
| 528 | 0x42f1b8 | library | SCE libinet | `fn_0042f1b8` | (rpc, dst, buf, word index): strcpy out of the RPC buffer | callers sceInetAddress2Name, sceInetAddress2String; not identified | low |
| 529 | 0x42f4b0 | library | SCE libinet | `sceInetClose` | (rpc, buf, cid, ms): RPC command 3 with two words in, the result out | library identification: the command after sceInetOpen (2), between Open and the Recv below; the SDK's sceInetClose(cid, ms) | medium |
| 530 | 0x42f4f8 | library | SCE libinet | `sceInetRecv` | (rpc, buf, cid, ptr, count, int* flags, ms): command 4; copies the data and the flags back | library identification: the argument shape of sceInetRecv(cid, ptr, count, pflags, ms) | medium |
| 531 | 0x42f5c0 | library | SCE libinet | `sceInetRecvFrom` | (…, cid, ptr, count, int* flags, addr*, int* port, ms): command 0xd; the data, a 16-byte address and the port back | library identification: the argument shape of sceInetRecvFrom; before sceInetSend | medium |
| 532 | 0x42f778 | library | SCE libinet | `sceInetSendTo` | (…, cid, ptr, count, int* flags, addr*, port, ms): copies the 16-byte address and the data in (0x42f078), command 0xe | library identification: the argument shape; after sceInetSend | medium |
| 533 | 0x42f860 | library | SCE libinet | `sceInetAbort` | (rpc, buf, cid, flags): command 0xf, two words in | library identification: the call after SendTo and before sceInetControl in the SDK's list, two int arguments; less sure than the four above | low |
| 534 | 0x42fa98 | library | SCE libinet | `sceInetGetRoutingTable` | (rpc, buf, out, n): command 10, copies n 0x48-byte entries back, returns the count | after sceInetInterfaceControl (9); the argument shape fits; the entry size is not checked against the SDK | low |
| 535 | 0x42fb38 | library | SCE libinet | `sceInetGetNameServers` | (rpc, buf, out, n): command 0xb, copies n 16-byte addresses back | as 0x42fa98 | low |
| 536 | 0x42fbc8 | library | SCE libinet | `fn_0042fbc8` | (rpc, buf, x): command 0xc with one word, returns the result | one-int call after the name-server one; not identified | low |
| 537 | 0x42fc10 | library | SCE libinet | `sceInetGetLog` | (rpc, buf, out, len, flags): command 0x11, copies len bytes back | the argument shape of sceInetGetLog(log, len, flags); low | low |
| 538 | 0x42fca8 | library | SCE libinet | `fn_0042fca8` | (rpc, buf): command 0x10, no input, returns the result | not identified | low |
| 539 | 0x42fce8 | library | SCE libinet | `fn_0042fce8` | (rpc, buf, x): command 0x32 with one word | not identified | low |
| 540 | 0x42fd30 | library | SCE libinet | `fn_0042fd30` | (rpc, buf, x): command 0x33 with one word | not identified | low |
| 541 | 0x42fd78 | library | SCE libinet | `fn_0042fd78` | (rpc, buf, x): command 0x34 with one word | not identified | low |
| 542 | 0x42ff40 | library | SCE libinet | `fn_0042ff40` | (rpc, buf): command 0x1f, no input | right after reg_handler (command 0x1e), so perhaps its unregister counterpart; caller rt_comm_platform2_shutdown; not identified | low |
| 543 | 0x42ff80 | library | SCE libinet | `fn_0042ff80` | (rpc, buf, x): command 0x20 with one word | after reg_handler; not identified | low |
| 544 | 0x42ffc8 | library | SCE libinet | `fn_0042ffc8` | (rpc, buf, out, n, cmd): the given command, copies n words of the reply to out, returns the first | helper of the two below; not identified | low |
| 545 | 0x430050 | library | SCE libinet | `fn_00430050` | a tail call of 0x42ffc8 with the caller's arguments | caller wait_get_addr; not identified | low |
| 546 | 0x430068 | library | SCE libinet | `fn_00430068` | the same | callers get_interface_id, wait_get_addr_only; not identified | low |
| 547 | 0x430300 | library | SCE libinet | `fn_00430300` | by bit 1 of its fifth argument (t1) calls get_interface_id or wait_get_addr_only | after wait_get_addr; caller rt_comm_platform2_get_local_ip_from_stack; not identified | low |
| 548 | 0x430918 | library | SCE libnetb | `fn_00430918` | (cid, …): with a cid, receives through 0x431088 and returns the count, or -0x1f5 | between sceBInetRecvFrom and sceBInetSend; no caller; not identified | low |
| 549 | 0x430b50 | library | SCE libnetb | `fn_00430b50` | the send counterpart through 0x431328 | between sceBInetSendTo and sceBInetControl; no caller; not identified | low |
| 550 | 0x431088 | library | SCE libnetb | `fn_00431088` | libnetb_recv_from with two fixed values; sets *ok when it returned 2 | between libnetb_recv_from and libnetb_send_to; caller 0x430918; not identified | low |
| 551 | 0x431328 | library | SCE libnetb | `fn_00431328` | libnetb_send_to of a two-byte value; sets *ok when it sent 2 | between libnetb_send_to and libnetb_alloc_bufs; caller 0x430b50; not identified | low |
| 552 | 0x431b88 | library | SCE ezNetCnf | `ezNetCnfGetCount` | (path, type): "eznetcnf RPC server not cur…" when unbound, else RPC 0 with the path; prints "ezNetCnfGetCount returned %d" and returns it | zNetwork-c.md: named by its own message; caller UINetCnfCount | high |
| 553 | 0x431c48 | library | SCE ezNetCnf | `ezNetCnfGetCombinationList` | the same RPC 1; "ezNetCnfGetCombinationList returned…" | zNetwork-c.md: its own message; caller UINetCnfOpen | high |
| 554 | 0x431d08 | library | SCE ezNetCnf | `ezNetCnfGetCombination` | (list, n): entry n (1-based) of the list, or NULL with "ezNetCnfGetCombination: invalid …" / "… pList is …" | zNetwork-c.md: its own messages; no caller | high |
| 555 | 0x431d88 | library | SCE ezNetCnf | `ezNetCnfGetDefault` | (list): the default entry (+4) of the list, or NULL with its messages | zNetwork-c.md: its own messages; caller UINetCnfCurrCombo | high |
| 556 | 0x431e08 | library | SCE ezNetCnf | `ezNetCnfSetDefault` | (path, name): RPC 3; "ezNetCnfSetDefault returned %d" | zNetwork-c.md: its own message; caller UINetSaveCombo | high |
| 557 | 0x431ed0 | library | SCE ezNetCnf | `ezNetCnfGetNetcnfifData` | (path, name, type): RPC 2; "ezNetCnfGetNetcnfifData returned…" | zNetwork-c.md: its own message; caller UINetCnfSelectCombo | high |
| 558 | 0x432810 | member | `CShutdownState` | `CShutdownState` | constructor: CGameState's table and name reset, strdup "ShutdownState" (zgame.h:0x54) at +4, the CShutdownState table (0x48c5d0) | state.md proposed `__ct__14CShutdownStateFv`; small-1.md: called by __sinit_main.cpp at COurGame +548; its destructor is row 16 | high |
| 559 | 0x432fc0 | library | libptt (LPC-10) | `analys_` | (speech, voice, pitch, rms, rc, st): the LPC-10 analysis frame: the statics tau and buflim, and calls to dcbias, dyptrk, energy, invert, ivfilt, lpfilt, mload, onset, placea, placev, preemp, rcchk, tbdm, voicin | library identification: the prototype's analys_ (0x3eb3a0, `analys___FPfPiPiPfPfP19lpc10_encoder_state`) has the same callees and constants; the library was rebuilt, so the comparison left these functions unpaired | done: carried as `analys_` |
| 560 | 0x433810 | library | libptt (LPC-10) | `bsynz_` | (coef, ip, iv, sout, rms, ratio, g2pass, st): the pitch-excitation synthesis (static kexc; random_, sqrtf; 0.125, 0.25, 0.75, 342, 2000, 6.928) | library identification: the prototype's bsynz_ (0x3ebe70) has the same constants and callees; caller synths_ | done: carried as `bsynz_` |
| 561 | 0x434680 | library | libptt (LPC-10) | `chanrd_` | chanwr_0_(1, its five arguments, 0) | library identification: the prototype's chanrd_ (5 arguments); caller lpc10_decode | done: carried as `chanrd_` |
| 562 | 0x4346b0 | library | libptt (LPC-10) | `chanwr_` | chanwr_0_(0, its six arguments) | library identification: the prototype's chanwr_; caller lpc10_encode | done: carried as `chanwr_` |
| 563 | 0x4346e0 | library | libptt (LPC-10) | `chanwr_0_` | (n, order, ipitv, irms, irc, ibits, st): packs (n 0) or unpacks (n 1) the 54 bits of a frame with the static iblist | library identification: the f2c multiple-entry body of chanwr / chanrd (static iblist, bit) | done: carried as `chanwr_0_` |
| 564 | 0x435040 | library | libptt (LPC-10) | `dcbias_` | (len, speech, sigout): sums the samples, subtracts the mean | library identification: the prototype's dcbias_ (3 arguments); caller analys_ | done: carried as `dcbias_` |
| 565 | 0x4351d0 | library | libptt (LPC-10) | `decode_` | (ipitv, irms, irc, voice, pitch, rms, rc, st): the frame decoder with the statics ivtab, corth, detab7, descl, deadd, qb, zrc, bit; calls ham84_, median_, pow_ii | library identification: the prototype's decode_ (0x3ecda0), the same statics and callees; caller lpc10_decode | done: carried as `decode_` |
| 566 | 0x435fd0 | library | libptt (LPC-10) | `deemp_` | (x, n, st): the de-emphasis filter (1.9998, 2.0925, 0.585, 2.5) | library identification: the prototype's deemp_ constants; caller synths_ | done: carried as `deemp_` |
| 567 | 0x4360b0 | library | libptt (LPC-10) | `difmag_` | the AMDF difference magnitudes | library identification: the prototype's difmag_; caller tbdm_ | done: carried as `difmag_` |
| 568 | 0x4361e0 | library | libptt (LPC-10) | `dyptrk_` | the dynamic pitch tracker (0.984375, 16, 128 …) | library identification: the prototype's dyptrk_ constants; caller analys_ | done: carried as `dyptrk_` |
| 569 | 0x436640 | library | libptt (LPC-10) | `encode_` | the frame encoder: static enctab, 32768, pow_ii | library identification: the prototype's encode_; caller lpc10_encode | done: carried as `encode_` |
| 570 | 0x436c80 | library | libptt (LPC-10) | `energy_` | (len, speech, rms): sqrt of the mean square | library identification: the prototype's energy_ (sqrtf, 3 arguments); caller analys_ | done: carried as `energy_` |
| 571 | 0x436de0 | library | libptt (f2c) | `i_nint` | (float*): the nearest integer, floor(x + 0.5) or the negative mirror | library identification: the prototype's i_nint (f2c runtime); callers placea_, voicin_, vparms_ | done: carried as `i_nint` |
| 572 | 0x436e70 | library | libptt (f2c) | `r_sign` | (a, b): the magnitude of a with the sign of b | library identification: the prototype's r_sign; callers onset_, vparms_ | done: carried as `r_sign` |
| 573 | 0x436ed0 | library | libptt (f2c) | `pow_ii` | (int* a, int* n): integer power | library identification: the prototype's pow_ii; callers decode_, encode_ | done: carried as `pow_ii` |
| 574 | 0x436f70 | library | libptt (LPC-10) | `ham84_` | (input, output, errcnt): Hamming (8,4) decoding by table | library identification: the prototype's ham84_; caller decode_ | done: carried as `ham84_` |
| 575 | 0x437030 | library | libptt (LPC-10) | `hp100_` | (speech, start, end, st): the 100 Hz high-pass filter (1.859076, 0.902428 …) | library identification: the prototype's hp100_ constants; caller prepro_ | done: carried as `hp100_` |
| 576 | 0x437120 | library | libptt (LPC-10) | `invert_` | (order, phi, psi, rc): Cholesky inversion to reflection coefficients (0.999) | library identification: the prototype's invert_; caller analys_ | done: carried as `invert_` |
| 577 | 0x437550 | library | libptt (LPC-10) | `irc2pc_` | (rc, pc, order, gprime, g2pass): reflection to predictor coefficients (sqrtf) | library identification: the prototype's irc2pc_ (5 arguments); caller synths_ | done: carried as `irc2pc_` |
| 578 | 0x4379b0 | library | libptt (LPC-10) | `ivfilt_` | (lpbuf, ivbuf, len, nsamp, ivrc): the inverse filter | library identification: the prototype's ivfilt_ (5 arguments); caller analys_ | done: carried as `ivfilt_` |
| 579 | 0x437b10 | library | libptt | `PTT_ReleaseTalk` | waits for the PTT RPC (g_cd), RPC command 7 with no input, callback _PTT_SyncCallback | library identification: the prototype's PTT_ReleaseTalk sends command 7 the same way; caller CZNetVoice::WorkerThread | done: carried as `PTT_ReleaseTalk` |
| 580 | 0x437bf0 | library | libptt | `PTT_PushToTalk` | (groupID): the same with command 6 and one word in | library identification: the prototype's PTT_PushToTalk(int groupID) sends command 6; caller CZNetVoice::WorkerThread. The map paired 0x437cf0 with PTT_PushToTalk: see the end of the sheet | done: carried as `PTT_PushToTalk` |
| 581 | 0x438ce0 | library | libptt (LPC-10) | `init_lpc10_decoder_state` | (st): sets the decoder state's fields to their start values | library identification: the prototype's init_lpc10_decoder_state (1 argument); callers create_lpc10_decoder_state and PTT_Heartbeat | done: carried as `init_lpc10_decoder_state` |
| 582 | 0x438f30 | library | libptt (LPC-10) | `init_lpc10_encoder_state` | (st): the encoder state's start values | library identification: the prototype's init_lpc10_encoder_state; callers create_lpc10_encoder_state and PTT_Heartbeat | done: carried as `init_lpc10_encoder_state` |
| 583 | 0x439310 | library | libptt (LPC-10) | `lpfilt_` | (inbuf, lpbuf, len, nsamp): the 31-tap low-pass filter (its coefficients 0.000339723 …) | library identification: the prototype's lpfilt_ constants; caller analys_ | done: carried as `lpfilt_` |
| 584 | 0x439600 | library | libptt (LPC-10) | `median_` | (d1, d2, d3): the median of three | library identification: the prototype's median_ (3 arguments); caller decode_ | done: carried as `median_` |
| 585 | 0x439670 | library | libptt (LPC-10) | `mload_` | (order, awins, awinf, speech, phi, psi): the covariance matrix load | library identification: the prototype's mload_ (6 arguments); caller analys_ | done: carried as `mload_` |
| 586 | 0x43a040 | library | libptt (LPC-10) | `onset_` | the onset detector (1.7, 63, 64; r_sign) | library identification: the prototype's onset_; caller analys_ | done: carried as `onset_` |
| 587 | 0x43a3a0 | library | libptt (LPC-10) | `pitsyn_` | the pitch-synchronous parameter interpolation (expf, logf, 90) | library identification: the prototype's pitsyn_; caller synths_ | done: carried as `pitsyn_` |
| 588 | 0x43b270 | library | libptt (LPC-10) | `placea_` | the analysis window placement (i_nint) | library identification: the prototype's placea_; caller analys_ | done: carried as `placea_` |
| 589 | 0x43b740 | library | libptt (LPC-10) | `placev_` | the voicing window placement | library identification: the prototype's placev_; caller analys_ | done: carried as `placev_` |
| 590 | 0x43ba10 | library | libptt (LPC-10) | `preemp_` | (inbuf, pebuf, nsamp, coef, z): the pre-emphasis filter | library identification: the prototype's preemp_ (5 arguments); caller analys_ | done: carried as `preemp_` |
| 591 | 0x43bbb0 | library | libptt (LPC-10) | `random_` | (st): the decoder's pseudo-random generator | library identification: the prototype's random_ (1 argument); caller bsynz_ | done: carried as `random_` |
| 592 | 0x43bc30 | library | libptt (LPC-10) | `rcchk_` | (order, rc1f, rc2f): reflection-coefficient check (0.99) | library identification: the prototype's rcchk_; caller analys_ | done: carried as `rcchk_` |
| 593 | 0x43bd50 | library | libptt (LPC-10) | `synths_` | the synthesiser: pitsyn_, irc2pc_, bsynz_, deemp_ (0.99, 4096) | library identification: the prototype's synths_ callees; caller lpc10_decode | done: carried as `synths_` |
| 594 | 0x43c140 | library | libptt (LPC-10) | `tbdm_` | the turbo AMDF pitch search (difmag_) | library identification: the prototype's tbdm_; caller analys_ | done: carried as `tbdm_` |
| 595 | 0x43c4e0 | library | libptt (LPC-10) | `voicin_` | the voicing decision (statics dactab, vdc; vparms_, i_nint, sqrtf; 3000, 63, 64) | library identification: the prototype's voicin_; caller analys_ | done: carried as `voicin_` |
| 596 | 0x43cef0 | library | libptt (LPC-10) | `vparms_` | the voicing parameters (i_nint, r_sign; 90) | library identification: the prototype's vparms_; caller voicin_ | done: carried as `vparms_` |
| 597 | 0x43d500 | member | `CRebootState` | `CRebootState` | constructor: CGameState's table and name reset, strdup "RebootState" (zgame.h:0x54) at +4, the CRebootState table (0x48c600) | state.md proposed `__ct__12CRebootStateFv`; small-1.md: called by __sinit_main.cpp at COurGame +556; its destructor is row 15 | high |
| 598 | 0x43d578 | library | SCE libusbkb | `sceUsbKbInit` | (int* max): sceSifInitRpc, binds RPC 0x80000211 ("libusbkb : bind errr"), creates the semaphore, gets the keyboard count, allocates the per-keyboard records (0x38 bytes), installs the interrupt handler 0x43e458 | zInput.md: named by its own messages; caller InitKeyreadStuff, where the prototype called its own sceUsbKeybdInit | high |
| 599 | 0x43d760 | library | SCE libusbkb | `sceUsbKbEnd` | removes the interrupt handler ("RemoveIntcHandler() --> error"), frees the records, deletes the semaphore ("DeleteSema() --> error") | zInput.md: its own messages; no caller | high |
| 600 | 0x43d808 | library | SCE libusbkb | `sceUsbKbGetInfo` | (info*): RPC 1 (0x10 in, 0x90 out) with the end callback 0x43dd80; remembers the request (1) and the output | zInput.md: its own message "sceUsbKbGetInfo: sceSifCallRpc"; callers sceUsbKbInit, GetKeyReadThisFrame | high |
| 601 | 0x43d8a8 | library | SCE libusbkb | `sceUsbKbRead` | (no, data*): for a valid keyboard RPC 2 (0x50 out); remembers request 2, the keyboard and the output | zInput.md: its own message; caller GetKeyReadThisFrame | high |
| 602 | 0x43d978 | library | SCE libusbkb | `sceUsbKbGetLocation` | (no, location*): RPC 3 | zInput.md: its own message; no caller | high |
| 603 | 0x43da48 | library | SCE libusbkb | `sceUsbKbSetLEDStatus` | (no, led): RPC 4 with the LED byte | zInput.md: its own message; no caller | high |
| 604 | 0x43db18 | library | SCE libusbkb | `sceUsbKbSetLEDMode` | (no, mode < 3): stores the mode in the record and sends RPC 5 | zInput.md: its own message; no caller | high |
| 605 | 0x43dc08 | library | SCE libusbkb | `sceUsbKbSetRepeat` | (no, start, interval): both non-negative; stores them at +0x18 / +0x1c of the record and clears the counter +0x14 | zInput.md guessed it; the SDK's sceUsbKbSetRepeat(no, sta, interval) has this shape; the interrupt handler 0x43e458 counts against these fields | medium |
| 606 | 0x43dc50 | library | SCE libusbkb | `sceUsbKbSetCodeType` | (no, type < 2): stores the type at +4 of the record | zInput.md gave SetReadMode or SetCodeType; the conversion 0x43e5e8 branches on +4 (raw codes or converted), and 0x43e8d0 is the read-mode setter, so this is SetCodeType; caller InitKeyreadStuff (0, 0) | medium |
| 607 | 0x43dca0 | library | SCE libusbkb | `sceUsbKbSetArrangement` | (no, arrange < 3): stores it at +8 | zInput.md guessed it (three layouts: the three key tables 0x43e738 picks from) | medium |
| 608 | 0x43dcf0 | library | SCE libusbkb | `sceUsbKbSync` | (mode, int* result): mode 0 waits on the semaphore, mode 1 polls sceSifCheckStatRpc; then the result dispatch 0x43dd90 into *result | zInput.md: sceUsbKbSync of the library (the prototype's one-argument wrapper was removed); callers sceUsbKbInit, GetKeyReadThisFrame | high |
| 609 | 0x43dd80 | library | SCE libusbkb | `fn_0043dd80` | the RPC end callback: iSignalSema of the library's semaphore | zInput.md; passed to every sceSifCallRpc of the library; its internal name is not known | low |
| 610 | 0x43dd90 | library | SCE libusbkb | `fn_0043dd90` | calls the result handler of the pending request (1-5) from the table after the "PsIIlibusbkb2500" tag (0x456c2c ...), then clears the request | zInput.md (the result dispatch); caller sceUsbKbSync; internal name not known | low |
| 611 | 0x43ddf8 | library | SCE libusbkb | `fn_0043ddf8` | result handler 1 (GetInfo): copies the keyboard count, the max and the connection bytes into the caller's info | table entry 0x456c2c of 0x43dd90; internal name not known | low |
| 612 | 0x43de50 | library | SCE libusbkb | `fn_0043de50` | result handler 2 (Read): per read mode copies or converts the received key codes into the caller's data, through the key queue (0x43e4e0 / 0x43e510 / 0x43e580) and the conversion 0x43e5e8 | table entry 0x456c30; internal name not known | low |
| 613 | 0x43e3c8 | library | SCE libusbkb | `fn_0043e3c8` | result handler 3 (GetLocation): copies 7 location bytes, -1 when the keyboard is gone | table entry 0x456c34; internal name not known | low |
| 614 | 0x43e418 | library | SCE libusbkb | `fn_0043e418` | result handler 4 (SetLEDStatus): 0 when the reply byte matches the request, else -1 | table entry 0x456c38; internal name not known | low |
| 615 | 0x43e438 | library | SCE libusbkb | `fn_0043e438` | result handler 5 (SetLEDMode): the same test | table entry 0x456c3c; its bytes equal 0x43e418; internal name not known | low |
| 616 | 0x43e458 | library | SCE libusbkb | `fn_0043e458` | interrupt handler: for each keyboard with a repeat set (start and interval > 0) and a held key, counts its repeat timer (+0x14); SYNC, EI | zInput.md: the handler sceUsbKbInit installs; internal name not known | low |
| 617 | 0x43e4e0 | library | SCE libusbkb | `fn_0043e4e0` | (no): clears the record's repeat counter and its 4-entry key queue (count, head, tail) | caller 0x43de50; internal name not known | low |
| 618 | 0x43e510 | library | SCE libusbkb | `fn_0043e510` | (no, code): pushes a 16-bit code into the 4-entry queue; -1 when full | caller 0x43de50; internal name not known | low |
| 619 | 0x43e580 | library | SCE libusbkb | `fn_0043e580` | (no, out*): pops the oldest code; -1 when empty | caller 0x43de50; internal name not known | low |
| 620 | 0x43e5e8 | library | SCE libusbkb | `fn_0043e5e8` | (no, mkey, led, n, raw codes, out): with code type 0 copies the raw codes, else converts each with sceUsbKbCnvRawCode 0x43e738 by the record's arrangement | caller 0x43de50; internal name not known | low |
| 621 | 0x43e738 | library | SCE libusbkb | `sceUsbKbCnvRawCode` | (arrange, mkey, led, raw): picks the shifted or plain table of the arrangement (0x480650 / 0x480a50 / 0x480e50), maps the code, then the special-key table 0x43e860 | library identification: the SDK's public sceUsbKbCnvRawCode(arrange, mkey, led, rawcode) has this shape and job; caller 0x43e5e8; not named by a message | medium |
| 622 | 0x43e860 | library | SCE libusbkb | `fn_0043e860` | (arrange, code): looks the code up in a 21-entry table per layout (0x481250) and returns its replacement with bit 0x4000, else the code | caller 0x43e738; internal name not known | low |
| 623 | 0x43e8d0 | library | SCE libusbkb | `sceUsbKbSetReadMode` | (no, mode < 2): stores the mode at +0xc; on a change also clears the repeat counter and the key queue | library identification: the SDK's sceUsbKbSetReadMode(no, rmode); the only other two-valued setter, the one the Read handler 0x43de50 branches on (+0xc); no caller | medium |
| 624 | 0x43e940 | library | SCE libusbkb | `sceUsbKbClearRbuf` | (no): RPC 6 with no output, then clears the keyboard's queue and counters | library identification: the SDK's sceUsbKbClearRbuf(no); no caller | medium |
| 625 | 0x485360 | compiler-made | (a unit without code of its own) | `fn_00485360` | static initialiser: builds the CSTable at 0x522180 (0, 0x400) and registers its destructor (__register_global_object) | xcheck-2.md: a byte twin of __sinit_seal_airesponse.cpp (0x485320, CSTable 0x522150); the unit has no code and its name is not known, so `__sinit_<file>.cpp` cannot be filled | low |
| 626 | 0x488ae0 | compiler-made | (an MSL-iostream unit after the game files) | `fn_00488ae0` | static initialiser: constructs std::__nInit (0x48eb90) and std::__wInit (0x48eb94) and registers their destructors | the last static initialisers, after __sinit_hud_scorepopup.cpp; the objects sit just before libptt's globals (g_syncSemaphore 0x48eb98), so the unit is likely one of the libraries linked after the game; its name is not known | low |
| 627 | 0x488b40 | compiler-made | (an MSL-iostream unit after the game files) | `fn_00488b40` | the same with the objects 0x48ec10 / 0x48ec14 | as 0x488ae0; its objects follow the libptt (LPC-10) statics | low |

## Functions that could not be characterised

- 0x15d124 (row 442): not a function in the program; stage3-starts.md withheld its start. Its 4 bytes are a `jr ra` whose delay slot is the first instruction of sceSifInitRpc (0x15d128), so it is an empty function of libkernel's SIF code. Nothing calls it and nothing names it.
- Every other row has at least a description of its body. The bodies whose purpose stays open: 0x205e10 (a DME message handler whose receiver 0x287500 is empty, so the message is unknown), 0x302820 (resets a flag and a float of two unnamed statics), 0x3eacc0 (empty), 0x3520d0 (a wrapper of setLoadImageTagsYX with no known sample name), the two Medius request handlers 0x3d0430 / 0x3d0438 (their request, sent by 0x3d4ea0, is not identified), and the library internals given `fn_` names (RSA lint, Medius KM, rt_msg_client and DME table helpers, libinet and libnetb RPC helpers, libusbkb's result handlers and key queue). The three static initialisers 0x485360, 0x488ae0 and 0x488b40 are clear, but the units they belong to are not known.

## Contradictions with what the program and the map hold

- 0x437cf0, paired in the function map (unsure) with `PTT_PushToTalk__Fi` (name not applied, it shows as FUN_00437cf0): its body sends PTT RPC command 4, which is the prototype's `PTT_SetChannel(int)` (0x3f1040). The prototype's PTT_PushToTalk sends command 6, as the new 0x437bf0 (row 580, `PTT_PushToTalk`) does; the new 0x437b10 sends command 7, the prototype's PTT_ReleaseTalk. So the pair should be 0x437cf0 = PTT_SetChannel. **Settled 2026-11-28** (library-pairs.md): the map and the program follow.
- 0x3d4ea0, paired in the function map (unsure) with `MediusCreateMessageID` (name not applied, its plate says so): its body sends Medius message 0x40 with a 0x2c-byte request and stores a callback in 0x44c314; it is a request function, not the message-id maker. The prototype's MediusCreateMessageID (0x3b4cb0: iTerminateString twice, iCreateAndAllocateMessageID, a counter) is the new 0x3d41ac, whose body is the same with the counter's wrap raised from 0x200 to 999. **Settled 2026-11-28** (library-pairs.md): the map and the program follow.
- The release's LPC-10 and PTT library (0x432fc0 to 0x43cef0, rows 559 to 596) is listed as new functions while the prototype's copies (analys_, bsynz_, chanwr_0_, ... vparms_, pow_ii, r_sign, i_nint) are listed as removed: they are the same functions, rebuilt. The unsure pairs the map made inside the library (lpc10_decode 0x438b80, lpc10_encode 0x438c20, prepro_ 0x43bb70) agree with the callees found here; the PTT_* pairs were not rechecked beyond 0x437cf0. **Settled 2026-11-28** (library-pairs.md): the map and the program follow.
- 0x2c0cc0: zSeal-c.md proposed `CSealCtrl::GetConcealment`, but its one call site (CSealCtrl::ComputeVisibility, 0x2c0570) passes a CZSealBody; this sheet puts it in CZSealBody.
- 0x16f008 ... 0x16f380: zMPEG.md calls them a new EE stream client; they are SCE libcdvd's CD stream functions (sceCdStInit ... sceCdStStat and their worker), named by their own messages and the stream command numbers.
- 0x32bf00 (`CDecalPool::RemoveAll`): the first loop uses the absolute CDecal::m_tempPool (its count 0x52a2a0, its array 0x52a2b0; both labels are exact pairs), whatever pool `this` is, while the second loop uses `this`; CWorld::RemoveDecals calls it on both pools. This is what the code does, not a wrong label, but it is worth a look before the name is settled.
- 0x27a650 and 0x27aac0 (the RestrainBuddy and StabBuddy callbacks) show in the program as thunks under the names of the functions they jump to (CZSealBody::RestrainBuddy, CZSealBody::StabBuddy), so the plan and a name search list two functions of each name; the rows give the callbacks their own names.
- The theVoice global (0x545240) is size-unconfirmed in the data map; its constructor (0x34fe20) writes only the bytes +0 to +0x1a.
