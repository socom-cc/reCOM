# boot-grenades notes (2026-11-12, socom-port-grenades2)

Scratch for grenades (thrown explosives). Untracked. Changed files: `mine.txt`; shared-file
edits in `edits/` (listed in `shared.txt`, applied to HEAD copies by `tree.sh`).

## State / next step
- DONE (HEAD 978c1b1 + mine + edits): select M67 -> throw -> flight -> bounce -> rest -> 5 s
  fuse -> explosion anim -> GRENADE_BLAST mark -> enemy flung, 7 fragments, killed; HUD 6/6 -> 5/6.
  Default build boots to the main menu (default.log/png, default2.log); t9 (and t11 on the new HEAD)
  run 175 s (~120 s of mission) without STOP.
- Shared files (NOT applied to the repo; coordinator merges): `edits/zh01_zseal.txt` (zseal.h:
  GetThrowAnim -> bool, DamageRandomLocation -> DAMAGE_LOCATION, ai::quadratic -> static bool),
  `edits/se01_env.txt` (seal_env.cpp: HandleDamageExplosive, GetNumExplosiveHits,
  HandleGrenadeExplosion, DamageRandomLocation), `edits/am01_aimain.txt` (ai_main.cpp: ai::elevate,
  ai::quadratic; zAI belongs to socom-port-aimove now). Format: srep.py (`@@@ file` / old / `@@=` /
  new). zseal.h and seal_env.cpp got uncommitted edits from another worker at 11:52 (I briefly
  applied mine there, then took exactly my hunks back out).
- Clip: build/port/recordings/2026-11-12_grenades.mp4 (22 s, from "GREN: throw begins").
- Screenshots: build/port/screenshots/19-grenades/.

## Tools
Copied tool set (paths -> boot-grenades / tree-grenades). `bd.sh <build> <pad> - [test edits]`,
`hook.sh <build> "<pad>" "<-D...>"` (hook_shapes.cpp from boot-ai: enemy SOCOM_HOOK_ENEMY ahead),
`go.ps1`, `build_default.sh <build>` (fresh tree with `shared_default.txt`, plain link),
`sinitvals.py <asm> <ptr sp offset>` (values a straight-line __sinit stores into an object).
tree.sh honours SHARED=<list>. Test-only edits: `edits/t_kit.txt` (kit item list trace),
`edits/t_settrigger.txt` (ai2's SetTrigger, needed before 978c1b1; no longer used).
Pads: `pad_t9.txt` = standard START path, 620:R2, 680:DOWN, 740:R2 (selects slot 4 M67; the menu's
DOWN goes to the previous index), R1 held 800-830 (full pressure = power 1), strafe right
1040 (LX=255+30), run 1075 (LY=0+95) toward the blast. Hook -DSOCOM_HOOK_ENEMY=265.0f puts
OutPatrol4 where the grenade lands. m8 kit: M4A1 SD, P9S, C4 x4, Mark141 x6, M67 x6.

## ELF chain (fire with a grenade)
CSealCtrl::Tick (R1 falling with a grenade: m_throwing, pressure readings; release: power =
GetThrowAverage, SetTrigger(true)) -> CZKit::Tick -> WillFireWeapon -> HandleFireWeapon (power >=
abort threshold) -> CZSealBody::BeginThrowItem -> GetThrowAnim -> PushBlend; fire time = release
fraction x loop time -> CZKit::TickExplosives (release point, CDynGrenade, ai::quadratic/elevate)
-> CZKit::Fire (fuse 5 s, removal 5.5 s) -> CZWeapon::Fire -> SetProjectile. Flight:
CZProjectile PreTick/PostTick -> HandleIntersections -> HandleBounce -> HandleTimers (fuse out) ->
PreTick (proximity DI of the explosion radius) -> PostTick -> HandleDelayedDetonate (special anim) ->
HandleDetonateExplosion (AddNewMark, OnWeaponHit of every node in range) -> CSealEx ->
CZSealBody::OnWeaponHit -> HandleDamage -> HandleDamageExplosive (FlingBody, sight line blast ->
head) -> next PostTick HandleGrenadeExplosion (shielding, stun, ringing ears, fragments,
UpdateHealth, killer).

## Written (ELF addresses)
- zwep_projectile.cpp: HandleBounce 0x318750, Detonate 0x3180c0, HandleDelayedDetonate 0x317df0,
  HandleDetonateExplosion 0x317cd0, WasDetonated 0x317350 (-> bool, zweapon.h).
- seal_body.cpp: GetThrowAnim 0x274ae0 (+ release offsets, statics typed float), BeginThrowItem
  0x2750d0, FlingBody 0x273bd0.
- seal_kit.cpp: TickExplosives 0x2aa7a0 throw part (player); file-local CDynGrenade ComputeMaxVel
  0x2879f0 / ComputeElevOfs 0x287980, _saturate<f> 0x1a8dd0, _max<f> 0x26c8a0 (no class/template
  declared in src); can_fire / l_offset statics typed. zbody.h: friend CZKit (CBody::m_state).
- zchar.h: throw_params defaults (0.15 / 600 / 300 / 0.6 / 0.3) from the ELF's inlined
  CharacterDynamics ctor in __sinit_seal_dyn.cpp 0x46ca00. Root cause of "the grenade drops at the
  feet": m8's dynamics.rdr has no THROW_PARAMS, the port had zeros.
- Shared (edit files): ai::quadratic 0x17e070, ai::elevate 0x17e190, HandleDamageExplosive 0x29bdd0,
  HandleGrenadeExplosion 0x28f840, GetNumExplosiveHits 0x28feb0, DamageRandomLocation 0x28f490.
- port/compat/libpad.c (fake pad): held buttons now report full pressure in rdata[8..19]; a term
  `<read>:R1P=<v>+<n>` (any <BUTTON>P) lowers it. Without this the throw power was 0 (abort).
- Traces (SOCOM_PORT only): "GREN: ..." throw begins / params / thrown / first bounce / at rest /
  detonated / blast / fling / blast reaches / sight line / fragment hits / killed.

## Results (t5/t8/t9 logs)
power 1.00, reach 600, elevation 12 deg, speed 238 -> lands ~250 ahead (bounce SNOW / PERSON,
elasticity 0.15), at rest; detonation 5 s after the throw; "special anim yes" (snow explosion puff
and smoke in the screenshots), mark on the ground (dark scorch next to the body, t9-87.png);
OutPatrol4 12.5 away: fling 95 (fall backward), exposed, 7 fragments, killed (HandleKiller).
Teammate/player outside 150 take nothing; a blast at the feet (t2/t3) killed player and Hutchins.
Half power (t7: R1P=127) gives the underhand toss anim (TossGrenade).

## ELF quirks kept
- TickExplosives (do_adjust): the throw speed becomes the hand's horizontal distance to the
  computed landing point (clamped to the 45 degree speed) - looks like a units mix-up, kept.
- HandleBounce reads the material's under-water bit without a NULL test (guarded).
- HandleGrenadeExplosion: with no fragment the UpdateHealth location is an uninitialised stack byte
  (0 here); ai::quadratic's linear case stores r2 twice and leaves r1.
- GetThrowAnim's offset out is always 0; both hands release from r_offset; the ground region read
  in HandleDetonateExplosion and the built world matrix are unused.

## Port deviations
- CDynGrenade / ai::_saturate<f> / _max<f> as file-local helpers in seal_kit.cpp (no declarations).
- Guards: HandleBounce material NULL; NotifyTargetDown's controller NULL.

## Not written / next
- HandleStunDamage 0x293f30 (stun 4 / 2 s for frags, flashbang 0, tear gas 1, smoke 3, taser 5):
  STUN_TYPE is an empty class in zseal.h (passed by value); needs an enum first (touches
  zinput.h, seal_ai/squirm/control/env). Calls left as comments in HandleGrenadeExplosion.
- AI events (CAiEvent::Acquire/Create unwritten) in HandleDelayedDetonate; CPickup::Create (the
  grenade pickup for AI throwbacks) in CZKit::Fire; AI throwers in TickExplosives
  (UpdateThrowFireParams); CSealCtrl::PostTick's debug throw line; CSealCtrlAi::OnWeaponEvent
  (AI reacting to a landed grenade, via MakeWeaponEventCallbacks -> HandleWeaponEvent 0x293bc0).
- HandleBloodDrip 0x2919a0 not written: needs m_blooddriptexhandles typed as vector<CZDecalDef>
  and InitDecalHandles' BLOOD_DRIP_DECALS part (more than "cheap").
- Other CharacterDynamics defaults differ from the ELF ctor (e.g. DamageToNewtons 235 vs 120,
  camera values 0); sinitvals.py lists all ELF values. Only throw_params was changed.
- C4 / claymore / satchel placement (TickExplosives placement branch), network grenades.
