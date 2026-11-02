/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body GetEntityList__7CEntityFv */
/* held from src/gamez/zEntity/ent_main.cpp:47 */
std::vector<CEntity*>& CEntity::GetEntityList()
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
