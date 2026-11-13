# Destination-narrowing return audit (stage 3, accepted recon plans)

Read-only scan, 2026-10-24, for build/facts/repair-queue.md "Destination-narrowing returns". Disposable; tracker evidence is authoritative.

## Method
- Scope: every row of an accepted plan (`progress sql`, 269 accepted plan items incl. repairs 001-005) in build/recon-plans/*.json (evidence and draft helper files skipped) whose return is uchar/char/schar/ushort/short/bool: 365 rows.
- `recon facts --function <all 365> --callers 99` exit lines classified the v0 source at every exit; `recon dwarf --address` checked the 53 rows that have a DWARF record (every one has a DWARF return of the same width, so they are out of scope).
- Rows whose recorded return evidence rests only on caller-side narrowing (andi 0xff/0xffff, sb/sh, recursive self-calls, wrappers, a vtable call site) or on a dispatcher narrowing its own return were re-checked with `recon asm`, `recon facts`/`recon live` of chained callees, `recon void`/`recon refs` slot families, `recon dwarf` and get_struct_layout (CAiCell).
- proven: the callee (or a callee it tail-returns, or an override in its slot family) narrows v0 before jr ra, or returns a byte/halfword member. proven (var): the only callee-side narrowing is of a local that is returned (the zrdr_tobool precedent); weaker, listed separately. unproven: every exit returns constants, 0/1 compare results (slt/sltu/xori), an unnarrowed value, or an unproven callee result.
- Out of scope (not listed): 53 DWARF-backed rows, 71 rows whose own exit narrows and whose evidence cites it, and 98 rows declared by a callback/remove_if/sort/AddTask/AddCmd `_b` type, a DWARF-typed base, a header, a typed argument, or callee narrowing cited in the evidence.

## Counts
- audited rows: 143; unproven 134 (of which 57 UICommandTable handlers); proven (var) 5; proven 4.
- 0x1a2e80 and 0x1a9590 (group 068d287b) are live `undefined`: socom:recon-group:068d287bbb2c9c569ef1-apply is still ready, so fix the plan before apply instead of a repair.

## Rows

| address | function | group | live return | verdict | evidence |
| --- | --- | --- | --- | --- | --- |
| 0x1d2560 | UIIsClanChallengeGame__FP13C2DAnimCmdHdrPf | 063fb483 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d2cf0 | UICoopMissionExists__FP13C2DAnimCmdHdrPf | 063fb483 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d3fc0 | UIClearGameState__FP13C2DAnimCmdHdrPf | 063fb483 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d4700 | UIIsTerrorist__FP13C2DAnimCmdHdrPf | 063fb483 | uchar | unproven | UICommandTable handler; sltu/xori 0/1; dispatcher narrowing only |
| 0x1d4720 | UIKillPopUp__FP13C2DAnimCmdHdrPf | 063fb483 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d4f30 | UIGetAcctInfo__FP13C2DAnimCmdHdrPf | 063fb483 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d55e0 | UIIsSessionMaster__FP13C2DAnimCmdHdrPf | 063fb483 | uchar | unproven | UICommandTable handler; 1/0 constants; dispatcher narrowing only |
| 0x1a2e80 | CVehicleRdr::Load | 068d287b | undefined | unproven | only exit returns sltu v0,zero,v0 (0x1a3704); only the caller narrows; no DWARF |
| 0x1a9590 | CAiMap::FindLookLoc | 068d287b | undefined | unproven | exits return li 1 / move zero; only callers narrow; no DWARF |
| 0x1d2f20 | UIMC_ChDir | 06f0b3d1 | uchar | unproven | UICommandTable handler; returns CMemCard::chdir 0x306c40 (zero / sltiu only); dispatcher narrowing only |
| 0x1d2fa0 | UIIsSpaceForSaveGameFile | 06f0b3d1 | uchar | unproven | UICommandTable handler; slti/xori 0/1; dispatcher narrowing only |
| 0x1d52e0 | UIFormatMemCard | 06f0b3d1 | uchar | unproven | UICommandTable handler; j CMemCard::Format 0x3072c0 (zero / sltiu only); dispatcher narrowing only |
| 0x1d52f0 | UIIsMemCardFormatted | 06f0b3d1 | uchar | unproven | UICommandTable handler; j CMemCard::IsFormatted 0x307310 (s0 = 0 / sltu only); dispatcher narrowing only |
| 0x1daf80 | zar::CZAR::FetchLIP | 070819d4 | uchar | unproven | exits return s4 = 0 (0x1dafd4), sltiu s4,s4,1 (0x1db03c) or sltu s4,zero,v0 (0x1db060): 0/1 only; only callers narrow (andi at 0x30a150, 0x30a258) |
| 0x1db0a0 | zar::CZAR::Fetch | 070819d4 | uchar | unproven | exits return s4 = 0 (0x1db0b0) or sltiu s4,s4,1 (0x1db13c, 0x1db17c): 0/1 only; only callers narrow |
| 0x1dbb30 | zar::CZAR::Fetch | 070819d4 | uchar | unproven | only exit returns sltu v0,zero,v0 (0x1dbc4c); only callers narrow (andi a0,v0,0xff at 0x1bffb4, 0x1c03bc) |
| 0x1f0380 | CEntity::OnUpdateTargetList | 070819d4 | uchar | unproven | exits return li v0,1 / move v0,zero; no word refs; only the caller UpdateTargetList narrows (andi s0 at 0x1f00a0) |
| 0x2d1f00 | CSealUnit::GetUnitLeaderHandle | 08b12c4b | uchar | unproven | returns s1 = lb s1,644(v0) (0x2d1f68, sign-extending), 0 or the recursive result, unnarrowed (move v0,s1 at 0x2d2010): a uchar return would need zero-extension before jr ra, so the asm contradicts uchar; callers' andi are destinations |
| 0x17ec00 | is_moving__2aiFPC6CPnt3Df | 0bc0c825 | uchar | unproven | returns 0/1 constants; only the caller narrows; no DWARF or stage 2 record (the text cites only the bool spelling) |
| 0x17f210 | Tick__8CAiEventFf | 0bc0c825 | uchar | unproven | returns 0/1 constants; no word refs; only the caller narrows; no DWARF |
| 0x26c860 | IsAi__11CSealCtrlAiCFv | 0c23b08b | uchar | unproven | returns li 1; slot 0x30 family (CSealCtrl::IsAi 0, CSealCtrlAi::IsAi 1) has constants only and no DWARF; only slot call sites narrow; the DWARF IsPlayer is slot 0x2c |
| 0x3ff9f0 | CNetCnf::Uninit | 1388aea1 | uchar | unproven | only exit returns li v0,1; only the caller UINetCnfUninit narrows (andi v0 at 0x1d20b4 proves UINetCnfUninit's own return, not this one) |
| 0x267e20 | CAiCone::ContainsPoint | 14a80014 | uchar | unproven | exits return li v0,1 / move v0,zero; only callers narrow |
| 0x1d3b70 | UIActivateButton | 15983d99 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d4620 | UIForceMPLaunch | 15983d99 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d4b90 | UIGameHasPassword | 15983d99 | uchar | unproven | UICommandTable handler; returns CZOnlineLobby::GameIsPasswordProtected 0x325b40 (li 1 / zero only); dispatcher narrowing only |
| 0x1d69c0 | @unnamed@zanim_menu_cpp@::UISetControllerConfig | 15983d99 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d6f20 | @unnamed@zanim_menu_cpp@::OnIsEquipmentSelected | 15983d99 | uchar | unproven | UICommandTable handler; li 1 / zero; dispatcher narrowing only |
| 0x23d230 | zrdr_findPNT3D | 15f81547 | uchar | unproven | exits return daddiu v0,zero,1 / move v0,zero; only the caller ftsFixupAiMap narrows (andi s3 at 0x1f4c10) |
| 0x23d9d0 | zrdr_findreal | 15f81547 | uchar | unproven | exits return daddiu v0,zero,1 / move v0,zero; only the caller CMission::PreOpen narrows |
| 0x193540 | PointInPath__7CAiPathCFRC9CAiMapLocPUi | 16c84908 | uchar | unproven | returns 0/1 constants; only the caller narrows; no DWARF |
| 0x19d950 | _close_enough<f>__FRCfRCfRCf | 16c84908 | uchar | unproven | returns 0/1 constants; only callers narrow; no DWARF |
| 0x1d5310 | UICheckJoinMP | 19ea6ebb | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d2f80 | UIMC_Init | 1bcbb373 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x222750 | CPnt3D::DistToVector | 1c1a2e49 | uchar | unproven | exits return li v0,1 / move v0,zero; only callers narrow |
| 0x2b2ca0 | CSealCtrl::_GetTargetPerception | 2183ba87 | uchar | unproven | s3 is 0 or daddiu s3,zero,1 (0x2b302c) at the exit; other exits move v0,zero; only callers narrow |
| 0x224df0 | SetDescendantVisuals__Q23zdb5CNodeFb | 234ba671 | uchar | unproven | exits return constants or sltu 0/1; the only narrowing is the recursive self-call's caller-side andi s1,v0,0xff (0x224eb8); not virtual |
| 0x224f30 | SetDescendantDI__Q23zdb5CNodeFb | 234ba671 | uchar | unproven | exits return constants or sltu 0/1; the only narrowing is the recursive self-call's caller-side andi s0,v0,0xff (0x225004); not virtual |
| 0x1a9970 | CAiMap::FindCoverLoc | 24e379ef | uchar | unproven | exits return li 1 / move zero; only callers narrow; no DWARF |
| 0x1d1840 | UINetGetDevIndex | 24e379ef | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d1ed0 | UINetCnfSelectCombo | 24e379ef | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d1f20 | UINetCnfCurrCombo | 24e379ef | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d1fa0 | UINetCnfCount | 24e379ef | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d23e0 | UISetMPMissionSeq | 24e379ef | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d2fd0 | UIInitializeOptions | 24e379ef | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d3fd0 | UIFlushMenuHistory | 24e379ef | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d48d0 | UIStoreSOP | 24e379ef | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d5160 | UIGetNumSavedGames | 24e379ef | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d2e20 | UIMC_Exists | 2f4d708d | uchar | unproven | UICommandTable handler; returns CMemCard::Exists 0x306cf0 (s0 = 0 / daddiu 1 only); dispatcher narrowing only |
| 0x259230 | CSealCtrlAi::HasSniperRifle | 365986aa | uchar | unproven | tail j to CZKit::HasSniperRifle 0x2af290, which returns only li 1 / 0 (itself unproven); the caller converts with sltu |
| 0x25e360 | CSealCtrlAi::ComputeThrowFireParams | 365986aa | uchar | unproven | s0 is only daddiu s0,zero,1 (0x25e38c); other exits 0; only callers narrow |
| 0x384380 | UiGetDirStickMoved__Fv | 3994c577 | uchar | unproven | exits return li 0..5 constants; only callers narrow |
| 0x384820 | GetStickDir__Fv | 3994c577 | uchar | unproven | exits return li 1..4 constants; only the caller CUIMapCtrl::HandlePad narrows |
| 0x2ef700 | CSndInstance::Tick | 3a6a6699 | uchar | unproven | exits return li 1 / move zero; no word refs; only the caller narrows (andi v1 at 0x2ef928) |
| 0x31e410 | CZWeapon::GetIDType | 3e32bb1c | uchar | unproven | tail-returns CZWeapon::GetIDType(EQUIP_ITEM) 0x31e1c0, which returns only constants (itself unproven); only callers narrow |
| 0x151460 | euc2jis | 3f609906 | ushort | unproven | returns xori v0,v0,0x8080 of the entry-zero-extended a0 (andi v0,a0,0xffff at 0x151460): parameter narrowing only, no narrowing of the result before jr ra; the caller's andi a2,v0,0xffff (0x150d00) is its destination |
| 0x318d70 | CZProjectile::DoMiss | 487ba19f | uchar | unproven | exits return li v0,1 (0x318f6c) / move v0,zero (0x318f1c, 0x318f54, 0x318f60); the single caller HandleIntersections narrows into its byte local (andi s7 at 0x3194c8) |
| 0x300c10 | IsOn__3C2DCFv | 53f99d95 | uchar | unproven | returns sltu of bit 5 of byte 0x15 (0/1); no word refs; only callers narrow |
| 0x2a7bf0 | ItemHasAmmo__5CZKitFi | 54ec3eaa | uchar | unproven | exits return 1 / 0; only callers narrow; no DWARF |
| 0x1d6f00 | OnIsMissionSuccessful__24@unnamed@zanim_menu_cpp@FP13C2DAnimCmdHdrPf | 56be50b3 | uchar | unproven | UICommandTable handler; returns (lbu m_state == 2) as a 0/1 compare, not the member; dispatcher narrowing only |
| 0x1d08f0 | UIIsTeamGame | 575adc71 | uchar | unproven | UICommandTable handler; j CZOnlineLobby::IsTeamGame 0x3254e0 (sltu only, live undefined); dispatcher narrowing only |
| 0x1d0ad0 | UINotOnCorrectClanTeam | 575adc71 | uchar | unproven | UICommandTable handler; sltu/xori 0/1; dispatcher narrowing only |
| 0x1d0b30 | UICanLadderPressDown | 575adc71 | uchar | unproven | UICommandTable handler; slt/xori 0/1; dispatcher narrowing only |
| 0x1d0b80 | UICanLadderPressUp | 575adc71 | uchar | unproven | UICommandTable handler; slti/xori 0/1; dispatcher narrowing only |
| 0x1d0cb0 | UIForceMediusStatusReport | 575adc71 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d0e40 | UIHasClanInvitations | 575adc71 | uchar | unproven | UICommandTable handler; j CZOnlineLobby::HasClanInvitations 0x32ad40 (sltu only); dispatcher narrowing only |
| 0x1d13f0 | UIClanHasInvitations | 575adc71 | uchar | unproven | UICommandTable handler; j CZOnlineLobby::ClanHasInvitations 0x323ac0 (sltu only); dispatcher narrowing only |
| 0x1d2020 | UINetCnfClose | 575adc71 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d2b50 | UIIsMemberOfClan | 575adc71 | uchar | unproven | UICommandTable handler; j CZOnlineLobby::IsMemberOfClan 0x322ae0 (sltu only); dispatcher narrowing only |
| 0x305c70 | IsOpen__7CFileIOCFv | 579ee969 | uchar | unproven | returns sltu/xori 0/1; IsOpen slot family (CBufferIO::IsOpen sltu, CMemCardIO::IsOpen xori) never narrows; only callers (incl. CMemCardIO::Open's own return andi at 0x306c14) narrow |
| 0x2858b0 | CSealCtrl::CanPlaceBomb | 5a39b194 | uchar | unproven | exits return li 1 / move zero; only callers narrow (the fifth returns it) |
| 0x25e7b0 | CSealCtrlAi::ComputeProjectileFireParams | 62e7e309 | uchar | unproven | exits return move zero / li 1; only callers narrow |
| 0x2bf820 | CZSealBody::GetFP | 62e7e309 | uchar | unproven | returns li 1 or GetFirepointPos 0x2c0140's result (0/1 constants, itself unproven); the caller only tests |
| 0x2bf8a0 | CZSealBody::GetAP | 62e7e309 | uchar | unproven | returns li 1 or GetFirepointPos 0x2c0140's result (unproven); only the caller narrows |
| 0x19c120 | CAiMaps::GetBoundary | 67724088 | uchar | unproven | returns the CAiCell::m_boundary bitfield (lbu; dsll32 27; dsrl32 30), live member type uint:2, unnarrowed, or constants/recursion; only the caller narrows |
| 0x19c8e0 | CAiMaps::GetLocation | 67724088 | uchar | unproven | exits return li 1 / move zero; only the caller GetStartMatrix narrows into its returned local |
| 0x1d5230 | UIDoesSlotHaveGame | 677aae36 | uchar | unproven | UICommandTable handler; returns CMemCard::Exists 0x306cf0 (0/1 only); dispatcher narrowing only |
| 0x23fd10 | _OutputASCII | 677aae36 | uchar | unproven | only exit returns li v0,1; _zrdr::Write narrows it as its own return (andi v0 at 0x23fd00): that proves Write, not this |
| 0x2a98a0 | CZKit::WillFireWeapon | 677aae36 | uchar | unproven | exits return li 1 / move zero; only callers narrow |
| 0x2e96d0 | ai::CheckLineOfFire | 6e9f1cc6 | uchar | unproven | exits return li 1 or s1 = 0 / daddiu s1,zero,1 (0x2e9810); only callers narrow |
| 0x2ec470 | CSnd::vagReadOffset | 6fb4a10f | uchar | unproven | returns 0 or s0 = sltu s0,zero,v0 (0x2ec4b0); only the caller narrows |
| 0x1d2df0 | UIMC_CreateIconFiles | 757d170c | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x2a8220 | CZKit::SetItem | 7891ee8b | uchar | unproven | exits return li 1 / move zero; only one caller narrows |
| 0x2c0140 | CZSealBody::GetFirepointPos | 7891ee8b | uchar | unproven | s0 is only 0 or daddiu s0,zero,1 (0x2c019c); only callers narrow, GetFP/GetAP return it |
| 0x298ad0 | CZSealBody::CanFire | 7916b44e | uchar | unproven | returns s1 (0 or 1 at the exit; the entry move s1,a0 is overwritten) or 13 move v0,zero exits; only the caller narrows |
| 0x2a8130 | CZKit::SetItemAmmo | 7916b44e | uchar | unproven | s0 is only 0 or daddiu s0,zero,1 (0x2a81f0); only the wrapper 0x2a80a0 narrows it (andi at 0x2a8110), which proves the wrapper |
| 0x2aec90 | CZKit::GetCurItemIDType | 79a2017d | uchar | unproven | returns li v0,254 or CZWeapon::GetIDType() 0x31e410 (unproven chain); only the caller narrows |
| 0x2af290 | CZKit::HasSniperRifle | 79a2017d | uchar | unproven | exits return li 1 / move zero; only the caller AttackTick narrows |
| 0x2bbc70 | get_state_fixup | 79a2017d | uchar | unproven | returns sealai::get_state's raw result (move s0,v0 at 0x2bbc8c; get_state 0x26c290 is live undefined, exits move v0,s1 / zero / callee) or li s0 constants; andi v0,s0,0xff at 0x2bbc90 only feeds bne, v0 at the exit is the unnarrowed s0 |
| 0x2e4480 | CSealCtrl::SetLookDirW | 79a2017d | uchar | unproven | s0 = slt / xori 1 (0x2e44b4/0x2e44b8): 0/1; only the caller narrows |
| 0x2e4600 | CSealCtrl::SetLookPosW | 79a2017d | uchar | unproven | s0 = slt / xori 1 (0x2e4618/0x2e461c): 0/1; only the caller narrows |
| 0x21d980 | GetIntersect__Q23zdb7CDIPolyFPQ23zdb11DiIntersect | 97e3ad52 | uchar | unproven | returns li 1 / zero; GetIntersect slot family (CDIDummy 0, CDIBBox 1/0) constants only, no DWARF; only slot call sites narrow |
| 0x2a01d0 | CZSealBody::PostCheckDILadder | 9a1f7e39 | uchar | unproven | returns li 1 or CZSealBody::CheckDILadder 0x29ff80's result (li 1 / move zero, live undefined); only the caller narrows |
| 0x1e1210 | CBlendOverlay::Tick | a39540ce | uchar | unproven | exits return li 1 / move zero; no word refs; only the caller narrows |
| 0x29d740 | CZSealBody::CalcGoalDir | a89b69de | uchar | unproven | exits return li 1 / move zero; callers narrow (CLook::SetLookDir andi s0 at 0x29d5b4, CalcAimGoal andi at 0x2bfe0c) |
| 0x1d2f60 | UIMC_Uninit | b197733d | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1853a0 | CAiMap::GetCellRepelParams | b1c7cc15 | uchar | unproven | s5 is 0 or daddiu s5,zero,1 (0x185a4c); only the wrapper CAiMaps::GetCellRepelParams narrows (andi at 0x185b2c, its own return) |
| 0x19a820 | CAiMap::GetBilinearAltitude | b1c7cc15 | uchar | unproven | s0 is 0 or daddiu s0,zero,1; only the caller narrows |
| 0x20a670 | IsJumpAndActionShared__13CCtrlrConfigsFv | b246f4cb | uchar | unproven | returns sltiu 0/1; the only caller stores sb (its byte destination) |
| 0x20a8d0 | IsInvalid__20CMissionObjectiveCamCFv | b246f4cb | uchar | unproven | returns sltu 0/1 or 0; only same-family siblings and inlined copies narrow, never this body |
| 0x20a930 | IsComplete__20CMissionObjectiveCamCFv | b246f4cb | uchar | unproven | returns sltu 0/1 or 0; only the caller AddObjective narrows (andi s0 at 0x3c233c) |
| 0x2ef610 | IsPlaying__12CSndInstanceFv | b9396927 | uchar | unproven | returns sltu of m_handle (0/1); the only narrowing caller is CTSound::Tick narrowing its own tick return (andi s3 at 0x2b67a8) |
| 0x2615e0 | GetRouteComplete__11CSealCtrlAiCFv | bb961ec9 | uchar | unproven | returns 0/1 constants; one caller narrows, others test; no DWARF |
| 0x1fa7c0 | ftsIsMapInVisibleList__FUiUi | bfd2ac76 | uchar | unproven | exits return 1 / 0; only the caller narrows; no DWARF |
| 0x1d2ee0 | UIMC_MkDir | c0fb9a80 | uchar | unproven | UICommandTable handler; returns CMemCard::mkdir 0x306ca0 (zero / sltiu only); dispatcher narrowing only |
| 0x1c3c10 | StateRunning__10CZAnimMainFi | c6ac02b3 | uchar | unproven | exits return li 1 / move zero; all eight callers narrow |
| 0x1d54e0 | UIUnInitNetwork | c75e636e | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x2b96a0 | get_param | c7e355d6 | uchar | unproven | returns constants 0..13 (li, movz); only the caller CTParam::Parse narrows |
| 0x1e0620 | CZBodyAnimBlend::IsDone | c80d9013 | uchar | unproven | exits return move zero / daddiu 1; no word refs; only the caller narrows |
| 0x1fe1b0 | IsAi__9CSealCtrlCFv | d5446266 | uchar | unproven | returns 0; slot 0x30 family constants only, no DWARF; only the slot call site narrows |
| 0x1fe1c0 | IsRemote__9CSealCtrlCFv | d5446266 | uchar | unproven | returns 0; slot 0x34 family (CRemoteCtrl::IsRemote li 1) constants only, no DWARF; only the slot call site narrows |
| 0x19c9b0 | CAiMaps::GetLocation | d68e2ddf | uchar | unproven | s0 is 0 or daddiu s0,zero,1 (0x19cdb0); callers narrow or sb into a byte local |
| 0x31e1c0 | GetIDType__8CZWeaponF10EQUIP_ITEM | d8f6732b | uchar | unproven | exits return constants 0..0xfe only; only callers narrow |
| 0x23f0d0 | _eval_defined | de7fe4af | uchar | unproven | s0 is 0 or daddiu s0,zero,1; only the caller _preproc_filter narrows |
| 0x23f2e0 | _get_pptoken | de7fe4af | uchar | unproven | exits return constants 0..4 (li, movz); only the caller narrows |
| 0x318f90 | HandleTimers__12CZProjectileFv | e7f659dd | uchar | unproven | exits return 0 / daddiu 1; only the caller PostTick narrows |
| 0x1d0e20 | UIStopAllSounds | ea5c5edd | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d6a50 | @unnamed@zanim_menu_cpp@::OnSetTtySpeedFactor | eb70620a | uchar | unproven | UICommandTable handler; only exit li v0,1; width only from zAnimUIMenuTick narrowing its own bool (andi at 0x1d027c/0x1d02cc, sb at 0x1d02f4) |
| 0x1d6b00 | @unnamed@zanim_menu_cpp@::OnSetCounterSpeedFactor | eb70620a | uchar | unproven | UICommandTable handler; only exit li v0,1; dispatcher narrowing only |
| 0x27d3e0 | CZSealBody::GetSpeedState | f0dcb486 | uchar | unproven | exits return li 0..3; only callers narrow |
| 0x2a6160 | CZKit::CanAddAmmo | f0dcb486 | uchar | unproven | exits return 1 / 0; only callers narrow |
| 0x1c34f0 | CZAnimMain::SequenceRunning | f6bdf5f8 | uchar | unproven | s0 is 0 or daddiu s0,zero,1 (0x1c359c); only the wrapper CZAnim::SequenceRunning narrows (its own return, andi at 0x1cd5f4) |
| 0x1c3600 | CZAnimMain::SequenceExists | f6bdf5f8 | uchar | unproven | s0 is 0 or daddiu s0,zero,1 (0x1c3664); only the wrapper CZAnim::SequenceExists narrows (andi at 0x1cd654) |
| 0x1d07e0 | UISysLoadIRX | f6bdf5f8 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d20e0 | UIAbortLoad | f6bdf5f8 | uchar | unproven | UICommandTable handler; move zero; dispatcher narrowing only |
| 0x1d2310 | UISetDefaultMenuScreen | f6bdf5f8 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d2570 | UIChangeCharacterType | f6bdf5f8 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d2ac0 | UIIsLeaderOfClan | f6bdf5f8 | uchar | unproven | UICommandTable handler; returns CZOnlineLobby::IsLeaderOfClan 0x3229e0 (sltiu only); dispatcher narrowing only |
| 0x1d2e60 | UIMC_ChSlot | f6bdf5f8 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d2ea0 | UIMC_ChPort | f6bdf5f8 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d37c0 | UISwitchProgressiveVideo | f6bdf5f8 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d38a0 | UICheckVideoMode | f6bdf5f8 | uchar | unproven | UICommandTable handler; li 1 / sltiu; dispatcher narrowing only |
| 0x1d3970 | UIDisableButton | f6bdf5f8 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x1d3a70 | UIEnableButton | f6bdf5f8 | uchar | unproven | UICommandTable handler; li 1; dispatcher narrowing only |
| 0x264270 | CSealCtrl::SlideTick | 15983d99 | uchar | proven (var) | SlideTick slot family: override CSealCtrlAi::SlideTick returns andi s0,v0,0xff (0x264670) of this base's result; the base's own exits are only 0/1 |
| 0x29dd20 | CZSealBody::SetLookDir | 1598914b | uchar | proven (var) | returns 0 or CLook::SetLookDir 0x29d3c0's result; CLook::SetLookDir returns s0 = 0/1 or andi s0,v0,0xff (0x29d5b4); live CLook::SetLookDir is undefined |
| 0x283090 | CSealCtrl::AllowCommandHOLDPOS | de7fe4af | uchar | proven (var) | returned s0 is narrowed in the body (andi s0,v0,0xff at 0x283184, 0x283204, 0x28320c, 0x283228, 0x283244), but on paths that reach the exit it is 0 or daddiu 1 |
| 0x264640 | CSealCtrlAi::SlideTick | e75bba13 | uchar | proven (var) | returns andi s0,v0,0xff (0x264670) of the base's result through move v0,s0 (0x264684): narrowing in the callee |
| 0x1d2120 | UITestUIVar | f6bdf5f8 | uchar | proven (var) | UICommandTable handler; returned s0 is narrowed in the body (andi s0,v0,0xff at 0x1d2210, 0x1d2230, 0x1d223c) or sltu 0/1 |
| 0x1d5300 | UIIsMemCardInserted | 06f0b3d1 | uchar | proven | UICommandTable handler; j CMemCard::IsInserted 0x3073a0, whose exit narrows (andi v0,v0,0xff at 0x307414 before jr ra 0x307444) |
| 0x305880 | CFileIO::Open | 3a6a6699 | uchar | proven | Open slot family (CFileIO/CBufferIO/CMemCardIO, recon void): override CMemCardIO::Open 0x306ad0 narrows its own exit (andi v0,v0,0xff at 0x306c14, jr ra 0x306c2c) |
| 0x1d9ec0 | DoMemAlign__Q23zar4CZARFv | 56be50b3 | uchar | proven | only exit returns lbu v0 of the 1-byte static m_memalign__Q23zar4CZAR (0x1d9ec4): the returned member's width (the evidence cites only the caller) |
| 0x2639e0 | CanAttack__11CSealCtrlAiFP7CEntity | bb961ec9 | uchar | proven | callee narrows at an exit: andi v0,v0,0xff at 0x263a00 before jr ra 0x263a28 (the evidence cites only the caller) |

## Notes and contradictions
- Callers of the DWARF-uchar functions test v0 directly (beq/bne or sb): none re-narrows. Metrowerks does re-narrow indirect results (CZAnimMain::CmdTick andi s0,v0,0xff after the bool tick callback at 0x1c494c). Caller andi is therefore the destination width and is not return evidence.
- 0x2d1f00 CSealUnit::GetUnitLeaderHandle: the live uchar is contradicted. It returns lb s1,644(v0) unnarrowed, and a uchar return would need andi 0xff before jr ra. The returned member is a signed byte, or the return is int.
- 0x19c120 CAiMaps::GetBoundary returns CAiCell::m_boundary, whose live member type is uint:2, not a uchar member.
- UICommandTable (0x439540, 1776 bytes) and zAnimUIMenuTick (0x1d0140) have no DWARF. Some handlers called through the same jalr column narrow their own return: UINetCnfUninit 0x1d20a0 (andi at 0x1d20b4), UIIsMemCardInserted 0x1d5300 by its tail callee, and the lbu returners UIHaveBeenBannedFromGame, UIMediusEnabled and UIIsNetwork. These would fix the column type only if a data-table column family rule were adopted (no such rule exists). That rule would flip the 57 unproven handler rows.
- Slot families are used as override return identity: CFileIO::Open is proven by CMemCardIO::Open narrowing at 0x306c14. The SlideTick pair (0x264270/0x264640) rests only on the andi at 0x264670.
- Out-of-scope rows with the same weaker "returned variable narrowed" basis (their evidence cites it): zrdr_tobool 0x23d570, zrdr_findSTRING 0x23d300, zrdr_findbool 0x23d030 (by chain), CVehicleRdrEntry::GetStartMatrix 0x1a2bd0, CSealCtrlAi::SetHoldFire 0x260db0, CSealCtrl::AllowCommandFOLLOW 0x283350, CAiMap::TransformTo 0x185b50, CAiMap::GetSoilByName 0x1871d0, CAiTarget::UpdateTarget 0x2ea020.
- Out of scope and also without width proof: zdb::IntersectStruct::IsInside 0x21c2c0 (sltu of a 1-bit field). Its evidence cites a bool conversion, not callers.
