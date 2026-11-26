# Stage 2: six small modules, batch 2 (2026-11-26)

One note for six one-list modules: `gamez/zTwoD`, `gamez/zUtil`, `gamez/zTexture`, `gamez/zGrid`,
`gamez/zCamera` and `Apps/FTS/game` (each list a, made with `compare.py --lists <module> --split 1`
and `--sheet <module> --list a`). Together they hold 40 uncertain rows, 79 sampled deviating rows
and 384 exact rows that were not checked one by one. Pairing produced by `socom-release-compare-c1`
(`python tools/release/compare.py`); checked by `socom-release-check-small-2`, who did not write the
tool, at HEAD f9354c10. Both images were decoded with the release tools. Callers were found by
scanning both images for `jal`/`j`, `lui`/`addiu` address loads, `$gp` accesses, vtable slots and data
words. Virtual callers were found by scanning for `lw vt,<vptr>(obj); lw f,<slot>(vt); jalr f`.
Ghidra was not needed.

The cross-check, the same for every module: all 566 paired rows of the six modules' owner files had
their callers, address loaders, vtable slots and data-word counts compared with the prototype's
through the map. Their own ordered calls and pointer loads were compared for substitutions. The
ordered calls of every paired caller of a function in these files were compared too (1723 callers).
Every vtable with a slot in the files was aligned slot by slot. Every paired row with a byte twin on
either side was scored by the callers it shares with its counterpart (105 rows, none beaten). Byte
twins called from paired callers were checked call by call (338 callers, none crossed).

What settled rows, in the order it was used: the call site in a paired caller (PlayRemoteMsg,
zAnimMessageTick, CGrid::AddClutter, StopEngine, main, CPipe::CAlpha::Add); the arguments passed
through; vtable slots and the virtual call sites; the gp statics shared with paired functions;
strings.

Slots below count from the first function word of a table (slot 0 is at +0x08).

## gamez/zTwoD

List a: ztwod_messageq.cpp, ztwod_font.cpp, c2dbitmap_poly.cpp, c2dline.cpp, c2dstring.cpp,
ztwod_bitmap.cpp, ztwod_init.cpp, ztwod_main.cpp and ztwod_poly.cpp (release 0x201f60-0x203770 and
0x314110-0x31ac00). 8 uncertain rows (5 new, 1 removed, 1 weak pair (`slot-only`), 1 deviating
flagged `caller-mismatch`), 15 sampled deviating rows out of 45, 89 exact rows.

### Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x201f90 | - | new, owner guess | confirmed | walks the message queue's list and writes four floats from a1 into +0x54..+0x60 of each message string (its colour). Caller CHUD::Tick (three times) |
| 0x202810 | 0x200130 `Add_Message__12C2DMessage_QFPCciii` | deviating, position, caller-mismatch | corrected to new | the general overload: the prototype (PCciii) body, with three more arguments (an int in t1, a bool in t2, a float in f12). Its only callers are the four wrappers 0x202c50, 0x202c70, 0x202ca0 and 0x202ce0 |
| 0x202c50 | - | new, owner guess | corrected to 0x200130 `Add_Message__12C2DMessage_QFPCciii` | the (PCciii) signature: it passes a2, a3 and t0 through to 0x202810 and fills the rest from members (+0x140, +0x120, bool 0). PlayRemoteMsg's two prototype calls of 0x200130 call it at the same places. OnDeath's message code, now in new 0x254020 (zSeal), calls it where the prototype OnDeath called 0x200130 |
| 0x202c70 | 0x2004b0 `Add_Message__12C2DMessage_QFPCci` | deviating (weak), slot-only | confirmed | 7 of the prototype's 8 other callers (VoterPacketHandler, PickupAmmo, PickupMPBomb, HandleFireWeapon, PlayRemoteMsg, PlaySound3D, PlaySoundVolPanPitch). zAnimMessageTick moved to 0x202ca0. Its body is now a forwarder to 0x202810 (its int goes to t1), hence similarity 0.009 |
| 0x202ca0 | - | new, owner guess | confirmed | a new overload (text, bool, float duration; the duration defaults to +0x120 when <= 0). zAnimMessageTick calls it where the prototype called the (PCci) one |
| 0x202ce0 | - | new, owner guess | confirmed | a new overload (text, three ints, bool, float). zAnimMessageTick calls it where the prototype called the (PCciii) one |
| - | 0x2fe9a0 `SetXSpacing__7C2DFontFf` | removed | confirmed | its only caller CHUD::Init dropped the call; the loop is not inlined there |
| 0x316940 | - | new, owner guess | confirmed | an MSL `vector<C2DFontEntry>::reserve` instance (40-byte elements, "vector::reserve length error", copy constructor, swap, clear). C2DFont::Load now reserves; the prototype Load had no such call |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x2023f0 | 0x1ffd20 `Tick__12C2DMessage_QFf` | yes | C2DMessage_Q slot 7 → 8 (the C2D shift) |
| 0x202f00 | 0x200a10 `__dt__12C2DMessage_QFv` | yes | slot 0 of the C2DMessage_Q table; same caller ~CMission |
| 0x2035a0 | 0x2010b0 `SetString__16C2DMessageStringFPCc` | yes | C2DMessageString slot 21 → 22 |
| 0x203620 | 0x201130 `Tick__16C2DMessageStringFf` | yes | C2DMessageString slot 7 → 8 |
| 0x3142f0 | 0x2fd370 `SetSegments__15C2DWidePolylineFP6CPtItrf` | yes | same caller CZLineMap::TickLine |
| 0x3151a0 | 0x2fe250 `SetUseFrameBufferAlpha__13C2DBitmapPolyFb` | yes | C2DBitmapPoly slot 15 → 16 |
| 0x316130 | 0x2ff260 `GetEntry__7C2DFontFc` | yes | the same three C2DString callers |
| 0x3184d0 | 0x301510 `Load__7C2DPolyFffffffPQ23zdb8CTexture` | yes | the same two callers |
| 0x318630 | 0x3016d0 `__ct__7C2DPolyFv` | yes | the same three callers |
| 0x318f80 | 0x302020 `UpdatePos__9C2DStringFv` | yes | 25 shared callers |
| 0x319110 | 0x302180 `AddCharacter__9C2DStringFc` | yes | 4 shared callers |
| 0x319550 | 0x3025a0 `Format__9C2DStringFPCce` | yes | slot 22 → 23 of the C2DString family tables |
| 0x319c50 | 0x302c50 `Draw__9C2DStringFPQ23zdb16CTextureRelocMgrPQ23zdb7CCameraf` | yes | 10 shared callers |
| 0x31a5e0 | 0x3035d0 `Load__9C2DBitmapFffffPQ23zdb10CTexHandle` | yes | 75 shared callers |
| 0x31a960 | 0x3039c0 `__ct__9C2DBitmapFv` | yes | 27 shared callers |

### The new C2D virtual and C2DVisual (hand-over from the zUI check)

- C2D's new slot 6 (+0x20 in every C2D table; the base is the empty 0x173940, in the orders.cpp run
  of C2D inline defaults) is a node setter. It is called right after `CNode::Create`, with the new
  node: by Add2dNode, by CGameMenu::LoadFromDesign (four times) and by PrepSkbsForDisplay (on the
  node Add2dNode returns). The prototype Add2dNode made no such call. The two overrides store the
  node: CUIMapCtrl (0x3b1760) at +0x210, CBmpWithNode (0x3c3390) at +0xa0. Proposed name (guess):
  `SetNode__3C2DFPQ23zdb5CNode`.
- C2DVisual's table lost the slot `Write__Q23zdb7CVisualFRQ23zar4CZAR`: 7 slots → 6, Get2DVisual
  moves from slot 6 to 5. Confirmed.

### New and removed

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x201f90 | sets the colour of every message string in the queue | guess: `SetColor__12C2DMessage_QFRC6CPnt4D` |
| 0x202810 | the general Add_Message | guess: `Add_Message__12C2DMessage_QFPCciiiibf` (the float's position in the list is not known) |
| 0x202ca0 | Add_Message(text, bool, duration) | guess: `Add_Message__12C2DMessage_QFPCcbf` |
| 0x202ce0 | Add_Message(text, three ints, bool, duration) | guess: `Add_Message__12C2DMessage_QFPCciiibf` |
| 0x316940 | `vector<C2DFontEntry>::reserve` | the MSL instance (string, element size); the exact mangled name is not known |

Removed: C2DFont::SetXSpacing (CHUD::Init no longer calls it).

### Still unsure

None. The Add_Message reading is a judgement. The other reading keeps 0x202810 as the prototype
(PCciii) function and makes 0x202c50 new. The signature, the arguments passed through and the call
sites favour the reading above. With the other reading, the prototype's name would go to a function
of seven arguments.

## gamez/zUtil

List a: util_output.cpp, util_memcard.cpp, util_sonyio.cpp, util_bufio.cpp and util_stable.cpp
(release 0x31ac30-0x31ea90). 7 uncertain rows (3 removed, 2 new, 1 weak pair (`role-only`), 1 exact
flagged `caller-mismatch`), 15 sampled deviating rows out of 20, 62 exact rows.

### Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x304320 `__dt__7COutputFv` | removed | confirmed | its only caller zUtilUninit is now empty |
| - | 0x304510 `zUtilInit__FPCc` | removed | confirmed | release main no longer calls it (between DumpLog and StartEngine) |
| 0x31b390 | 0x3044e0 `zUtilUninit__Fv` | deviating (weak), role-only | confirmed | the same call position in StopEngine (after zVid_Uninit, before DestroyPool). The body is now `jr ra; nop` |
| - | 0x3043a0 `__ct__7COutputFPCcb` | removed | confirmed | its only caller zUtilInit is gone |
| 0x31be60 | 0x305010 `BuildTOC__7CFileCDFv` | exact, caller-mismatch | confirmed | the only copy. zSysInit's call after RebootIOP moved into CIOPManager::RebootIOP |
| 0x31e370 | - | new, owner guess | confirmed | a CMemCard method (this, bool): polls the card on the port at +0x24 (sceMcSync or sceMcGetInfo), flips a card global, runs an event anim on error. Callers Init (four times), 0x31e880 (four times), zAnim handler 0x1d36b0 (with 1) |
| 0x31e880 | - | new, owner guess | confirmed | Init's body run again with m_initcount set to 0, then restored. Caller: the zMenuState IOPRebootHandler |

Sampled deviating rows: all 15 are the same function on both sides. CMemCardIO fflush, fwrite,
fread, ftell and Close keep their slots 11, 9, 7, 5 and 1. chdir, Exists, CreateIconFiles,
GetFreeSpace, Format, IsInserted, LoadConfig, SaveGame, Uninit and Init have the same UI callers,
1 to 4 each. Uninit and Init are also called by CGameMenu::LoadFromDesign now.

Hand-over: `GetSize__7CFileIOCFv` (0x31ac40) holds. It is slot 3 of the CFileIO and CBufferIO tables
and sits between util_bufio.cpp's GetMode and CBufferIO::fwrite. ai_log.cpp, which emitted the
prototype copy, is gone. Its owner is util_bufio.cpp; the settled row is already in the zAI note.

### New and removed

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x31e370 | polls the memory card's state | guess: `CheckCard__8CMemCardFb` |
| 0x31e880 | re-initialises the card modules after an IOP reboot | guess: `ReInit__8CMemCardFv` |

Removed: zUtilInit and COutput's constructor and destructor; COutput::DumpLog stays.

### Still unsure

None.

## gamez/zTexture

List a: ztex_manager.cpp, ztex_dyn.cpp, ztex_handle.cpp, ztex_main.cpp, ztex_palette.cpp and
ztex_read.cpp (release 0x30fc70-0x3140a0 and 0x21b190). 7 uncertain rows (2 unsure, 2 new, 3
removed), all 4 deviating rows sampled, 57 exact rows.

### Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x3110b0 | 0x2f9d00 `MIPUpdateTextureSelects__Q23zdb8CTextureFUiUi` | unsure, position, low-similarity | confirmed (deviating) | the same updates of the TBP fields at +0x54 and +0x58, now through one 64-bit stack copy. UpdateTextureSelects reaches it through new 0x3112a0 |
| 0x3112a0 | - | new, owner guess | confirmed | the per-texture block of the prototype UpdateTextureSelects, moved out: sets the texture's TBP (+0x50), calls MIPUpdateTextureSelects for each mip (+0x64, count +0x60), sets the palette CBP (+0x1c), returns the next address (+0x2e). Caller UpdateTextureSelects |
| 0x3129b0 | - | new, owner guess | confirmed | a CGSTexBuffer method: clears the vector at +0x1c and inserts up to n. LoadWorld calls it twice (new code there) |
| - | 0x2fbb90 `RelocateAll__Q23zdb12CGSTexBufferFv` | removed | confirmed | EndBatchReloc (52 bytes now) only calls Load. UpdateTextureSelects' first loop has RelocateAll's "store only if changed" test now |
| - | 0x2fcb90 `resize__Q23std38__vector_imp<1,Q23std12allocator<1>,0>FUiRC1` | removed | confirmed | inlined: Load calls insert where it called resize; EndBatchReloc no longer has the inline Load copy |
| - | 0x2fcc00 `erase__Q23std38__vector_imp<1,Q23std12allocator<1>,0>FP1P1` | removed | confirmed | its only caller was resize |
| 0x313ef0 | 0x2fccd0 `insert__Q23std38__vector_imp<1,Q23std12allocator<1>,0>FP1UiRC1` | unsure, position, low-similarity | confirmed (deviating) | the only insert of this vector on both sides: the same calls (fprintf/abort, new, the same swap and first, delete) and strings; 1076 → 416 bytes. Callers Load and 0x3129b0 |

Sampled deviating rows: 4 of 4 are the same function. EndBatchReloc is slot 1 of the CBatchRelocator
table. UpdateTextureSelects has the callers InterruptFromVIF1 and Load. DestroyBuffers has the
callers auxUnload and UnInit. Load has the same six callers, plus EndBatchReloc.

### New and removed

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x3112a0 | updates one texture's GS addresses and returns the next | guess: `UpdateTextureSelects__Q23zdb8CTextureFUiUi` |
| 0x3129b0 | sizes the buffer's chain vector | guess: `ReserveChain__Q23zdb12CGSTexBufferFUi` |

Removed: CGSTexBuffer::RelocateAll; vector_imp<1>::resize and ::erase.

### Still unsure

None.

## gamez/zGrid

List a: grid_cell.cpp, grid_di.cpp, grid_main.cpp and grid_clutter.cpp (release 0x214c10-0x21cff0).
6 uncertain rows (3 new, 1 removed, 1 weak pair (`slot-only`), 1 weak pair (`role-only`)), 15
sampled deviating rows out of 27, 45 exact rows.

### Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x217090 | - | new, copy, owner guess | confirmed | `CPnt3D::operator-` by value. It has the bytes of `__pl__6CPnt3DCFRC6CPnt3D` (0x293390), with Sub in place of Add. The prototype declared it but never defined it. NodeGetIntersectBatch calls it where the prototype called Sub |
| 0x218e00 | - | new, owner guess | confirmed | a CGrid method: the cell under (x, z), with clamped indices into the cell table (+0x30); NULL unless the node's type is 10. Caller: new CWorld light-level 0x231930 |
| - | 0x2170e0 `AddClutter__Q23zdb5CCellFPQ23zdb8CClutter` | removed | corrected to 0x21acd0 | see the row below |
| 0x21ac90 | 0x2170d0 `RenderClutter__Q23zdb5CCellFPQ23zdb5CCell` | deviating (weak), slot-only | confirmed | same caller CPipe::RenderWorld; renders two clutter lists (+204, +224) where the prototype tail-called Render on one |
| 0x21acd0 | - | new, owner guess | corrected to 0x2170e0 `AddClutter__Q23zdb5CCellFPQ23zdb8CClutter` | the same call site in CGrid::AddClutter. It adds the clutter to one of the two lists by a flag of the clutter's node (+0x64, +0x5d bit 4), calling SetDescendantDI first. The prototype tail-called CClutterList::Add on +204 |
| 0x21ad50 | 0x2170f0 `DeleteClutter__Q23zdb5CCellFv` | deviating (weak), role-only | confirmed | same caller CGrid::DeleteClutter; frees both lists |

Sampled deviating rows: all 15 are the same function on both sides. Each has the same callers, 1 to 6
of them. GetIntersect and GetAltitude are also called by the new CWorld bool overloads 0x232050 and
0x231f00. ~CCell is slot 0 of the CCell table.

### New and removed

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x217090 | CPnt3D subtraction by value | `__mi__6CPnt3DCFRC6CPnt3D` (the bytes of `__pl__` with Sub) |
| 0x218e00 | the grid cell under a point | guess: `GetCell__Q23zdb5CGridFff` |

Removed: none (CCell::AddClutter is 0x21acd0).

Layout, plainly shown by settled rows: CCell has a second clutter list at +224 next to the one at
+204.

### Still unsure

None.

## gamez/zCamera

List a: fov.cpp, zcam_main.cpp, camera.cpp and zcam_update.cpp (release 0x1e5980-0x1ede60).
6 uncertain rows (2 removed, 4 new, two of them without an owner), 15 sampled deviating rows out of
34, 42 exact rows.

### Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x1e45f0 `__cl__7CMatrixCFUiUi` | removed | confirmed | inlined: no release copy of its five instructions; TestLandmarkFOG and its other callers no longer call it |
| - | 0x1e4820 `GetScaledZSquared__Q23zdb7CCameraFP6CPnt3D` | removed | confirmed | its only caller CPipe::CAlpha::Add calls GetScaledRangeSquared (exact pair) at that place |
| 0x1e9370 | - | new, owner guess | confirmed | called by the CCamera constructor. It copies the eight floats at +0x4d0 (the fog-altitude planes) into two new blocks at +0x510 and +0x530. Unless bit 7 of +0x14f is set, it then writes -10000.0, 0.001 and the values at +0x130/+0x134 into them |
| 0x1e9e40 | - | new, no owner | confirmed; owner camera.cpp | stops and releases the playing heartbeat sound instance (gp static); caller CMission::ReOpen_Unload1 |
| 0x1e9e80 | - | new, no owner | confirmed; owner camera.cpp | looks up SND_HEARTBEAT_SLOW_LOOP, _MEDIUM_LOOP and _FAST_LOOP into three gp statics, then stops any playing instance. Callers CMission::Open and ReOpen_Load. CAppCamera::UpdateDeathCamState is the only other user of these four statics (it now has three Stop/ReleaseSoundInstance pairs on them). They sit next to camera.cpp's other statics, and the two functions just before camera.cpp's first function |
| 0x1ebc30 | - | new, owner guess | confirmed | a CAppCamera method. From the ground under the camera node (GetAltitude, not on a seal) it sets the camera's CanSeeRegions, AboveMaterial (+0x2b0) and IsInside (+0x2ac). Caller CZHudMissionCams::HudTick (new call) |

Sampled deviating rows: all 15 are the same function on both sides, each with the same callers (1 to
4). GetLandmarkFarPlane is also called by CMenuState::Init; the CCamera constructor now calls
0x1e9370.

### New and removed

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x1e9370 | initialises the camera's two new fog-altitude blocks | guess: `InitFogAlt__Q23zdb7CCameraFv` |
| 0x1e9e40 | stops the heartbeat loop | guess: `StopHeartbeat__Fv` (camera.cpp static) |
| 0x1e9e80 | loads the heartbeat sounds | guess: `LoadHeartbeatSounds__Fv` (camera.cpp static) |
| 0x1ebc30 | updates the camera's region, material and inside flag from the ground | guess: `UpdateRegions__10CAppCameraFv` |

Removed: CMatrix::operator()(row, col) (inlined) and CCamera::GetScaledZSquared (its caller uses
GetScaledRangeSquared).

Layout, plainly shown by a confirmed row: CCamera grew past the prototype's 0x520 bytes (writes up to
+0x54c).

### Still unsure

None. The owner of 0x1e9e40 and 0x1e9e80 (camera.cpp) rests on the shared statics and the position.

## Apps/FTS/game

List a: headset.cpp, orders.cpp, reco.cpp, beachball.cpp, database.cpp and thezoom.cpp (release
0x1720f0-0x17bd90, 0x1effc0, 0x309b20-0x30ac30, 0x31cc90, 0x33a870-0x33b1e0, 0x3523f0-0x353520).
6 uncertain rows (4 new, 2 weak pairs (`slot-only`)), 15 sampled deviating rows out of 44, 89 exact
rows.

### Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x173940 | - | new, copy, owner guess | confirmed | the base of the new C2D slot 6 (`jr ra; nop`; see zTwoD). It is slot 6 of every C2D-family table (51 tables), which tells it from its byte twins. It sits in orders.cpp's run of C2D inline defaults |
| 0x176a20 | 0x1777c0 `Load__10OrdersMenuFffff` | deviating (weak), slot-only | confirmed | same caller CHUD::Init; stores the four arguments, as ints, at +0x68..+0x74 (inline conversion instead of fptosi calls) |
| 0x309c50 | - | new, owner guess | confirmed | a Headset method: clears a new byte at +0xb and sets m_stop if the current line is playing. Caller CZSealBody::OnDeath |
| 0x30aa90 | - | new, owner guess | confirmed | a Headset method: starts the headset audio stream (snd_DoExternCall, 11025 Hz) or marks it unavailable, then sets the state to idle. Caller CSnd::Open |
| 0x30ab10 | - | new, owner guess | confirmed | looks for a 16-bit 11025 Hz USB audio device (lgAudEnumerate, which only openmic called in the prototype). Callers ftsGetHeadset (before it creates the headset) and DisconnectedTick |
| 0x3534c0 | 0x336d90 `recoInit__Fv` | deviating (weak), slot-only | confirmed | same caller CLoadState::Init. It returns 1 as before, but sets recoShouldInit from ftsGetHeadset() instead of clearing it |

Sampled deviating rows: all 15 are the same function on both sides. GetAssetLibs, Tick, SetTrans
and GetPosW keep their slots, shifted where the C2D shift applies; GetPosW is slot 1 of the CEntity
and CZSealBody tables. ScrollBack, HandleRecoCmd, SetupTuples, the six Headset functions, Tick of
CameraZoom and recoGrabMemory have the same callers, 1 to 4 each. StopSound is also called by
CZAnim::StopSounds, DeQueue by new 0x309a60.

Found by the cross-check, outside the list's rows:

| release | map | finding |
|---|---|---|
| 0x1effc0 | `GetPosW__7CEntityCFv` (0x177290), owner orders.cpp | pair right, owner wrong: the release copy sits inside ent_main.cpp's run (between TeleportTo and OnMissionEnd); the prototype emitted it in orders.cpp |

Hand-over, options.cpp (src/Apps/FTS/options.cpp, outside these six modules): process_arguments is
not removed. Release 0x1735e0 (new, no owner, 204 bytes) is it. It sits right after getopt, as in the
prototype. main calls it at the same place (after mwInit), and it is getopt's only release caller.
What is left of the switches: the option string is "m:". The one option, `-m <name>`, copies its
argument into a 64-byte global. All the long options (`--AP`, `--ammo`, `--nosounds`, `--ailog`,
`--nomenu`, `--two_player`, `--medius`, `--nodi` and the rest) are gone, and so are the short
switches of "d:p:m:V:hfFaAszZR" other than m. SetDatabase, SetRootPath, atoi and printf are no
longer called. It still sets four flags to 1 on entry and calls `SetAiEnabled(flag, 1)` after the
loop. The earlier notes (state, zFTS, zSeal-d) gave "process_arguments is removed" as the basis for
removing SetSkipMenu, ftsSetPlayerCount, ftsSetSquirm and SetAiLogEnabled. Those verdicts hold,
because the 204-byte version calls none of them.

### New and removed

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x173940 | C2D's new virtual, empty base | guess: `SetNode__3C2DFPQ23zdb5CNode` (callers pass the node just created) |
| 0x309c50 | stops the current headset line | guess: `StopCurrent__7HeadsetFv` |
| 0x30aa90 | opens the headset audio stream | guess: `OpenStream__7HeadsetFv` |
| 0x30ab10 | finds a USB headset device | guess: `FindDevice__7Headset...` (three arguments, types not known) |

Not new, though the map has it as new: 0x1735e0 (`process_arguments__FiPPc`).

Layout, plainly shown by a confirmed row: Headset has a byte at +0xb.

### Still unsure

None.

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x202c50 | 0x200130 | the (PCciii) signature, passing its three ints through to 0x202810; PlayRemoteMsg's two call sites and OnDeath's (now in 0x254020) | socom-release-check-small-2 | 2026-11-26 | | |
| 0x202810 | new | the general Add_Message (the prototype (PCciii) body plus an int, a bool and a float); called only by the four overload wrappers | socom-release-check-small-2 | 2026-11-26 | src/gamez/zTwoD/ztwod_messageq.cpp | |
| 0x202c70 | 0x2004b0 | 7 of its 8 other prototype callers; zAnimMessageTick moved to 0x202ca0; body now a forwarder to 0x202810 | socom-release-check-small-2 | 2026-11-26 | | |
| 0x31b390 | 0x3044e0 | the same call position in StopEngine (after zVid_Uninit); body now empty | socom-release-check-small-2 | 2026-11-26 | | |
| 0x3110b0 | 0x2f9d00 | the same TBP updates at +0x54/+0x58; reached from UpdateTextureSelects through new 0x3112a0 | socom-release-check-small-2 | 2026-11-26 | | |
| 0x313ef0 | 0x2fccd0 | the only vector_imp<1>::insert on both sides: same calls and strings; its caller resize is inlined into Load | socom-release-check-small-2 | 2026-11-26 | | |
| 0x21acd0 | 0x2170e0 | the same call site in CGrid::AddClutter; adds to one of the cell's two clutter lists | socom-release-check-small-2 | 2026-11-26 | | |
| 0x21ac90 | 0x2170d0 | same caller CPipe::RenderWorld; renders both clutter lists | socom-release-check-small-2 | 2026-11-26 | | |
| 0x21ad50 | 0x2170f0 | same caller CGrid::DeleteClutter; frees both clutter lists | socom-release-check-small-2 | 2026-11-26 | | |
| 0x1e9e40 | new | stops the heartbeat instance; its gp statics are camera.cpp's (shared with UpdateDeathCamState) | socom-release-check-small-2 | 2026-11-26 | src/gamez/zCamera/camera.cpp | |
| 0x1e9e80 | new | loads the three SND_HEARTBEAT loops into camera.cpp's gp statics | socom-release-check-small-2 | 2026-11-26 | src/gamez/zCamera/camera.cpp | |
| 0x176a20 | 0x1777c0 | same caller CHUD::Init; the same four stores at +0x68..+0x74 | socom-release-check-small-2 | 2026-11-26 | | |
| 0x3534c0 | 0x336d90 | same caller CLoadState::Init; same return, before the same neighbour | socom-release-check-small-2 | 2026-11-26 | | |
| 0x1effc0 | 0x177290 | owner: the release copy of GetPosW__7CEntityCFv sits inside ent_main.cpp's run | socom-release-check-small-2 | 2026-11-26 | src/gamez/zEntity/ent_main.cpp | |
| 0x1735e0 | 0x173e30 | process_arguments: main's call at the same place; getopt's only caller; right after getopt as in the prototype; option string "m:" | socom-release-check-small-2 | 2026-11-26 | src/Apps/FTS/options.cpp | |

Rows that change together: 0x202810 and 0x202c50 (the counterpart moves from the first to the
second); 0x21acd0 and the removed 0x2170e0 (one row once paired); 0x1735e0 and the removed 0x173e30
(one row once paired).

## How the tool did

| module | class | rows | right | wrong |
|---|---|---|---|---|
| zTwoD | new | 5 | 4 | 1: 0x202c50 is Add_Message(PCciii) |
| zTwoD | deviating, position, caller-mismatch | 1 | 0 | 1: 0x202810 is new |
| zTwoD | deviating (weak), slot-only | 1 | 1 | 0 |
| zTwoD | removed | 1 | 1 | 0 |
| zUtil | removed | 3 | 3 | 0 |
| zUtil | new | 2 | 2 | 0 |
| zUtil | deviating (weak), role-only | 1 | 1 | 0 |
| zUtil | exact, caller-mismatch | 1 | 1 | 0 |
| zTexture | unsure | 2 | 2 (the candidates were right) | 0 |
| zTexture | new | 2 | 2 | 0 |
| zTexture | removed | 3 | 3 | 0 |
| zGrid | new | 3 | 2 | 1: 0x21acd0 is CCell::AddClutter |
| zGrid | removed | 1 | 0 | 1: CCell::AddClutter is 0x21acd0 |
| zGrid | deviating (weak), slot-only / role-only | 2 | 2 | 0 |
| zCamera | removed | 2 | 2 | 0 |
| zCamera | new | 4 | 4 (two without an owner: camera.cpp) | 0 |
| Apps/FTS/game | new | 4 | 4 | 0 |
| Apps/FTS/game | deviating (weak), slot-only | 2 | 2 | 0 |

The sample: 79 of 79 deviating rows are the same function on both sides (zTwoD 15, zUtil 15,
zTexture 4, zGrid 15, zCamera 15, Apps/FTS/game 15).

The cross-check: 566 paired rows compared: zTwoD 135, zUtil 83, zTexture 63, zGrid 74, zCamera 76,
Apps/FTS/game 135. Also compared: the ordered calls of 1723 paired callers, the vtables with a slot
in the files (zTwoD 53, Apps/FTS/game 54, zCamera 11, the rest 1 to 3), 105 rows with byte twins and
338 callers of byte twins. Differences looked at:

- Rows: 135 (zTwoD 56, of which 25 are only the C2D slot shift; Apps/FTS/game 46, 10 of them the
  shift; zUtil 12, zCamera 9, zTexture 7, zGrid 5).
- Caller call sequences: 149.
- Functions with call-order substitutions: 6 (Add_Message(PCci): new → its call of 0x202810;
  SetString: strcasecmp → strcmp; NodeGetIntersectBatch: Sub → operator-; CGrid::Create: malloc →
  calloc; theta_x_z: fabs/fptodp → fabsf; EndBatchReloc: its inline Load copy → a call of Load).

They are callers added, moved or inlined. The Add_Message overloads, the split per-texture update,
BuildTOC moving into RebootIOP and the C2D node setter calls are among them. So are the zArchive
containers changed from lists to vectors (which moves calls between the byte-identical
list_deleter/compressed_pair template copies in orders.cpp), the slot shift and the removed _Write
and UpdateUIVar thunk slots already noted for zNode and zUI.

Pairs wrong: 0 outside the list rows counted above; 1 owner wrong (0x1effc0 GetPosW, ent_main.cpp).
Also the GetSize owner, already in the zAI note. Outside the six modules: process_arguments
(0x1735e0) is paired by this check.

What misled it:

- Add_Message: the release moved the (PCciii) body into a longer new overload and left the old
  signature as a 32-byte forwarder. The tool paired the body by position (0.558) and left the
  forwarder, which has the old callers and passes the old arguments through, as new.
- CCell::AddClutter: an 8-byte tail call became a 124-byte chooser between two lists, so similarity
  was nil; the call site in CGrid::AddClutter decides. Its neighbours RenderClutter and DeleteClutter
  were paired only by slot and role for the same reason.
- process_arguments: shrank from 2472 to 204 bytes; the call site in main and the getopt call
  decide.

What cost the most time: deciding which Add_Message carries the prototype name, and finding the
callers of the new C2D virtual (a scan for calls through vptr +0xc, slot +0x20). Suggestions:

- When a removed function's paired caller calls a new function at the same call site, and that new
  function calls the removed one's callees (main → 0x1735e0 → getopt), pair them.
- When a pair's release side has only wrapper callers, check whether one wrapper has the prototype
  side's signature and callers; prefer it.
