# Audit of unmarked functions, list A (2026-11-15, socom-port-audit-a)

List A: the 148 reference-ELF functions (15,332 bytes) of the character, AI, entity and mission code that no
`@socom-skeleton` fence names but whose name is defined somewhere in `src/` (constructors, destructors, small
members, a few free functions). Each was disassembled from the reference ELF and compared with the port's
definition instruction by instruction (stores, calls, loops, constants, member and base construction or
destruction, return value). Scratch `build/port/boot-audit-a/` (untracked: NOTES.md, mine.txt, `asm.txt` with the
disassembly of every row, the CPnt3D experiment `pnt.sh` / `wsweep.sh`, `buildall.sh`). HEAD 86052025; no marker
was added, moved or changed and no function moved file.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 100 |
| FIXED | 7 |
| KEPT | 2 |
| EQUIVALENT-IMPLICIT | 35 |
| NOT LOCATED | 4 |
| total | 148 |

## Fixes (ELF addresses)

- `CPnt3D::CPnt3D()` 0x1a9160 (`zMath/zmath.h`): the ELF constructor is `jr ra / move v0,a0`, the members are left
  as they are; the port zeroed them. Now empty. Before the change every unit was compiled with
  `-Wuninitialized -Wmaybe-uninitialized` with both constructors (`pnt.sh`): the empty one adds exactly one
  warning, `CEntity::UpdateTargetList` copying a fresh `CTarget` whose `m_vec` is unset, which is the ELF's own
  behaviour (`CTarget::CTarget` 0x1efad0 leaves `m_vec` alone). Statics are unaffected (zeroed storage).
- `CEntity::TeleportTo(const CMatrix *)` 0x1ee5a0 (`zEntity/ent_main.cpp`): was empty. Now: the four velocities
  zeroed (+0x2c, +0x20, +0x38, +0x60), the matrix copied to `m_next_matrix`, its quaternion to `m_quat` and
  `m_next_quat`, the node placed (`SetMatrix(&m_next_matrix)`). ELF quirk noted, not repeated: the quaternion's
  length (InnerProduct + w*w, `sqrtf`) is computed and dropped. Only `CEntity` and `CTurret` keep this slot (vtables
  0x471b64, 0x4730c4); seals override it.
- `ftsGetAltitudeApprox` 0x1f20f0 (`zFTS/fts_main.cpp`): a port NULL guard on the AI-map cell removed; the ELF
  reads its flags directly (0x1f224c). `CAiMaps::GetLocation` has put the location on the map, so `GetCell`
  answers a cell or the dummy cell: no behaviour change.
- `CValve::Set` 0x1ff660 (`zValve/zvalve_holding.cpp`, the only built definition): the state was left unset and a
  change to non-zero gave DORMANT (no callbacks, false). Now as the ELF: a change of the value calls the callbacks
  with 1 (to non-zero) or 2 (to 0) and answers true; no change, no callbacks, false; the value is stored either way.
  Port callers: hold fire / fire at will (`CSealCtrlAi::SetHoldFire`), the satchel charge placement, the action
  reset of a replay (`CNodeAction::Reset`).
- `SealInitCharacterDynamics` 0x258ec0 (`zSeal/seal.cpp`): `dynamics.rdr` is read only while the dynamics are not
  loaded, with the path `data/common` (which becomes the reader's current path); the port read it every time with
  no path.
- `CDynGrenade::ComputeMaxVel` 0x2879f0 (`zSeal/seal_control.cpp`, and the same inline throw in
  `zSeal/seal_kit.cpp`): `cos_45` is 0x3f3504f7 (0.707107f); the port literal 0.70710725f was 0x3f3504fb.
- `CValvePool::FlushNames` 0x2f6e10 (`zValve/valve_list.cpp`): was empty. Now counts the valves whose name is in
  the pool's name buffer and empties the buffer when there are none or when forced. The ELF also answers
  `count != 0`; the port keeps the `void` that `zvalve.h` declares (its only ELF caller is `~CValvePool`
  0x2f7150, at exit).

## Kept

- `CEntityCtrl::PostMortemPreTick` 0x1f1fd0: `void` in the port (overrides in zSeal / zInput are `void`); the ELF
  returns 1 and its caller `CZSealBody::PreTick` ignores it.
- `ai::PushLineColor` 0x2e3380: `void`; the ELF returns 1 and its one caller (`CSealCtrl::PostTick` 0x287820)
  ignores it.

## Not located (for the later pass; not written)

- `CTarget::GetEntity` 0x25ab90 (`lw v0,0(a0)`; called by `CAiSPursue::Tick` 0x25a284, whose port reads
  `m_ent` directly).
- `CDIDummy::GetIntersect` 0x1f24f0, `CDIDummy::GetAltitude` 0x1f2500 (both return 0) and
  `CDIDummy::LoadTipAndTail` 0x1f2510 (empty): the port has no `CDIDummy` class (only a comment in
  `zIntersect/zintersect.h`); `fts_main.cpp`'s owner annotation lists them.

## Result table

| Address | Function | Port definition | Verdict | Evidence |
|---|---|---|---|---|
| 0x17fc20 | CAiEvent::~CAiEvent | zAI/ai_events.cpp | MATCH | frees m_bits.m_vec (the CBits dtor inline) and clears it |
| 0x197cb0 | CAiMap::GetCellCenter | zAI/zai.h -> GetCellPos (zAI/ai_mapwalk.cpp) | MATCH | bounds, centre x/z, 10-bit altitude, action offset; the cell flags read without a NULL test, as the ELF |
| 0x19a820 | CAiMap::GetBilinearAltitude | zAI/ai_maps.cpp | MATCH | four cells in the same order and weights, bad-altitude skip, renormalised under 0.98 |
| 0x19b0f0 | CAiMap::GetLocation(pos) | zAI/zai.h | MATCH | x/z box, truncated indexes, map id 0, grid test |
| 0x19ba90 | CAiMap::GetInterpolationCells | zAI/ai_maps.cpp | MATCH | step -1 at or below 0.5 (weight 0.5 + f), else +1 (1.5 - f) |
| 0x19d8e0 | CAiMap::names::names | zAI/zai.h (implicit) | EQUIVALENT-IMPLICIT | vector base only: begin/end/capacity zero |
| 0x19e020 | CAiMap::region::Contains | zAI/ai_mapdata.cpp | MATCH | 0 <= dx < m_dx and 0 <= dy < m_dy |
| 0x1a9160 | CPnt3D::CPnt3D | zMath/zmath.h | FIXED | empty in the ELF; was zeroing |
| 0x2d1e00 | CAiSBreach::~CAiSBreach | zAI/zai.h | EQUIVALENT-IMPLICIT | own vtable, CAiState's, delete; no member with a dtor |
| 0x1df110 | CZBodyAnim::NullNode | zBody/zbody.h | MATCH | -1 |
| 0x1e34a0 | CBody::NullNode | zBody/zbody.h | MATCH | -1 |
| 0x1e3920 | CZBodyPart::Orient | zBody/body.cpp | MATCH | SetPosition when this, SetRotation(&m_rot) |
| 0x1ee3c0 | CEntityCtrl::OnDeath | zEntity/zentity.h | MATCH | empty |
| 0x1ee5a0 | CEntity::TeleportTo(const CMatrix *) | zEntity/ent_main.cpp | FIXED | was empty |
| 0x1ee6c0 | CEntity::OnMissionEnd | zEntity/ent_main.cpp | MATCH | empty |
| 0x1f0180 | CRobin::setup | zEntity/ent_target.cpp | MATCH | first/end/count/total, wrap count or overflow |
| 0x1f0d70 | _sort_target | zEntity/ent_target.cpp | MATCH | a.m_distSq < b.m_distSq |
| 0x1f1410 | CTarget::CTarget(const CTarget &) | zEntity/zentity.h (implicit) | EQUIVALENT-IMPLICIT | memberwise copy of the 40 bytes |
| 0x1f1fd0 | CEntityCtrl::PostMortemPreTick | zEntity/zentity.h | KEPT | void; ELF returns 1, unread |
| 0x1f1fe0 | CEntityCtrl::GetRemoteControl | zEntity/zentity.h | MATCH | NULL |
| 0x1f1ff0 | CEntityCtrl::SetThrottle | zEntity/zentity.h | MATCH | m_throttle[index] = f12 |
| 0x1f20f0 | ftsGetAltitudeApprox | zFTS/fts_main.cpp | FIXED | NULL-cell guard removed |
| 0x25ab90 | CTarget::GetEntity | - | NOT LOCATED | no such member |
| 0x1f24f0 | CDIDummy::GetIntersect | - | NOT LOCATED | no CDIDummy class |
| 0x1f2500 | CDIDummy::GetAltitude | - | NOT LOCATED | no CDIDummy class |
| 0x1f2510 | CDIDummy::LoadTipAndTail | - | NOT LOCATED | no CDIDummy class |
| 0x1f2580 | CSaveModule::TestFlags | zSave/zsave.h | MATCH | equal: 1, else (flags & m_Flags) != 0 |
| 0x1f5ef0 | CMatrix::Transform(in, out, n) | zMath/zmath.h | MATCH | rows 0-3 with w 1; ELF quirk: a do-while (count 0 not tested first) |
| 0x1f9360 | CMission::~CMission | zFTS/fts_mission.cpp | EQUIVALENT-IMPLICIT | empty body; the two lists, the string, three C2DMessage_Q, three vectors, CSaveModule, in that order |
| 0x1fbc60 | CUIVariable::~CUIVariable | zUI/zui.h | MATCH | Destroy, then the vector and _zrdr |
| 0x1fbe80 | CUIVarSTable::CUIVarSTable | zUI/zui.h | MATCH | CSTable(0xffff, 1024) |
| 0x1fd560 | CSealCtrl::GetSealCtrlAi | zSeal/zseal.h | MATCH | NULL |
| 0x1fe130 | ftsSetSquirm | zFTS/fts_player.cpp | MATCH | doSquirm = arg |
| 0x1fe140 | CSealCtrlCopy::~CSealCtrlCopy | zFTS/fts_player.cpp | EQUIVALENT-IMPLICIT | own vtable, ~CSealCtrl, delete |
| 0x1fe1a0 | CSealCtrlCopy::IsPlayer | zFTS/fts_player.cpp | MATCH | 0 |
| 0x1fe1b0 | CSealCtrl::IsAi | zSeal/zseal.h | MATCH | 0 |
| 0x1fe1c0 | CSealCtrl::IsRemote | zSeal/zseal.h | MATCH | 0 |
| 0x1fe1d0 | CSealCtrl::OnStateChange | zSeal/zseal.h | MATCH | empty |
| 0x1fe1e0 | CSealCtrl::GetAiNetState | zSeal/zseal.h | MATCH | +0xe4 (DWARF m_ai_net_state) |
| 0x1fe1f0 | CSealCtrl::SetAiNetState | zSeal/zseal.h | MATCH | +0xe4 |
| 0x1ff660 | CValve::Set | zValve/zvalve_holding.cpp | FIXED | callbacks 1 / 2 on a change |
| 0x201260 | C2DString::GetString | zTwoD/ztwod.h | MATCH | +0x20 (DWARF m_string) |
| 0x201270 | C2DString::Draw | zTwoD/ztwod.h | MATCH | empty |
| 0x201280 | C2DString::GetSpacing | zTwoD/ztwod.h | MATCH | 0.0f |
| 0x201650 | CPnt3D::Cross | zMath/zmath.h | MATCH | w 1 operands, OuterProduct, Normalize when asked |
| 0x20a1e0 | CCtrlrConfigs::ReadBtnName | zFTS/fts_controller.cpp | MATCH | nine names in order, values 7 12 13 15 10 11 14 8 9, else 16 |
| 0x20c250 | CGameStateChangeCmd::~CGameStateChangeCmd | zGame/game_state.cpp | MATCH | empty, delete |
| 0x219340 | zdb::CClutterList::Add | zGrid/grid_clutter.cpp | MATCH | summary reset, repel flag, max far fade, swap with the first fading one |
| 0x21b5f0 | CInput::OpenPadIO | zInput/zin_main.cpp | MATCH | scePadInit(0), 0 |
| 0x21b780 | CCheat::TickAll | zInput/zin_cheats.cpp | MATCH | Update(dT, pad) for each |
| 0x2ce160 | CRemoteCtrl::~CRemoteCtrl | zInput/remote_control.cpp | MATCH | empty; ~CSealCtrl, delete |
| 0x2ce1c0 | CRemoteCtrl::GetRemoteControl | zInput/zinput.h | MATCH | this |
| 0x2ce1d0 | CRemoteCtrl::OnDeath | zInput/zinput.h | MATCH | empty |
| 0x2ce1e0 | CRemoteCtrl::OnStunDamage | zInput/zinput.h | MATCH | empty |
| 0x2ce1f0 | CRemoteCtrl::IsPlayer | zInput/zinput.h | MATCH | 0 |
| 0x2ce200 | CRemoteCtrl::IsRemote | zInput/zinput.h | MATCH | 1 |
| 0x258ec0 | SealInitCharacterDynamics | zSeal/seal.cpp | FIXED | read only when unloaded, data/common |
| 0x259160 | CAiSRescued::~CAiSRescued | zAI/zai.h | EQUIVALENT-IMPLICIT | own vtable, CAiState's, delete |
| 0x2591c0 | CAiSRescued::CanAttack | zAI/zai.h | MATCH | 0 |
| 0x2591d0 | CAiSRescued::CanScan | zAI/zai.h | MATCH | 0 |
| 0x2591e0 | CAiSRescued::GetScriptResponse | zAI/zai.h | MATCH | "on_rescued" |
| 0x2591f0 | CAiState::GetStatus | zAI/zai.h | MATCH | "" (0x4511e8) |
| 0x259200 | CAiState::CanPushAiState | zAI/zai.h | MATCH | 1 |
| 0x259210 | CAiState::CanSwitchAiState | zAI/zai.h | MATCH | 1 |
| 0x259220 | CAiState::CanPursue | zAI/zai.h | MATCH | 1 |
| 0x267e20 | CAiCone::ContainsPoint | zAI/zai.h | MATCH | stores m_vec and m_dot; in front, within m_height, radius test |
| 0x269420 | CAiState::CanScan | zAI/zai.h | MATCH | 1 |
| 0x26b170 | CAiState::~CAiState | zAI/zai.h | EQUIVALENT-IMPLICIT | vtable, delete |
| 0x26c5c0 | CAiState::OnSignal | zAI/zai.h | MATCH | empty |
| 0x26c5d0 | CAiState::Tick | zAI/zai.h | MATCH | 1 |
| 0x26c5e0 | CAiState::CanAttack | zAI/zai.h | MATCH | 1 |
| 0x26c5f0 | CAiState::GetScriptResponse | zAI/zai.h | MATCH | NULL |
| 0x26c600 | CAiSPursue::~CAiSPursue | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x26c660 | CAiSPursue::CanAttack | zAI/zai.h | MATCH | !(m_option_flags & 1) |
| 0x26c680 | CAiSAnimate::~CAiSAnimate | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x26c6e0 | CAiSGrenade::~CAiSGrenade | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x26c740 | CAiSGrenade::CanPursue | zAI/zai.h | MATCH | 0 |
| 0x26c750 | CAiSGrenade::CanAttack | zAI/zai.h | MATCH | 0 |
| 0x26c760 | CAiSDeploy::~CAiSDeploy | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x26c7c0 | CAiSDeploy::CanAttack | zAI/zai.h | MATCH | 0 |
| 0x26c7d0 | CAiSAction::~CAiSAction | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x26c830 | CSealCtrlAi::GetSealCtrlAi | zSeal/zseal.h | MATCH | this |
| 0x26c840 | CSealCtrlAi::GetJumpFlag | zSeal/zseal.h | MATCH | 0 |
| 0x26c850 | CSealCtrlAi::IsPlayer | zSeal/zseal.h | MATCH | 0 |
| 0x26c860 | CSealCtrlAi::IsAi | zSeal/zseal.h | MATCH | 1 |
| 0x27d9b0 | CZSealBody::SetPartAsGear | zSeal/seal_body.cpp | MATCH | offset, QFromRot, Orient with a node, body-part slot cleared |
| 0x281070 | CZSealBody::GetDynamics | zSeal/seal_cfg.cpp | MATCH | &theCharacterDynamics |
| 0x287930 | CDynGrenade::ComputeTimeToImpact | zSeal/seal_control.cpp | MATCH | quadratic(-49, vy, h), the larger root, else 0 |
| 0x287980 | CDynGrenade::ComputeElevOfs | zSeal/seal_control.cpp | MATCH | 0x3c8efa35 * (10 (1 - p) + 12 p) |
| 0x2879f0 | CDynGrenade::ComputeMaxVel | zSeal/seal_control.cpp (+ seal_kit.cpp copy) | FIXED | cos_45 literal |
| 0x28c180 | CZSealBody::GetAnimationNode | zSeal/seal_env.cpp | MATCH | even id: the (net) pickup's node |
| 0x29a6b0 | CNodeAction::GetAction | zNode/node_action.h | MATCH | dynamic_cast of m_nodeEx, then the parents (unrolled twice in the ELF) |
| 0x2a4bf0 | ftmask_create | zSeal/seal_env.cpp | MATCH | bit per integer or truncated real |
| 0x2a5a00 | CZKit::unwrap | zSeal/zseal.h | MATCH | -1 for index == count or no items, else wrapped |
| 0x2afba0 | CSavedFireModeInfo::CSavedFireModeInfo | zSeal/seal_kit.cpp | MATCH | 0, 255 |
| 0x2b3880 | CSealCtrlAi::PreTick(float, void *) | zSeal/seal_sensors.cpp | MATCH | statics, the snooze clock, both branches of the target walk, reverse walk, dumps at debug 2, counters cleared |
| 0x2b4190 | taskFindParam | zSeal/seal_tasks.cpp | MATCH | the index-th command of the type |
| 0x2d7a00 | CAiSCQBAttack::~CAiSCQBAttack | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2d7a60 | CAiSCQBAttack::CanAttack | zAI/zai.h | MATCH | 0 |
| 0x2d9040 | CAiSScript::KillResponse | zSeal/seal_aistate.cpp | MATCH | running response kept unless forced; flags, stop, resume, debug line |
| 0x2dca90 | CAiSUnknown::~CAiSUnknown | zSeal/zseal.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2dcaf0 | CAiSSuspended::~CAiSSuspended | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach (CMatrix has no dtor) |
| 0x2dcb50 | CAiSSuspended::CanAttack | zAI/zai.h | MATCH | 0 |
| 0x2dcb60 | CAiSSuspended::CanPursue | zAI/zai.h | MATCH | 0 |
| 0x2dcb70 | CAiSBreach::CanPursue | zAI/zai.h | MATCH | 0 |
| 0x2dcb80 | CAiSScript::~CAiSScript | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2dcbe0 | CAiSGoto::~CAiSGoto | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2dcc40 | CAiSHostage::~CAiSHostage | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2dcca0 | CAiSAvoid::~CAiSAvoid | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2dcd00 | CAiSPickup::~CAiSPickup | zSeal/zseal.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2df160 | CAiSFollow::~CAiSFollow | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e24a0 | CSealCtrlSquirm::GetJumpFlag | zSeal/zseal.h | MATCH | 0 |
| 0x2e3380 | ai::PushLineColor | zSeal/seal_ailines.cpp | KEPT | push_front (insert before the sentinel's next); void, ELF returns 1, unread |
| 0x2e4a50 | CAiSRush::~CAiSRush | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e9160 | CAiSPathRecover::~CAiSPathRecover | zAI/zai.h | EQUIVALENT-IMPLICIT | ~CAiPath of m_path (+0x28), CAiState's vtable, delete |
| 0x2e91e0 | CAiSPathRecover::CanAttack | zAI/zai.h | MATCH | 0 |
| 0x2e91f0 | CAiSPathRecover::CanPursue | zAI/zai.h | MATCH | 0 |
| 0x2e9200 | CAiSFlee::~CAiSFlee | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e9260 | CAiSFlee::CanScan | zAI/zai.h | MATCH | 0 |
| 0x2e9270 | CAiSFlee::CanPursue | zAI/zai.h | MATCH | 0 |
| 0x2e9280 | CAiSTarget::~CAiSTarget | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e92e0 | CAiSEvent::~CAiSEvent | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e9340 | CAiSRestrained::~CAiSRestrained | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e93a0 | CAiSRestrained::CanAttack | zAI/zai.h | MATCH | 0 |
| 0x2e93b0 | CAiSRestrained::CanScan | zAI/zai.h | MATCH | 0 |
| 0x2e93c0 | CAiSRestrained::GetScriptResponse | zAI/zai.h | MATCH | "on_restrained" |
| 0x2e93d0 | CAiSStunResponse::~CAiSStunResponse | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e9430 | CAiSStunResponse::CanAttack | zAI/zai.h | MATCH | 0 |
| 0x2e9440 | CAiSCorpse::~CAiSCorpse | zSeal/zseal.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e94a0 | CAiSHold::~CAiSHold | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e9500 | CAiSSurrender::~CAiSSurrender | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e9560 | CAiSSurrender::CanAttack | zAI/zai.h | MATCH | 0 |
| 0x2e9570 | CAiSSurrender::GetScriptResponse | zAI/zai.h | MATCH | "on_surrender" |
| 0x2e9580 | CAiSNoAmmo::~CAiSNoAmmo | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e95e0 | CAiSNoAmmo::CanAttack | zAI/zai.h | MATCH | 0 |
| 0x2e95f0 | CAiSReload::~CAiSReload | zSeal/zseal.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e9650 | CAiSReload::CanAttack | zSeal/zseal.h | MATCH | 0 |
| 0x2e9660 | CAiSShotAt::~CAiSShotAt | zAI/zai.h | EQUIVALENT-IMPLICIT | as CAiSBreach |
| 0x2e96c0 | CAiSShotAt::CanPursue | zAI/zai.h | MATCH | 0 |
| 0x2e9fe0 | compare_target | zSeal/ai_target.cpp | MATCH | same record, else both set and same entity |
| 0x2f6770 | CValve::Uninit | zValve/valve_list.cpp | MATCH | empty |
| 0x2f6e10 | CValvePool::FlushNames | zValve/valve_list.cpp | FIXED | was empty |
| 0x1a51f0 | AI_PARAMS::AI_PARAMS(const AI_PARAMS &) | zAI/zai.h (implicit) | EQUIVALENT-IMPLICIT | the 15 words copied |
| 0x31eaf0 | CZWeapon::IsLegalAmmo | zWeapon/zwep_weapon.cpp | MATCH | strcmp of the names over the legal list |
| 0x31ebd0 | CZWeapon::GetIconTextureName | zWeapon/zwep_weapon.cpp | MATCH | +0x10 |
| 0x31ec50 | CZWeapon::GetMuzzleVelocity | zWeapon/zwep_weapon.cpp | MATCH | +0x40 |
| 0x31ecb0 | CZWeapon::GetAmmoCapacity | zWeapon/zwep_weapon.cpp | MATCH | +0x24 |
| 0x31ecc0 | CZWeapon::GetDescription | zWeapon/zwep_weapon.cpp | MATCH | +0x8 |

The EQUIVALENT-IMPLICIT destructors: in the ELF each sets its own vtable, then `CAiState`'s (the base's inline
destructor), and deletes when asked; none destroys a member except `CAiSPathRecover` (`~CAiPath`). The port's
classes declare `virtual ~X() {}` with `CAiState` as the only base and no members with destructors besides that
`CAiPath`, so GCC's destructors do the same.

## Runs (final tree: HEAD 86052025 + mine.txt; focus kept in every run; screenshots in `build/port/screenshots/53-audit/`)

- aast (zseal4's scratch stability hook + `pad_fire.txt`, 165 s: intro movie skipped with CROSS, briefing cameras
  with X, firing): no STOP, no exception; enemies fire at the team ("OutPatrol1 fires at Hutchins"), kills with
  respawns and recycle timers (OutPatrol1 / OutPatrol3 alive 0 -> respawn 1 -> alive 1), the team FOLLOWING on the
  HUD at 130 s; heap in use 22.99-23.36 MB over 60-163 s with combat, level at 23.35 MB over 144-162 s. The
  mission-start CMD_HOLDFIRE orders now set the AIs' hold-fire valves through the corrected `CValve::Set`
  (callbacks with state 1); the team still returns fire.
- aaw (`port/test-hooks/win`, -DSOCOM_HOOK_WIN, 235 s): Snow3 rescued in Extract (209.7 s), mission_complete
  0 -> 1, "EXIT: debrief open (objectives 3/7)" at 215.5 s, MISSION SUCCESSFUL on screen.
- aasr (`port/test-hooks/state`, -DSOCOM_HOOK_MISSIONS=8): in use 18,666,708 B at return 1, then 18,666,804 B at
  returns 2-8: flat and equal to HEAD. None of the corrected functions frees memory on the mission -> menus path
  (`CValvePool::FlushNames` runs only from `~CValvePool` at exit).
- aadef (default build: no hooks, no fake pad): boots to dlgMenu at 15.7 s, the main menu on screen.

`python tools/socom.py audit independence --strict` passes.
