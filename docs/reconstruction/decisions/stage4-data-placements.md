# Data-object placements (stage 4)

The user's placements of data objects the ELF does not pin to a file (2026-11-22, the holding rows of
build/stage4/owner-decisions/holding-rows-2026-11-21.md, as that sheet proposes). One `## module/file` heading per destination, as in
stage4-function-placements.md; each line `- 0xADDR  name` names one data object. The binary brackets each
object between other units' data (link order) but names no unit; a guess is marked as one.

## ztexture/ztex_main.cpp
Note: (2026-11-22, holding rows of 2026-11-21) rows 19-21: the .sbss run between zsys_spr.cpp's m_running and ztex_read.cpp's m_freeAfterLoad; ztex_main.cpp holds CTexture's constructor and Init, the statics' user.
- 0x476558  zdb::CTexture::m_baseAddress
- 0x47655c  zdb::CTexture::m_startAddress
- 0x476560  zdb::CTexture::m_endAddress

## zvideo/zvid_video.cpp
Note: (2026-11-22, holding rows of 2026-11-21) rows 22-24: the .sdata run after util_stable.cpp and before vis_main.cpp; CVideo's members Brightness and Clear are placed here (stage4-function-placements.md).
- 0x4753d8  CVideo::m_defaultFrameRate
- 0x4753dc  CVideo::m_maxFrameRate
- 0x4753e0  CVideo::m_brightness

## zsystem/zsys_bench.cpp
Note: (2026-11-22, holding rows of 2026-11-21) rows 25-46: the contiguous .sbss run 0x4764c8-0x47651b (and drawTimeX in .data) between headset.cpp and zsys_memory.cpp; CBench::Reset is placed here (stage4-function-placements.md).
- 0x4764f4  CBench::countNodes
- 0x4764f8  CBench::countRenderNodes
- 0x4764fc  CBench::countAlphaNodes
- 0x476500  CBench::countClutterNodes
- 0x476504  CBench::countVisuals
- 0x476508  CBench::countAlphaVisuals
- 0x43a6d0  CBench::drawTimeX
- 0x4764c8  CBench::preTask
- 0x4764cc  CBench::postTask
- 0x4764d0  CBench::inputTime
- 0x4764d4  CBench::postCamUpdate
- 0x4764d8  CBench::postAppCamTick
- 0x4764dc  CBench::postCompassTick
- 0x4764e0  CBench::postHUDTick
- 0x4764e4  CBench::swapTime
- 0x4764e8  CBench::drawTime
- 0x4764ec  CBench::twoDTime
- 0x4764f0  CBench::dmaTime
- 0x47650c  CBench::countParticleSources
- 0x476510  CBench::countParticleSourcesProcessed
- 0x476514  CBench::countParticlesProcessed
- 0x476518  CBench::countParticlesDrawn

## zsystem/zsys_memory.cpp
Note: (2026-11-22, holding rows of 2026-11-21) row 47: directly before zsys_memory.cpp's __HeapSizePS2 in .sbss; read only by zsys_FullAllocAndFree.
- 0x47651c  __HeapSize

## zseal/seal_ai.cpp
Note: (2026-11-22, holding rows of 2026-11-21) row 48: inside the .sbss run of the ai / CSealCtrlAi statics that ends at seal_ai.cpp's LOCAL @2555.
- 0x475d50  ai::do_aimap_collide
Note: (2026-11-25, user: "Put the statics of CSealCtrlAi into seal_ai.cpp") the five .sbss CSealCtrlAi statics 0x475d54-0x475d67 lie between ai::do_aimap_collide 0x475d50 (placed here on 2026-11-22) and CSealCtrlAi::aiLogEnabled 0x475d68, which seal_ai.cpp owns (referenced only by seal_ai.cpp, directly before its LOCAL @2555 0x475d78); a unit's .sbss block is contiguous, so with those two owners the five are seal_ai.cpp's. Without the 2026-11-22 placement the binary would permit seal.cpp's tail as well (its LOCAL statics end at init$3579 0x475d40; seal.cpp and seal_ai.cpp are adjacent in link order, sinit 68, 69). Accesses: CSealCtrlAi::PreTick(float) in seal_ai.cpp increments the three counts (0x2677ac/b8, 0x2677d8/ec, 0x2677f8/0x267800); seal_sensors.cpp's PreTick(float, void *) stores zero to the three counts (0x2b3df8, 0x2b3e00, 0x2b3e04) and reads aiActiveCount (0x2b3924), hud_devtext.cpp's CHUD::StatusLine reads them; diCount is only stored, by seal_sensors.cpp's PrePostTick (0x2b380c); aiDebugEnabled (1 byte) is set to 1 by options.cpp's process_arguments (0x1742e4) and read by seal_tasks.cpp's CTGoto::Begin (0x2bc880); seal.cpp touches none of them. Link order rules those four files out (seal_sensors.cpp, seal_tasks.cpp, hud_devtext.cpp, options.cpp).
- 0x475d54  CSealCtrlAi::aiActiveCount
- 0x475d58  CSealCtrlAi::aiSleepingCount
- 0x475d5c  CSealCtrlAi::aiSnoozingCount
- 0x475d60  CSealCtrlAi::diCount
- 0x475d64  CSealCtrlAi::aiDebugEnabled
Note: (2026-11-25, the same decision) CSealCtrlAi::aiCameraRangeFilter 0x474f60 (.sdata, 1 byte, initial value 1) lies strictly inside seal_ai.cpp's .sdata run: after its LOCAL throttleEps 0x474f54 and the CSealCtrlAi statics aiAccuracyAngle 0x474f58 and aiEnabled 0x474f5c (placed in seal_ai.cpp), before aiSoundHandle 0x474f68, aiSoundInstance 0x474f70 and its LOCAL @3270 0x474f78; its only access is a store of zero by options.cpp's process_arguments (0x174340), which link order rules out.
- 0x474f60  CSealCtrlAi::aiCameraRangeFilter

## zsystem/zsys_init.cpp
Note: (2026-11-22, holding rows of 2026-11-21) row 49, user-accepted guess: .bss right after zsys_init.cpp's theIOPManager; zSysInit fills it (the origin zsys_main.cpp does not exist; alternative zsys_spr.cpp).
- 0x50ea70  zSys

## ztwod/ztwod_init.cpp
Note: (2026-11-22, holding rows of 2026-11-21) rows 50-56, user-accepted guess: the .sbss run after c2dstring.cpp's locals and before util_output.cpp's debug; link order rules out ztwod_main.cpp, the origin; set by C2D::Open and C2D::Init (alternative ztwod_bitmap.cpp).
- 0x476598  C2D::m_p2dcamera
- 0x476588  C2D::m_topx
- 0x47658c  C2D::m_botx
- 0x476590  C2D::m_topy
- 0x476594  C2D::m_boty
- 0x476580  C2D::m_fXPixel
- 0x476584  C2D::m_fYPixel

## zanim/zanim_load.cpp
Note: (2026-11-22, holding rows of 2026-11-21) row 57, user-accepted guess: .sbss between zanim_cmd_tick.cpp's and anim_main.cpp's data; zanim_load.cpp lies between them in text and is its only zAnim user (alternative anim_main.cpp, the origin).
- 0x4757ec  CZAnimMain::m_LoadFromZAR

## zweapon/zwep_weapon.cpp
Note: (2026-11-24, holding rows of 2026-11-21; first placed in zwep_global.cpp on 2026-11-22) rows 58-71, user-accepted guess: most of these statics are read by CZWeapon methods in zwep_weapon.cpp; CZProjectile in zwep_projectile.cpp also reads personMaterialId and m_timer_pCurval, and no zwep_weapon.cpp code reads m_allowFireAnimations, m_allowImpactAnimations and m_allowWeaponIntersection (rows 59-61: read by options.cpp, seal_kit.cpp and CZProjectile), which are placed with their class, CZWeapon's class file; the .sdata and .sbss runs fit one file per class (review of 2026-11-24: zwep_weaponlist.cpp at 0x314690, not zwep_global.cpp, is the first zWeapon unit in .text; alternative zwep_global.cpp); the ELF spells m_bulletpassSound.
- 0x475418  zwep::personMaterialId
- 0x47541c  CZWeapon::m_allowFireAnimations
- 0x475420  CZWeapon::m_allowImpactAnimations
- 0x475424  CZWeapon::m_allowWeaponIntersection
- 0x475428  CZWeapon::m_timer_bIncrTimer
- 0x47542c  CZWeapon::AI_PARAMS::version
- 0x47667c  CZWeapon::m_pProjectilelist
- 0x476680  CZWeapon::m_pMarklist
- 0x476684  CZWeapon::m_bulletpassSound
- 0x476688  CZWeapon::m_weaponTickDisabled
- 0x47668c  CZWeapon::m_timer_maxval
- 0x476690  CZWeapon::m_timer_pCurval
- 0x476694  CZWeapon::m_timer_bTimerRegistered
- 0x476698  CZWeapon::m_timer_bTimerCleared
