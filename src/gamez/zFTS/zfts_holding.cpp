/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body g_arrDefCharTypeNames */
/* held from src/gamez/zFTS/fts_mission.cpp:14 */
char** g_arrDefCharTypeNames[32];

/* @socom-skeleton body g_iNumUiVehicles */
/* held from src/gamez/zFTS/fts_mission.cpp:15 */
u32 g_iNumUiVehicles = 0;

/* @socom-skeleton body UpdateMissionArchive__FPCcPCc */
/* held from src/gamez/zFTS/fts_mission.cpp:19 */
void UpdateMissionArchive(const char* type, const char* path)
{
	std::string pathstr;

	if (type)
	{
		pathstr.assign("run/", pathstr.length());

		if (strncmp(type, "mp", 2) == 0)
		{
			pathstr.append("mp");
		}
		else
		{
			if (strncmp(type, "m", 1) == 0)
			{
				pathstr.append("sp/");
			}
		}
	}

	if (path)
	{
		if (strlen(path) != 0)
		{
			pathstr.assign("run/", pathstr.length());

			if (strncmp(path, "mp", 2) == 0)
			{
				pathstr.append("mp/", strlen("mp/"));
			}
			else
			{
				if (strncmp(path, "m", 1) == 0)
				{
					pathstr.append("sp/", strlen("sp/"));
				}
			}

			pathstr.append(path, strlen(path));
			CRdrArchive::AddArchive("readerm.zar", pathstr.c_str());
			CRdrArchive::OpenAll();
		}
	}
}

/* @socom-skeleton body CreateCustomCharTypes__FP11CVehicleRdrP5_zrdr */
/* held from src/gamez/zFTS/fts_mission.cpp:185 */
void CreateCustomCharTypes(CVehicleRdr* reader, _zrdr* start)
{
	g_iNumUiVehicles = 0;

	if (_zrdr* vehicles = zrdr_findtag(start, "UiVehicles"))
	{
		_zrdr* node = NULL;
		for (u32 i = 0; node = &vehicles->array[i], i < vehicles->array->integer - 1; i++)
		{
			char* name = zrdr_findstring(node, "Name");
			CVehicleRdrEntry* entry = reader->GetEntryByName(name);

			if (!entry)
				continue;

			strcpy(*g_arrDefCharTypeNames[i], entry->m_character);
			CCharacterType* chartype_mod = CCharacterType::GetByNameMod(name);
			CCharacterType* chartype = CCharacterType::Create(name, chartype_mod, false);
			chartype->m_istemporary = true;

			entry->SetCharacterName(name);
			UpdateCharWeaponUiVars(i);
		}
	}
}

/* @socom-skeleton body CreateCustomCharTypes__FP5_zrdr */
/* held from src/gamez/zFTS/fts_mission.cpp:211 */
void CreateCustomCharTypes(_zrdr* start)
{
	g_iNumUiVehicles = 0;

	if (_zrdr* vehicles = zrdr_findtag(start, "UiVehicles"))
	{
		_zrdr* node = NULL;
		for (u32 i = 0; node = &vehicles->array[i], i < vehicles->array->integer - 1; i++)
		{
			char* name = zrdr_findstring(node, "Name");
			CVehicleRdrEntry* entry = NULL; // TODO: replace this

			if (!entry)
				continue;

			strcpy(*g_arrDefCharTypeNames[i], entry->m_character);
			CCharacterType* chartype_mod = CCharacterType::GetByNameMod(name);
			CCharacterType* chartype = CCharacterType::Create(name, chartype_mod, false);
			chartype->m_istemporary = true;

			entry->SetCharacterName(name);
			UpdateCharWeaponUiVars(i);
		}
	}
}

/* @socom-skeleton body LoadMissionMapVisibilities__FP5_zrdr */
/* held from src/gamez/zFTS/fts_mission.cpp:237 */
void LoadMissionMapVisibilities(_zrdr* start)
{

}

/* @socom-skeleton body ftsNetworkGameInit__Fv */
/* held from src/gamez/zFTS/fts_net_game.cpp:5 */
void ftsNetworkGameInit()
{
	CZNetGame* netGame = theMission.netGame;

	if (theNetwork.m_bSessionMaster)
	{

	}
}
