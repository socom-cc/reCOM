/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */
#include "gamez/zAI/zai.h"

/* @socom-skeleton body Reset__8CAiStateF8AI_STATE */
/* held from src/gamez/zAI/ai_main.cpp:129 */
void CAiState::Reset(AI_STATE state)
{
	m_bitfield = m_bitfield & 0b11111101;
	m_state = state;
	m_field8_0x14 = 0;
	m_bitfield = m_bitfield & 0b11111110;
	m_field2_0x8 = 0;
	m_field1_0x4 = 0;
	m_bitfield = m_bitfield & 0b11111011;
	m_bitfield = m_bitfield & 0b00000111;
}
