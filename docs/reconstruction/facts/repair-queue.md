# Stage 3 recon repair queue (disposable working list; tracker evidence is authoritative)
- 0x1c5220 CZAnimMain::OpenFile (group c6ac02b3, applied): live returns /stdio.h/FILE *, only from fscanf's old library signature; body returns 0; repair to __sFILE * after group 221 (fscanf partial) is applied. Source: group 221 acceptance evidence (socom-verifier-r29).
- DmeFree (group 10af7db1, unresolved partial-candidate): its `void * *` parameter is the rules' untyped-pointee spelling; state that explicitly when it gets a partial row.
- 414 partial-candidate rows in applied groups: build/facts/partial-candidates.txt.
- 128-bit demangle fix (provable now): g53 0x2f5900 `void zSysFifoKick(uint16 *, uint)`, 0x2f5ab0 `uint16 * zSysSprGetPacket(uint16 **)`, 0x2f5d20 `uint16 * zSysAddDMA(uint16 *, uint16 *)`; g119 0x3805f0 `CDblBufTextureRelocator::TakeDrawPacket(this, uint16 *, uint)`. See build/verify-demangle/SUMMARY.txt.
- Slot-void rule (user decision 2026-10-23): applied partial rows in families like UpdateUIVar may become full void prototypes once recon void implements it.
- Slot-void rules v18 (commit above): 34 applied rows now have complete prototypes (12 P-slot-void, 17 P-void, 5 known family members); list in build/verify-slot-void/impact.md. Group 225's CRenderableString::UpdateUIVar partial row (0x390f10) becomes void: repair after 225 is applied.
- From repair 004 review (socom-verifier-r42): stub targets 0x38baa0, 0x38ba00, 0x393b90 (applied groups, recon void says void, live still default); zdb::CBatchRelocator::TakeDrawPacket 0x2fcb40 (partial candidate, same shape as 0x3805f0).
- Type candidate: CGraph (live 1-byte declaration-only forward). CGraph::Create shows 28 bytes: char * +0, list_deleter<PCv> +4 and +16 (group 237 review, socom-verifier-r44). Needs the fill-forward type-plan path (issue d314a84b).
- Type candidates: CAiStar (live 1-byte placeholder; CAiPath::CreatePlanner allocates 44 bytes) and CAiPlanner (1-byte placeholder) (group 248 review, socom-verifier-r46). Fill-forward path needed (issue d314a84b).
- Type candidate: CAiVisMap (live 1-byte placeholder; RegisterDynamicVisMap writes up to +80) (group 244 planning). CGraph +4/+8 list confirmed by CreateNode. Fill-forward path (issue d314a84b).

## Destination-narrowing returns (found by socom-verifier-r56, group 260 review, 2026-10-24)
Accepted rows whose `uchar` return may rest only on a caller narrowing into its own byte local
(destination width), not on the callee: re-check each with all callers (`--callers`), vtable/table
callback types and DWARF; repair to partial/unresolved if unproven.
- group 06f0b3d1: UICommandTable handler rows (dispatcher zAnimUIMenuTick narrows its own bool return).
- group 487ba19f: DoMiss 0x318d70 (HandleIntersections' shared byte local).

## Possible live-signature errors (group 276/278 planner socom-recon-planner-g152, 2026-10-24)
- CSealCtrlAi::SetAiMode: reads a3 at 0x266e70, not in its live 2-parameter signature (PathFollowTick passes its entry a3 through).
- CSealCtrlAi::GetAiAware: live `AI_AWARE (float)` has no `this`; check receiver.
- recon void ignores table-family verdicts: CSnd::Close's f0 chain ends at UISysPostInit (a table entry); an integer-width family verdict would make it void (tool idea).
- RESOLVED (socom-verifier-r63, 2026-10-24): SetAiMode's a3 'read' is a delay-slot lui/addiu inside the function (live 2-param signature correct); GetAiAware is static (live signature correct). No repair needed.

## Repair 007 candidates (group 279/280 planner socom-recon-planner-g153, 2026-10-24)
- group 7ab334be: CNetCnf::OpenTick, AddDevTick, ReadInterfaceListTick typed uchar from an lbu of an untyped handle byte + caller narrowing; the narrow-return audit did not list them. Re-check; withdraw to partial if unproven.

## Parameter widths from narrowing done only for a callee's argument (group 293 planner g160, 2026-10-25)
Rule (r70 rejection of group 289): narrowing applied only to pass a value to another callee proves that callee's width, not the parameter's; entry narrowing of the parameter itself or callers' extension still count. Re-check these accepted rows:
- group 63005b29: a0 of rt_msg_client_iset_server_send_aggregation_time (ushort)
- group 0d310fb6: rt_msg_client_disconnect
- group cf1cd7e2: port of rt_msg_client_iudp_clear_target (and udp_clear_target, NextSequenceID cited as precedents by r60)
- v19 candidates noted at plan time (groups 291/292): ToggleReady 0x207ec0, CZProjectileList::PostTick 0x31ac00 (v19 VERDICT void).

## Possible contradiction (group 319/320 planner g180, 2026-10-25)
- PickupBuddyCallback thunk 0x26fe40 (j 0x26f530) shows its target's live `CZBodyAnimBlend * (CZSealBody *, CZSealBody *)` (target typed in group 314), but its address is stored into the same DWARF `void (void *, void *)` member (ANIM_CALLBACK.m_func) as CrouchToPickupBuddyCallback. Re-check the target 0x26f530's return/parameters against that declared callback type.
