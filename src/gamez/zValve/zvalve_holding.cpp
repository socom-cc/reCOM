/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */
#include "gamez/zValve/zvalve.h"

/* @socom-skeleton body Set__6CValveFi */
/* held from src/gamez/zValve/valve_main.cpp:247 */
bool CValve::Set(u32 value)
{
	/* 0x1ff660: a change of the 16-bit value calls the callbacks with 1 (set to non-zero) or 2
	 * (set to 0); no change, no callbacks (and false). The value is stored either way. (was:
	 * state left unset, and DORMANT for a change to non-zero, so no callback ran) */
	VALVE_STATE state = VALVE_STATE::VSTATE_DORMANT;

	if (m_value != value)
	{
		state = value != 0 ? VALVE_STATE::VSTATE_TEMPORARY : VALVE_STATE::VSTATE_PERMANENT;
	}

	m_value = value;

	if (state != VALVE_STATE::VSTATE_DORMANT)
	{
		MakeCallbacks(state);
	}

	return state != VALVE_STATE::VSTATE_DORMANT;
}
