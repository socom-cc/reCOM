/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body Draw2DOnly__9CGameMenuFv */
/* held from src/gamez/zGame/game_main.cpp:83 */
void CGameMenu::Draw2DOnly()
{
	thePipe.m_node = m_pBackplaneNode;
	thePipe.m_simpletrans = true;
	thePipe.RenderUiNode(&m_nodeTop);
	thePipe.m_simpletrans = false;
}
