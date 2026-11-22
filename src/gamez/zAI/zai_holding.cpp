/* port: kept by hand: the held route moved CAiState::Reset to zai.h; ai::do_aimap_collide waits for its stage 4 owner row (seal_ai.cpp, user decision 2026-11-22). */
#include "gamez/zAI/zai.h"
#include "gamez/zSeal/zseal.h" /* class ai (do_aimap_collide) */

/* port: do_aimap_collide__2ai (0x475d50, .sbss, 0) has no source owner yet; held here */
bool ai::do_aimap_collide;
