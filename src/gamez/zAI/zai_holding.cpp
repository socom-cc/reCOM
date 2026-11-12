/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */
#include "gamez/zAI/zai.h"
#include "gamez/zSeal/zseal.h" /* class ai (do_aimap_collide) */

/* port: do_aimap_collide__2ai (0x475d50, .sbss, 0) has no source owner yet; held here */
bool ai::do_aimap_collide;

/* @socom-skeleton body Reset__8CAiStateF8AI_STATE */
/* held from src/gamez/zAI/ai_main.cpp:129 */
void CAiState::Reset(AI_STATE state)
{
	/* 0x2d1e60 */
	m_unk_0c_1 = 0;
	m_state = (u8)state;
	m_unk_14 = 0;
	m_setup = 0;
	m_unk_08 = 0;
	m_option_flags = 0;
	m_response = 0;
	m_unk_0c_3 = 0;
}
