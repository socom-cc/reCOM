# Audit of list medium-anim-a (2026-11-19, socom-port-audit-manim-a)

List `medium-anim-a` of the correctness audit ([AUDIT_PLAN.md](../AUDIT_PLAN.md)): 78 fenced
functions of 200 to 699 bytes (27,092 bytes) in `gamez/zAnim/zanim_cmd_parse.cpp`,
`zanim_cmd_tick.cpp`, `zanim_load.cpp` and `zanim_menu.cpp`. HEAD 0e13d498. Judged file by file in
the scan's rank order (`build/port/audit/scan-medium-anim-a.md`; `zanim_menu.cpp` first, as it held
the top ranks), each body compared with its packet's ELF disassembly instruction by instruction
(operand order, widths and signedness, float operation order, constant words, call arguments,
stores, guards), including the port helpers that stand for the ELF's inline code (UiArgument,
UiSetValve, UiCharSetMask, CSelectedCharsItr::Advance, UiApplyStickPreset, GetUICommandType,
`_zrdr::Get`).

## Counts (78 rows, all judged)

| Verdict | Rows |
|---|---|
| MATCH | 66 |
| DEFECT-FIXED | 9 (A 0, B 1, C 8) |
| DEVIATION-KEPT | 3 |
| UNJUDGED | 0 |

Defect rate 9 / 78 (12%); A or B 1 / 78. Three of the C rows are only the form of a float test

2026-11-20 (audit-closeout): kept guards removed, now DEFECT-FIXED C: #67 (the user's rule: the prototype's behaviour is kept; see [audit-closeout.md](audit-closeout.md)).
(NaN only), four are NULL tests the ELF does not have.

## Fixes (ELF evidence)

- B, #1 zAnimLoadMessage 0x1aacb0: COLOR's reals go through fptoui (0x1aadec, 0x1aadf8, 0x1aae04;
  fptoui 0x16d7a0 gives 0 for a negative value); GCC's `(u32)` gave 0xff for -1.0. Masked unless a
  COLOR component is negative.
- C, #58 / #59 / #60 UIDisableButton / UIEnableButton / UIActivateButton: the m_arg_list NULL test
  before GetCharP(0) removed (0x1d39bc, 0x1d3abc, 0x1d3bbc; the large-anim-c lead).
- C, #48 UINetAddDev: the name is read inline, without UiArgument's NULL test before strcmp
  (0x1d1a60 strcmps it unchecked).
- C (compare forms, NaN only): #24 zAnimWaitTick 0x1b961c (`!(timer + dT <= value)`), #25
  zAnimLoopTick 0x1b97d4 / 0x1b97e8 (`!(time < 0)`, `!(loop_timer < time)`), #33
  zAnimObjectBlendModeTick 0x1bd608 (`!(duration <= 0)`).

## Kept deviations

- #67 CMenuStack::PopUpDialog: a NULL name is neither strcmp'd nor strlen'd (the ELF does both,
  0x1d5f58, 0x1d5f80 / 0x1d5fa0); the code comment now names both calls.
- Already recorded in the code and confirmed: #40 zAnimUIMenuTick's table-size test before the
  direct UICommandTable read (the ELF reads past the end) and its port trace block; #73
  OnListSavedGames zeroing the save header before an unchecked read; #18 zAnimLoadObjectBlendMode
  zeroing the A..D selectors; #58-#60's "" for a NULL name. Also the void returns of
  AnimLoadAnimList and UnloadCmdSet (no caller reads the ELF's value), the CPopUpDialog ctor's
  extra zeroing (zui.h) and the port's own `_calloc` line numbers (debug only).

ELF quirks kept (already commented in the code): Unload_MissionReader passing the mission name to
RemoveArchive, UISwitchProgressiveVideo's NTSC test of the current mode, UINetUpdateIFCVars'
"WRITE" compare, UINetCnfGetDispNames clearing DevDispName when the net name is empty, UIStoreSOP
without variable NULL tests, GetBlendMode answering 2 for every other name or type,
zAnimLoadPauseAnim keeping a record without NAME, zAnimLoadLoop testing the count element's type,
zAnimLoadEndWhile writing through a NULL sequence.

Float checks: ComputeRunTime's sums ((x x + y y) + z z by adda / madd, the run terms) and the VU0
transform in zAnimObjectAddChildTick are in the ELF's order; the literals 0x3a83126f, 0x3ca3d70a,
0x3c8efa35, 0x3c360b61, 0x38d1b717 equal the port's spellings; no argument goes on the stack.

## Leads

- zanim_cmd_tick.cpp zAnimLightTick (large-anim-c) tests `cmd->duration > 0.0f`; if the ELF has
  the `!(duration <= 0)` form of #33, it is the same NaN-only C.
- UiArgument tests the name for NULL before strcmp; the ELF does in most UI commands but not in
  UINetAddDev (#48). Other UiArgument callers outside this list are worth the same check.
- Scan noise met besides the known kinds: the port's own layouts of CMission (theMission +0x1c /
  +0x20, +0x584 / +0x564), _zvid_public (zVid +0x50 / +0x48), CPopUpDialog (2544 / 2604 bytes) and
  CMemCard (+0x18 / +0x28) show as offset differences; all self-consistent.

## What the packets lacked

Exact instruction addresses: the compacted listing leaves out the prologue's register saves, so
addresses counted from the function start are off; `dis.sh` gave them. Also: GetUICommandType
(0x1d0710, the ELF inlines it in #41 / #42) and the UICommandTable words (sym.py, entry 0 has id
1); fptoui's behaviour (dis.sh 0x16d7a0); the bitfields CValve::m_value (16 bits) and CZAnim's word
at +0x2c (m_animset_index bits 3-10); the sizes of _zanim_object_motion_script (60) and the
_zanim_cmd_wait / _message / _si_script layouts; the port-only enums CZNetGame::MP_MAJOR_GAME_STATE
and CZAnimArg::TYPE; the CNode SetRotation / GetRotation overloads; EQUIP_ITEM's width.

## Runs

- Default build (`default.sh audit-manim-a-default`): library exit 0, link 0 undefined.
- Smoke (`gate.ps1 -Only roundtrip`, HEAD 0e13d498 + this list's files): PASS, menus -> m8 ->
  menus four times, in use 18,657,900 bytes flat. No targeted trace: the B fix needs a negative
  MESSAGE COLOR, which no m8 run can be steered to.

## Table

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 68 | 0x1d6080 | 252 | CMenuStack::GetPopUp() | gamez/zAnim/zanim_menu.cpp | MATCH | - | new(2544) unchecked use only when non-NULL; the inline ctor (CPlainBmp, vtables, CWrappedText at +0xa4 with m_height -1, C2D at +0x170, m_child / m_valve cleared, two C2DButtons) and SetString("") through the vtable = the port's ctor + m_text.SetString(""); stored to m_popup either way. The port ctor's extra zeroing is recorded in zui.h. The scan's offsets are the port's larger CPopUpDialog layout. |
| 77 | 0x1d7300 | 416 | ExecuteChooseDefaultEquipment(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | UiCharSet valve (lhu m_value, 0 when missing), iterator ctor (-1, NULL) + Advance; per character GetDefCharTypeName -> GetByNameMod -> &m_weapons (+592) or NULL; assign when the lists differ, clear when none; UpdateCharWeaponUiVars(index); the inlined Advance = the port's. Returns 1. The scan's Add / operator= calls are GCC inlining UpdateCharWeaponUiVars. |
| 69 | 0x1d64c0 | 272 | CMenuStack::HandleCommand(char const*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | strcpy(m_cmds[m_top].arg, DEFAULT_ARGNAME); jump table on type + 1 (-1 .. 8): 0 -> type -1; 1 -> m_top--; 2..8 -> type -1 and m_top--; m_count-- always. |
| 65 | 0x1d5ce0 | 264 | CMenuStack::FlushHistory(bool) | gamez/zAnim/zanim_menu.cpp | MATCH | - | 20 arguments reset to DEFAULT_ARGNAME; while m_list is not empty: back pushed to m_free, strcpy(m_free.back(), MENUHISTORY_STRPOOL), m_list size--; m_popup && flag -> virtual deleting dtor, m_popup = 0. |
| 64 | 0x1d5b10 | 228 | CMenuHistory::CMenuHistory() | gamez/zAnim/zanim_menu.cpp | MATCH | - | Both vectors constructed and reserve(32); 32 times strcpy(m_pool[i] (+12 + 48 i), MENUHISTORY_STRPOOL) and push to m_free. |
| 61 | 0x1d43f0 | 552 | UICheckForcedLaunch(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | left = m_countdown (+0x8c) - zNetGetTime() (s32); 0.001 (0x3a83126f) * left or 0 through fptoui, compared with the 16-bit value, stored, callbacks 1 / 2 on change (the port's UiSetValve; the ELF evaluates the value three times); m_ten_second_launch (+0x9f): the same with m_clock.m_initial_read (+0xa8) and the X-second valve; session master (theNetwork+8) and left <= 0 -> UpdateLocalPersona. fptoui and GCC's cast agree for the positive values. |
| 62 | 0x1d48d0 | 676 | UIStoreSOP(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | Five Find calls first, then per line: type byte 3 -> its string else NULL; ftsGetPlayer()->m_SOPList[i] (+0xe8 + 4 i) assigned (NULL -> replace(0, npos, 0) = CSaferStr::operator=). No NULL test of the variables (ELF quirk, commented). |
| 40 | 0x1d0140 | 480 | zAnimUIMenuTick(_zanim_cmd_hdr*, float*) | gamez/zAnim/zanim_menu.cpp | DEVIATION-KEPT | - | node_ref_index (+0x4) -> Refresh(false), GetNode(i, false), GetFirstVisual, Get2DVisual (slot 0x20), m_2d (+0x68), TickZAnimCmd (slot 0x50) with &result (preset 1); handled -> result. Else GetName(arg) (unused), direct table entry when its id matches (NULL func -> 1), else the search, 1 when none: same. Kept (reason in the code): the port tests id against the table size before the direct read the ELF makes past the end; the port trace block is empty unless a trace build. |
| 70 | 0x1d65d0 | 364 | CMenuStack::~CMenuStack() | gamez/zAnim/zanim_menu.cpp | MATCH | - | Inlined FlushHistory(true) (empty() loop form), the pop-up test repeated, member vector dtors, delete on the flag: the port's FlushHistory(true) + repeated test. |
| 66 | 0x1d5e50 | 204 | Unload_MissionReader() | gamez/zAnim/zanim_menu.cpp | MATCH | - | m_database NULL -> return; 1024-byte "run/" copy; "mp" (2) -> "mp/", else "m" (1) -> "sp/"; strcat mission; RemoveArchive("readerm.zar", mission) (ELF quirk kept, commented). The scan's +0x1c / +0x20 is the port's CMission layout. |
| 74 | 0x1d6f20 | 360 | OnIsEquipmentSelected(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | GetWeaponId(GetName(arg)); iterator over UiCharSet; per character the weapon list scanned for the item byte (12-byte entries) -> 1; none -> 0. |
| 55 | 0x1d3310 | 352 | UISetStickPreset(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | m_pads[0] NULL -> 1; Create("stick_preset", 2), value >= 3 -> 1; SetPreset(1, value); three Adds, then sensitivity, acceleration, dead zone - 0.02 (0x3ca3d70a) set as REAL (type 2, UpdateDependents) = UiApplyStickPreset / UiSetRealVar. |
| 76 | 0x1d71d0 | 300 | ExecuteChooseEquipment(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | GetWeaponId(GetName(arg)); ChooseEquipmentForCharacter(it, item) per selected character (inlined Advance = the port's); returns 1. |
| 56 | 0x1d37c0 | 220 | UISwitchProgressiveVideo(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | UiArgument (INPUT_STRING -> GetCharP(0), no list test); NULL or empty -> 1; NTSC: vidMode (+0x51) != 0 -> videoMode (+0x50) = 0; DTV: videoMode != 2 -> 2 (ELF quirk, commented). The scan's zVid offsets are the port's _zvid_public layout. |
| 57 | 0x1d38a0 | 208 | UICheckVideoMode(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | UiArgument; NULL or empty -> 1; NTSC -> vidMode == 0; DTV -> vidMode == 2; other -> 1. |
| 67 | 0x1d5f20 | 348 | CMenuStack::PopUpDialog(char const*) | gamez/zAnim/zanim_menu.cpp | DEFECT-FIXED | C | kept earlier; guard removed 2026-11-20: strcmp / strcpy of the name as is (0x1d5f58, 0x1d5f80). Earlier: m_top++ first; INPUT_STRING -> GetCharP(0) (no list test); type 3 and the name copied (through a std::string in the ELF); m_count++; g_menuRootNode->FindChild("POPUP", true) (slot 0x24), SetActive(true) (slot 0x34, virtual in the port's znode.h). Kept: the port's NULL-name handling (no strcmp, "" copied) where the ELF strcmps and strlens NULL (strcmp 0x1d5f58, strlen 0x1d5f80 / 0x1d5fa0); the comment now names both. |
| 58 | 0x1d3970 | 252 | UIDisableButton(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | DEFECT-FIXED | C | Fixed: the m_arg_list NULL test before GetCharP(0), which the ELF lacks (0x1d39bc). Rest: m_top++, type 8, strcpy, m_count++, 1. Kept (in the code): "" for a NULL name where the ELF strcpys NULL. |
| 59 | 0x1d3a70 | 252 | UIEnableButton(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | DEFECT-FIXED | C | Fixed: the same m_arg_list NULL test (0x1d3abc). Rest as UIDisableButton with type 7. Kept: "" for a NULL name. |
| 60 | 0x1d3b70 | 252 | UIActivateButton(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | DEFECT-FIXED | C | Fixed: the same m_arg_list NULL test (0x1d3bbc; the large-anim-c lead). Rest as UIDisableButton with type 6. Kept: "" for a NULL name. |
| 73 | 0x1d6d70 | 400 | OnListSavedGames(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | DEVIATION-KEPT | - | Editor push; 7 slots: push, "%d", "SaveGame%d" into the static filename, Exists -> sprintf again, m_game->GetHeader(name, 2, &header) unchecked, "Saved Game", m_description + 3, its first 3 chars (terminated); else "Empty Slot", "--/--/----", "XXX"; pop; pop; Add("SavedGames", 0, 1)->Set. Kept (already in the code): the header is zeroed first where the ELF reuses the stack contents when the read fails. |
| 75 | 0x1d70a0 | 300 | OnCloseAndSwitch(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | UiArgument form inline; strncpy(m_DefaultMenu, name, 64); offline: Pop(0), Switch(&m_menuState, 0); network and session master: m_game_over (+0x9b) -> Pop / Switch, else MPMajorGameState(5 = NEWROUND); UpdateLocalGame(game) either way; network non-master: nothing. |
| 78 | 0x1d74b0 | 504 | ChooseEquipmentForCharacter(CSelectedCharsItr const&, EQUIP_ITEM) | gamez/zAnim/zanim_menu.cpp | MATCH | - | Item byte searched in the list -> found: return; size < 2: return; IsPrimary -> [0].Setup, IsSecondary -> [1].Setup, then UpdateCharWeaponUiVars; else used = sum over [2..] of 2 for 0xbc / 0x98 else 1, need 2 for 0xbc / 0x98 else 1, used + need >= 4 -> return; a local (0xff, 0xff, 0, 0) set up and inserted at the end, UpdateCharWeaponUiVars. |
| 63 | 0x1d5160 | 208 | UIGetNumSavedGames(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | Create(GetName(arg), 2) unchecked; count of Exists("SaveGame0".."9") via the static filename; UiSetValve(count). |
| 71 | 0x1d6790 | 296 | _SaveSavedGame(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | atoi(UiArgument); GetByName("SavingSavedGame"); sceCdReadClock; "%-3s%d/%d/%d" with database, month (+6), day (+5), year (+7) bytes; SaveGame("SaveGame<n>", description); valve -> set 0 with callbacks 2 on change. |
| 72 | 0x1d68c0 | 248 | _LoadSavedGame(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | atoi(UiArgument); GetByName("LoadingSavedGame"); LoadGame("SaveGame<n>"); valve -> set 0. |
| 41 | 0x1d0330 | 380 | zAnimLoadUIAppMenu(_zrdr*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | _calloc(1, 8, line 4317); timeless bit and data_size 8 (the +2 halfword); +4 = GetUICommandType(TYPE) (inlined: NULL 0x95, empty 0, the table's case-insensitive search from entry 0, 0 when none; the port's loop condition is equivalent, entry 0 has id 1); ARGUMENT non-empty -> strcpy to a 128-byte buffer, +5 = AddName. |
| 42 | 0x1d04b0 | 600 | zAnimLoadUIMenu(_zrdr*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | NODE -> LoadNodeNames(tag, 0, 0, scope bits of +4) & 0xffff; non-zero -> Refresh(false), GetNode, GetFirstVisual, Get2DVisual (slot 0x20), m_2d; ParseZAnimCmd (slot 0x4c) -> node_ref stored, returned. Else the 8-byte record (line 4287), +4 node_ref, +6 type, +7 argument name: same. |
| 43 | 0x1d0ce0 | 224 | UINetCensorText(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | Offline -> 1; strcasecmp("$1", name) -> GetCharP(0); Find; NULL or not a string -> 1; Censor(string, AuxNetCensorText, var); the variable = "CHECKING FOR APPROPRIATE LANGUAGE...". |
| 44 | 0x1d0ec0 | 208 | UINetSaveCombo(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | ticking: SaveComboTick -> 0 or (ticking = 0, 1); else "Combination%d" NumCombos + 1, GetComboData, attach_ifc / attach_dev (+256) from pIFCInfo / pDevInfo sys_name (+8), both idle timeouts (+0x1308, +0x1318) 10, ticking = SaveCombo, returns 0. |
| 45 | 0x1d0f90 | 228 | UINetGetIFCInfo(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | Valve value (lhu, so the >= 0 test always holds in both); Add IFC_NAME; IFC_COUNT = NumIFC via the inline set; pIFCInfo = GetIFC(which), IFC_NAME = usr_name (+264). |
| 46 | 0x1d1080 | 228 | UINetGetDevInfo(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | As #45 with DEV_NAME / DEV_COUNT, NumDevs, GetDev, pDevInfo. |
| 47 | 0x1d1170 | 640 | UINetUpdateIFCVars(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | Nine Adds in order; READ (strcasecmp, no NULL test in either): INTERFACE_INDEX valve, GetInterfaceEntry, "Settings for %s/%s" (+12, +268), five "0.0.0.0", three ""; else strcasecmp "WRITE" only (ELF quirk, commented). The scan's missing 'WRITE' is a merged string. |
| 48 | 0x1d1a10 | 248 | UINetAddDev(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | DEFECT-FIXED | C | Fixed: the port's UiArgument tests the name for NULL before strcmp; this ELF function does not (0x1d1a60), so the read is inline now. Rest: not ticking -> ticking = AddDev(HCnf, name), 0; AddDevTick -> 0 or MACAddr = GetMACAddr(buf, 128), ticking = 0, 1. |
| 49 | 0x1d1b10 | 568 | UINetGetInterfaceList(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | not ticking -> ticking = ReadInterfaceList, 0; tick -> 0 or: three Adds, InterfaceCount, three editors pushed, per entry "%s/%s" to uninstalled (installed word +8 == 0) or installed, and to all; pops, Sets, ticking = 0, 1. |
| 50 | 0x1d1d50 | 372 | UINetCnfGetDispNames(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | combo = valve value - 1; NetDispName = net; strncpy(both, net, 80); DevDispName = dev; both[0] -> "/" + dev, NetDevDispName = both; else DevDispName = "" (ELF quirk, commented); IfcDispName = GetIfcDisplayName. |
| 51 | 0x1d2120 | 348 | UITestUIVar(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | NULL name or variable -> 0; type 1: integer != 0; 2: !(0 == real) (= the port's != for NaN too); 3: string and its first char; 4: array[0].integer - 1 != 0; else 0. The scan's cvt is the ELF's unreachable nested type tests. |
| 52 | 0x1d2470 | 228 | UIAdvanceMPMission(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | No game or offline -> 1; game-over valve (+0xc) value -> 45000 else 30000 added to zNetGetTime into m_countdown (+0x8c); master: AdvanceMissionSequence > 0 -> "mp%d" into database; UpdateLocalGame; PreOpen(database). |
| 53 | 0x1d2620 | 228 | UISendClanMessage(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | Add SEND_CLAN_MESSAGE; not a string -> 1; std::string of the string (NULL -> empty); SendClanMessage(c_str) & 0xff. |
| 54 | 0x1d2980 | 228 | UIInvitePlayerToClan(C2DAnimCmdHdr*, float*) | gamez/zAnim/zanim_menu.cpp | MATCH | - | As #53 with PLAYER_INVITE_NAME and InvitePlayerToClan. |
| 26 | 0x1b98b0 | 372 | zAnimObjectAddChildTick(_zanim_cmd_hdr*, float*) | gamez/zAnim/zanim_cmd_tick.cpp | MATCH | - | GetNode(+6), GetNode(+7); either NULL -> 1; point zeroed; flag 1 -> child TransformToWorld; parent AddChild (slot 0x18); flag 1 -> unit matrix, BuildMTW, Vu0MatrixInverseWithUniformScale, the VU0 transform m0 x + m1 y + m2 z + m3 (the port's sum in the same order), SetPosition. The scan's float ops are the port spelling the VU0 code in C. |
| 31 | 0x1bd1f0 | 304 | zAnimObjectRotateStateTick(_zanim_cmd_hdr*, float*) | gamez/zAnim/zanim_cmd_tick.cpp | MATCH | - | GetNode(+6), GetNode(+7); node NULL -> 1; rotation zeroed; position (+0x30..+0x38) read first; at -> BuildMTW, SetMatrix; flag 1: 0 + rotation -> SetRotation(CPnt3D*); flag 2: GetRotation + rotation -> SetRotation; SetPosition(saved). |
| 32 | 0x1bd320 | 496 | zAnimObjectTranslateStateTick(_zanim_cmd_hdr*, float*) | gamez/zAnim/zanim_cmd_tick.cpp | MATCH | - | flag 4: pos + offset, else flag 1: 0 + offset; flag 2: arg list (NULL -> none) GetPnt3D(5) added; nothing and no AT -> 1; AT -> TransformToWorld; position re-read afterwards; flags 8 / 0x10 / 0x20 keep x / y / z; SetPosition. |
| 34 | 0x1bfd90 | 240 | zAnimDestructorTick(_zanim_cmd_hdr*, float*) | gamez/zAnim/zanim_cmd_tick.cpp | MATCH | - | Vectors (0x1c, 0x24, 0x2c), (0x20, 0x28, 0x30), (0x34, 0x38, 0x3c), (0x40, 0x44, 0x48); sprintf("%s", GetName(+5)) (GCC's strcpy); GetNode(+4); DestructionManager(node, name, +8, +0x18, the four vectors, strips +6, +0x4c). The comment's "friction +0x3c" is part of the third vector. |
| 29 | 0x1baf10 | 492 | CZAnimFromToAcc::Tick(float, CPnt3D*) | gamez/zAnim/zanim_cmd_tick.cpp | MATCH | - | Loop while !(dt <= 0); step = dt; phase 1 / 2: timer + dt <= limit -> dt 0, timer += dt, else step = limit - timer, timer 0, dt -= step, next phase (1: cruise <= 0 -> 3); phase 1 speed += accel * step, 2 speed = max; 3: speed += decel * dt, timer += dt; other: dt 0; pos += (direction * speed) * step. |
| 21 | 0x1b8ce0 | 200 | zAnimBreakTick(_zanim_cmd_hdr*, float*) | gamez/zAnim/zanim_cmd_tick.cpp | MATCH | - | do CmdNext; valid and an ENDIF (halfword compare with m_cmd_endif) at this IF level (+4 vs seq +7) -> level--; while valid and not END_WHILE. The ELF's seq NULL selects are the inline cmd_pc read. |
| 30 | 0x1bb100 | 556 | CZAnimFromToAcc::ComputeRunTime(CPnt3D*, CPnt3D*) | gamez/zAnim/zanim_cmd_tick.cpp | MATCH | - | from - to; sqrtf((x x + y y) + z z) (adda / madd); accel / decel times; run = (start at + at (0.5 accel at)) + (max dt + dt (0.5 decel dt)), same grouping; dist - run < 0 -> halving from max with !(fabs <= 0.0001 (0x38d1b717)), peak = 0.5 (high + low), the same tests; cruise 0 or left / max; returns the sum. |
| 22 | 0x1b8f20 | 436 | zAnimIfTick(_zanim_cmd_hdr*, float*) | gamez/zAnim/zanim_cmd_tick.cpp | MATCH | - | level++; CmdNext(8), ProcExpr true -> 1; else step until invalid or ELSE / ELSEIF / ENDIF at this level (ENDIF -> level--); ELSEIF -> test again, else 1. |
| 24 | 0x1b95c0 | 256 | zAnimWaitTick(_zanim_cmd_hdr*, float*) | gamez/zAnim/zanim_cmd_tick.cpp | DEFECT-FIXED | C | Fixed: the timed test is the ELF's timer + dT <= value (0x1b961c, wait) where the port tested value < timer + dT (NaN only). Rest: clock by flags 4 / 2 / else, used = value - timer clamped at 0 (c.lt), dT -= used; counted: counter++ (u16), not done while counter <= the word at +8 / +0xc. |
| 23 | 0x1b90e0 | 328 | CZAnimExpression::NewCmd(char const*) | gamez/zAnim/zanim_cmd_tick.cpp | MATCH | - | NULL -> NULL; GetCmdEntry("EXPRESSION", false), _calloc(1, 8, line 4153), op by strcmp ("!" 1, "&&" 2, "||" 3, "(" 4, ")" 5, else 0) at +4; data_type from the entry, data_size 8, timeless. |
| 25 | 0x1b9750 | 216 | zAnimLoopTick(_zanim_cmd_hdr*, float*) | gamez/zAnim/zanim_cmd_tick.cpp | DEFECT-FIXED | C | Fixed: the timed end is the ELF's !(time < 0) and !(loop_timer < time) (0x1b97d4, 0x1b97e8) where the port tested 0 <= time and time <= loop_timer (NaN only). Rest: loop_counter++ (s16), loop_timer += dT + seq_timer; counted: count != -1 and == counter -> 1; else SeqSetState(3), 0. |
| 27 | 0x1b9a30 | 216 | zAnimMultiObjectMotionScriptTick(_zanim_cmd_hdr*, float*) | gamez/zAnim/zanim_cmd_tick.cpp | MATCH | - | NULL or count 0 -> 1; per 60-byte entry at +8: *dt = step, tick, not done -> done 0, least = min (c.lt); *dt = least. |
| 28 | 0x1b9b80 | 524 | zAnimObjectMotionScriptTick(_zanim_cmd_hdr*, float*) | gamez/zAnim/zanim_cmd_tick.cpp | MATCH | - | NULL entry or node ref 0 -> 1; GetNode; GetAnimSet(m_animset_index, bits 3-10 of +0x2c: the port's bitfield is the same bits), SIScript(+7); no script -> 1; time = cmd_timer; offset >= size -> 1; loop: time += apply_script_frame; !(dt <= 0): frame_count++, offset += 16 (+80 per flag 1 / 2 / 4), frame_time 0, end -> done; while !(dt <= 0) and not done. |
| 33 | 0x1bd590 | 556 | zAnimObjectBlendModeTick(_zanim_cmd_hdr*, float*) | gamez/zAnim/zanim_cmd_tick.cpp | DEFECT-FIXED | C | Fixed: the duration test is the ELF's !(duration <= 0) (0x1bd608) where the port tested duration > 0 (NaN only). Rest: alpha word 0x44; GetNode(+6) NULL -> 1; step + cmd_timer <= duration -> dT 0, not done, else step = duration - timer, dT -= step; flags 1 / 2 / 4; FIX = fptosi(128 fix) clamped 0..255; A..D from +7; flag 8 -> GetBlendSequenceValue(+seq_offset, count, step + cmd_timer); SetBlendMode. |
| 1 | 0x1aacb0 | 376 | zAnimLoadMessage(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | DEFECT-FIXED | B | Fixed: COLOR's three reals go through fptoui (0x1aadec, 0x1aadf8, 0x1aae04), which gives 0 for a negative value; GCC's (u32) cut -1.0 to 0xff. Masked unless a COLOR component is negative (not seen; m8's anim data not searched). Rest: _calloc(1, 8), timeless, data_size 8; MESSAGE non-empty -> 128-byte copy, AddName to +4; RED / GREEN / BLUE low bytes (each preset 0) to +5..+7; COLOR (unchecked findPNT3D) replaces them. The _calloc line is the port's (debug only). |
| 3 | 0x1aea20 | 580 | CZAnimObjectMotion::GetTranslation(_zrdr*, float*, float*, float*, float*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | Per output i = 0..3: list length (type 4: array[0].integer - 1, else 0) > i -> element i + 1's REAL, INTEGER (cvt) or 0, else 0; returns 1. The scan's Get calls are the inline the ELF expands. |
| 19 | 0x1b47b0 | 364 | CZAnimBlendMode::GetBlendMode(_zrdr const*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | String: SRC 0, FB 1, "0" / ZERO / VALUE 2, else 2; integer: 2 either way; other types 2 (ELF quirk, commented). The scan's missing strings are suffix-merged. |
| 18 | 0x1b3560 | 648 | zAnimLoadObjectBlendMode(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | DEVIATION-KEPT | - | _calloc(1, 20), timeless, size 20; NAME -> node byte +6, flags 0, duration 0; RECURSIVE 4, PRIMARY_FACE 1, SUB_FACE 2; BLENDMODE -> fix preset 1.0, GetBlendModes, A..D into +7, fix +8; BLEND_VALUE_SEQUENCE -> seq_offset = data_size, GetBlendValueSequence, count > 0 -> flag 8, seq_count, !(end <= duration) -> duration = end; missing NAME / BLENDMODE / false -> free, NULL. Kept (already in the code): a..d zeroed where the ELF leaves them unset. |
| 14 | 0x1b1a20 | 360 | zAnimLoadObjectOpacityFromTo(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | NULL -> NULL; _calloc(1, 24), size 24 (not timeless); NAME -> halfword +4; RUN_TIME found: <= 0 -> 0x3a83126f, missing: 1.0; inv = 1 / duration; FROM +8, TO +0xc; rate = inv * (to - from). |
| 2 | 0x1abb80 | 364 | zAnimLoadObjectAddChild(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | NULL -> NULL; _calloc(1, 8), size 8 (not timeless); PARENT / CHILD: NAME sub-tag else the tag, LoadNodeNames to +6 / +7, 0 when missing; RETAIN_WORLD_LOCATION -> flag 1. |
| 11 | 0x1b0b00 | 272 | zAnimLoadEndWhile(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | NULL -> NULL; timeless 8 bytes; size > 0 (signed) -> pop, freed (line 113) when empty; offset -> jump halfword +6 = offset, the WHILE's jump at seq + offset = seq_data_size (seq NULL: 0 written at the offset, ELF quirk); else free (2718), NULL. |
| 4 | 0x1aec70 | 264 | zAnimLoadStopSequence(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | Timeless 8 bytes (line 3492); NAME missing -> free (3504), NULL; first element (inline Get, NULL for an empty list) string or NULL -> AddName to +4. |
| 5 | 0x1aed80 | 264 | zAnimLoadCallSequence(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | As #4 (lines 3462 / 3474). |
| 6 | 0x1aee90 | 284 | zAnimLoadInvalidateAnim(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | As #4 with ZAnimWildcardApply before AddName; no NAME clears +4 then frees (3444). |
| 7 | 0x1aefb0 | 280 | zAnimLoadResumeAnim(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | As #6 (lines 3397 / 3409), no clear before the free. |
| 8 | 0x1af0d0 | 256 | zAnimLoadPauseAnim(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | As #7 but no NAME keeps the record with index 0 (ELF quirk, commented). |
| 9 | 0x1af1d0 | 280 | zAnimLoadStopAnim(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | As #7 (lines 3340 / 3352). |
| 12 | 0x1b0c10 | 416 | zAnimLoadWhile(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | NULL -> NULL; timeless 8 bytes; a one-element list whose element is the string TRUE -> skip_test (+4) = 1, else AnimParseExpression; realloc(size + 1, line 84), push seq_data_size (0 without a sequence), size++. |
| 20 | 0x1b7b90 | 208 | zAnimGetDirectionFromAzimuthZenith(float, float, CPnt3D*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | angle = 0x3c8efa35 * az; x = sinf, z = cosf; y = 0x3c360b61 * zen; x, z negated; flat = y < 0 ? 1 + y : 1 - y; x, z scaled. |
| 10 | 0x1b06e0 | 332 | zAnimLoadNodeActive(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | Timeless 8 bytes (2882); NAME -> halfword +6; no STATE -> arg 1; array[1].string (unchecked) ACTIVE 1, INACTIVE 2; else / no NAME -> free (2930), NULL. |
| 13 | 0x1b18d0 | 332 | zAnimLoadLoop(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | NULL -> NULL; timeless 12 bytes; LOOP_COUNT: flag 1, count -1, array[0] integer 2 and type 1 -> count = array[1].integer (ELF quirk, commented); else LOOP_TIME: flag 2, time -1.0, findreal -> record; else free (2389), NULL. |
| 15 | 0x1b2fb0 | 516 | zAnimLoadObjectRotateState(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | Timeless 20 bytes (1885); no NAME -> free (1939), NULL; node +6, LIKE_NODE +7 (0 without); ROTATION (findtag, findreal 3) -> flag 1, three * 0x3c8efa35; RELATIVE -> flag 2, the same into the same offset. |
| 16 | 0x1b31c0 | 600 | zAnimLoadObjectTranslateState(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | Timeless 20 bytes (1798); no NAME -> free (1867), NULL; node +6, AT_NODE +7; TRANSLATION 1, INPUT_TRANSLATION 2, RELATIVE 4 (into the same offset); UPDATE without X / Y / Z -> 8 / 0x10 / 0x20. |
| 17 | 0x1b3420 | 316 | zAnimLoadObjectActiveState(_zrdr*) | gamez/zAnim/zanim_cmd_parse.cpp | MATCH | - | Timeless 8 bytes (1732); NAME -> halfword +6; STATE required: array[1].string ACTIVE 1, INACTIVE 0; else free (1780), NULL. |
| 37 | 0x1c1dd0 | 340 | CZAnimMain::AnimLoadAnimList(char const*, _zrdr*) | gamez/zAnim/zanim_load.cpp | MATCH | - | count = array[0].integer - 1 (type unchecked); pairs from 1 while i < count; a non-string key ends it (the ELF's -1; port void, recorded); ANIMATION_DEFINITION -> flat_nexttag(value, "NAME", NULL) + 1 element, AnimLoadNameZRDR; ANIMATION_DEFINITION_FILE -> AnimLoadZRDFile(path, value's array[1].string); ANIMATION_PATH compared only. The scan's missing strings are merged. |
| 35 | 0x1c0240 | 256 | CZAnimMain::OpenZAR(char const*) | gamez/zAnim/zanim_load.cpp | MATCH | - | No m_LoadFromZAR -> NULL; new(164) CZAR(NULL, NULL) with CZAnimZAR's vtable, NULL -> NULL; no "zanim.zar" in the name -> "%s/%s" name, "zanim.zar", else "%s"; Open(path, 0, 1, 16) -> archive, else deleting dtor (slot 8), NULL. |
| 36 | 0x1c0340 | 560 | CZAnimMain::LoadZAR(CZAnimZAR*, char const*) | gamez/zAnim/zanim_load.cpp | MATCH | - | No m_LoadFromZAR -> 1; m_pFile NULL or not IsOpen (slot 0x10) -> 0; Anim_Main_Params (16) fetched, failed or version != 30 -> 1; fetched into this, name table Load, Anim_Set_Count, GetOpenKey, OpenKey("Anim_Sets"); NULL -> 1; per key: OpenKey NULL -> next (no close); setname NULL or strcasecmp -> GetAnimSet(GetAnimSetIndex(name, true)), current set / anim / seq, Load; CloseKey; CloseKey(sets); 1. |
| 38 | 0x1c2270 | 248 | CZAnimMain::UnloadCmdSet(int) | gamez/zAnim/zanim_load.cpp | MATCH | - | Bad index -> return (the ELF's 0; void recorded); 12-byte set: cmd_list -> names of the 24-byte entries freed (136) and cleared, list freed (121), list / count 0; name freed (127), cleared. |
| 39 | 0x1c23c0 | 248 | CZAnimMain::Unload() | gamez/zAnim/zanim_load.cpp | MATCH | - | Name table Unload; sets list: each (48-byte) set's Unload under the inline GetAnimSet range test, freed (46), NULL; count 0, current set 0; command sets: UnloadCmdSet each, freed (99), NULL; count, current anim, seq 0; 1. |
