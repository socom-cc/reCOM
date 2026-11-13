# boot-teamhud notes (2026-11-13, socom-port-teamhud): the team status panel, bottom right (m8)

Untracked scratch. Changed files: `mine.txt` (= copy.txt for tree.sh); shared-file hunks: `shared.txt` + edits/.
Tools copied from boot-voicecams (itself from boot-orders; paths -> boot-teamhud / tree-teamhud / teamhud-default).
Test hook: hook_th.cpp (hookv.sh, bv.sh <build> pad_v1.txt).

## State / next step
- Written (compiles): CTeamNames Init (units) / Tick (hit + death paths) / Clear, CTeamMateNames Init /
  UnInit; edit files: GetHudHitFlag (bool), CSealCtrlAi::GetStatusString, CHUD::ReInit_Uninit / ReInit_Init.
- th1 (old HEAD 6ab484e; bv.sh th1 pad_v1.txt, hook_th.cpp) WORKS: rows KAHUNA (player, no text), BOOMER,
  JESTER, SPECTRE (the display names are the code names) with green dots; HOLD -> Bravo HOLDING (th1-76),
  Boomer ENGAGING while fighting (th1-82), FOLLOW -> all FOLLOWING (th1-95); Boomer hit twice: health 0.83
  -> dot 150/60/10, 0.75 -> 150/10/10 red (th1-110); Spectre's fatal fall: grey dot, dark red name, text off
  (th1-126); mission to t 145 s, no STOP, heap ~21.97 MB flat; pause -> REPLAY: ReOpen_Unload1/2, ReOpen_Load,
  mission 2 rows re-set (all green, Spectre alive, FOLLOWING) (th1-235), stable to t 48 s.
- th2 (HEAD b175ed7, stances): same results, mission to t 135 s, no STOP. def3 (teamhud-default at HEAD
  8d0eacc, edits re-applied cleanly): main menu (def3.png).
- Screens: build/port/screenshots/33-team-status/.
- DONE. hook_th.cpp never presses R1, so these runs say nothing about the map worker's "no round after the
  cameras" question.
- Seen, not chased: one th1 frame (t ~15) drew Boomer's order text empty for a moment; the trace showed it set.
  The ELF's C2DString ctor leaves m_string unzeroed, so an order text that was never loaded (the player's
  row) holds garbage, but it stays off.

## Survey (from the ELF)
- The bottom-right panel is CTeamNames (hud_teamnames.cpp; CHUD::m_teamnames +0x12b70), single player only
  (CHUD::Init 0x3baa8c / ReInit_Init 0x3bb100 call its Init when !theNetwork.m_bNetwork, else it is Off).
  CTeamMateNames (hud_teammatenames.cpp) is the network game's floating team-mate names (Init only when
  m_bNetwork): not part of this panel. PoseBitmap (hud_posebitmap.cpp) is the player's own stance icon, a
  separate element: the panel has no stance icon.
- Init 0x3d8a00: the box (newweapnbkrnd.tif mirrored, 435,364..640,438) + divider, 4 health dots
  (teammate_health.tif at x 519), rows i = 0..3 at y 382 + 15 i (+5 for Bravo): Able = CSealUnit 2's seals
  0, 1, Bravo = unit 3's seals 0, 1 (GetUnitByTeam + GetSealByIndex, SetupTeamNameEntry 0x3d8dc0: the
  display name in capitals right-aligned at x 510, the dot green, the order text off), and two "[" brackets
  (the element grouping; there is no element letter). Units exist before (CMission::Open / ReOpen_Load).
- Tick 0x3d83d0 per row with a seal (virtual: CHUD::Tick calls it):
  - health: CZSealBody::GetHudHitFlag 0x2941d0 (test and clear m_hudwashit, set by UpdateHealth when health
    drops / on death, SetHudHitFlag): alive -> the dot flashes (255,255,10) and its goal becomes
    (150, 10 + 150 * max(0, (health - 0.75) * 4), 10) (yellow-green at full health .. red at 75% or less);
    dead -> dot and goal deadColor (30,30,30), name colour (50,20,5) (dark red), order text off. No hit: the
    dot eases at m_increment (500/s) to its goal; SetColor = colour / 2.
  - state: dead -> order text off; alive: test and clear CZSealBody::m_order_flag (set by IssueCommand and by
    every AI state push / pop / resume: CAiState::Signal, StateTick, PopAiState..), then for an AI controller
    CSealCtrlAi::GetStatusString 0x26b7e0 -> the text at x 535 on the row, on, opaque. The text stays until
    the next one (m_arrOrderFadeTimes is written, never read).
- GetStatusString by the top AI state: HOLD -> HOLDING (COVERING with option 0x20), GOTO -> TRAVELING
  (LEADING opt 4, ATTACKING opt 8), FOLLOW -> FOLLOWING, DEPLOY -> DEPLOYING, BREACH -> BREACHING (substate
  >= 7 CLEARING), LASING -> LASING, PURSUE / TARGETING -> ENGAGING, ACTION on a door (AI map action type 1)
  -> OPENING / CLOSING by the valve value wanted; others NULL (nothing changes).
- Clear 0x3d8940 (ReInit_Uninit): texts wiped, brackets emptied, children dropped (m_ally kept: ELF).
- Empty on the chain before this work: GetHudHitFlag (void decl), GetStatusString, CTeamNames::Clear, the
  GetUnitByTeam calls (port-disabled), CHUD::ReInit_Uninit / ReInit_Init (empty bodies: after a REPLAY the
  panel would keep pointers to the old mission's seals), CTeamMateNames::UnInit (called by ReInit_Uninit).

## Written (ELF addresses)
- hud_teamnames.cpp (mine): Init's unit lookups 0x3d8c20, Tick 0x3d83d0 hit / death paths, Clear 0x3d8940.
- hud_teammatenames.cpp (mine): CTeamMateNames::Init 0x3dee20, UnInit 0x3deda0.
- edits/s_env.txt (seal_env.cpp): CZSealBody::GetHudHitFlag 0x2941d0 -> bool; edits/s_zseal.txt its decl.
- edits/s_ai.txt (seal_ai.cpp): CSealCtrlAi::GetStatusString 0x26b7e0.
- edits/s_hudmain.txt (hud_main.cpp): CHUD::ReInit_Uninit 0x3bb1c0, ReInit_Init 0x3bb050 (+ a local
  declaration of hudTurnOffScorePopup, which no header declares).

## ELF quirks kept
- The order text never fades (m_arrOrderFadeTimes written only). Clear leaves m_ally. SetOpacity sets the
  dots' trans twice and gives the order texts the raw opacity (boot-hud).
- After any hit the dot never returns to pure green: its goal is (150, g, 10).
- CTeamMateNames::UnInit leaves its texts listed as children.

## Not written
- CTeamMateNames::Tick 0x3de6a0 and WordIntersectionTest (network games only); hudTurnOffScorePopup (stub).
