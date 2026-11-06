/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */
#include "gamez/zValve/zvalve.h"

/* @socom-skeleton body Set__6CValveFi */
/* held from src/gamez/zValve/valve_main.cpp:247 */
bool CValve::Set(u32 value)
{
	VALVE_STATE state;

	if (m_value != value && value != 0)
	{
		state = VALVE_STATE::VSTATE_DORMANT;
	}

	m_value = value;

	if (state != VALVE_STATE::VSTATE_DORMANT)
	{
		MakeCallbacks(state);
	}

	return state != VALVE_STATE::VSTATE_DORMANT;
}
