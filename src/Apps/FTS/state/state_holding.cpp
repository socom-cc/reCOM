/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body __ct__10CMenuStateFv */
/* held from src/Apps/FTS/state/st_menu.cpp:16 */
CMenuState::CMenuState()
{
	m_name = zstrdup("MenuState");
	m_skip = 0;
	m_skip_swap = 0;

	TtySoundString = CSaferStr();
	BackSoundString = CSaferStr();

	SelectionSound = NULL;

	strncpy(m_DefaultMenu, "dlgIntroScreen.rdr", 64);

	TtySoundString.reserve(64);
	BackSoundString.reserve(64);
}
