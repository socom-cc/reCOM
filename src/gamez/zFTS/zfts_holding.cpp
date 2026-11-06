/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */
#include <string.h>
#include <string>
#include "gamez/zCharacter/zchar.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zNetwork/znet.h"
#include "gamez/zReader/zrdr.h"
#include "gamez/zReader/zrdr_local.h"
#include "gamez/zVehicle/zvehicle.h"

/* @socom-skeleton body g_arrDefCharTypeNames */
/* held from src/gamez/zFTS/fts_mission.cpp:14 */
#if 0 /* port: duplicate of zFTS/fts_mission.cpp (ELF: g_arrDefCharTypeNames__25@unnamed@fts_mission_cpp@) */
char** g_arrDefCharTypeNames[32];
#endif

/* @socom-skeleton body g_iNumUiVehicles */
/* held from src/gamez/zFTS/fts_mission.cpp:15 */
#if 0 /* port: duplicate of zFTS/fts_mission.cpp (ELF: g_iNumUiVehicles__25@unnamed@fts_mission_cpp@) */
u32 g_iNumUiVehicles = 0;
#endif

/* @socom-skeleton body UpdateMissionArchive__FPCcPCc */
/* held from src/gamez/zFTS/fts_mission.cpp:19 */
#if 0 /* port: duplicate of zFTS/fts_mission.cpp (ELF: UpdateMissionArchive__25@unnamed@fts_mission_cpp@FPCcPCc) */
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
#endif

/* @socom-skeleton body CreateCustomCharTypes__FP11CVehicleRdrP5_zrdr */
/* held from src/gamez/zFTS/fts_mission.cpp:185 */
#if 0 /* port: duplicate of zFTS/fts_mission.cpp (ELF: CreateCustomCharTypes__25@unnamed@fts_mission_cpp@FP11CVehicleRdrP5_zrdr) */
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
#endif

/* @socom-skeleton body CreateCustomCharTypes__FP5_zrdr */
/* held from src/gamez/zFTS/fts_mission.cpp:211 */
#if 0 /* port: duplicate of zFTS/fts_mission.cpp (ELF: CreateCustomCharTypes__25@unnamed@fts_mission_cpp@FP5_zrdr) */
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
#endif

/* @socom-skeleton body LoadMissionMapVisibilities__FP5_zrdr */
/* held from src/gamez/zFTS/fts_mission.cpp:237 */
#if 0 /* port: duplicate of zFTS/fts_mission.cpp (ELF: LoadMissionMapVisibilities__25@unnamed@fts_mission_cpp@FP8CRdrFile) */
void LoadMissionMapVisibilities(_zrdr* start)
{

}
#endif
