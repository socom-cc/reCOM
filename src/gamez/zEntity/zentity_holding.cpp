/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */
#include "gamez/zEntity/zentity.h"

/* @socom-skeleton body GetEntityList__7CEntityFv */
/* held from src/gamez/zEntity/ent_main.cpp:47 */
CEntityList& CEntity::GetEntityList()
{
	return m_list;
}

/* @socom-skeleton body IsAlive__7CEntityCFv */
/* held from src/gamez/zEntity/ent_main.cpp:52 */
bool CEntity::IsAlive() const
{
	return m_isAlive;
}

/* @socom-skeleton body SetController__7CEntityFP11CEntityCtrl */
/* held from src/gamez/zEntity/ent_main.cpp:71 */
void CEntity::SetController(CEntityCtrl* controller)
{
	if (m_control)
	{
		m_control->m_entity = NULL;
	}

	m_control = controller;

	if (m_control)
	{
		m_control->m_entity = this;
	}
}

/* @socom-skeleton stub __ct__11CEntityCtrlFi */
CEntityCtrl::CEntityCtrl(s32)
{
	/* ELF 0x1f20a0: m_entity = 0; memset(m_throttle, 0, 12) */
	m_entity = NULL;
	m_throttle[0] = m_throttle[1] = m_throttle[2] = 0.0f;
}

/* @socom-skeleton stub __dt__11CEntityCtrlFv */
CEntityCtrl::~CEntityCtrl()
{
}

/* @socom-skeleton stub PreTick__11CEntityCtrlFf */
void CEntityCtrl::PreTick(float)
{
}

/* @socom-skeleton stub Tick__11CEntityCtrlFf */
void CEntityCtrl::Tick(float)
{
}

/* @socom-skeleton stub PreTick__7CEntityFf */
void CEntity::PreTick(float)
{
}

/* @socom-skeleton stub Tick__7CEntityFf */
void CEntity::Tick(float)
{
}

/* @socom-skeleton stub PostPreTick__7CEntityFf */
void CEntity::PostPreTick(float)
{
}

/* @socom-skeleton stub PrePostTick__7CEntityFf */
void CEntity::PrePostTick(float)
{
}

/* @socom-skeleton stub PostTick__7CEntityFf */
void CEntity::PostTick(float)
{
}

/* @socom-skeleton stub UpdateNextPosition__7CEntityFv */
void CEntity::UpdateNextPosition()
{
}

/* @socom-skeleton stub ComputeNextPosition__7CEntityFf */
void CEntity::ComputeNextPosition(float)
{
}
