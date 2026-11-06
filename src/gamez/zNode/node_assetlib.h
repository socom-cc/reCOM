#ifndef NODE_ASSETLIB_H
#define NODE_ASSETLIB_H

/* port: forward declarations for names this header uses */
struct _zanim_cmd_hdr;
struct _zrdr;
#include <list>

#include "gamez/zNode/node_model.h"
#include "gamez/zTexture/ztex.h"
#include "gamez/zSystem/zsys.h"
/* @socom-skeleton decl forward */
namespace zdb {
class CTextureAssetCharacters;
}
/* @socom-skeleton end forward */

namespace zdb
{
	class CModel;
	class CTexture;
	class CTexPalette;
	class CLight;
}

namespace zdb
{
	class CAssetLib
	{
		friend class CAssetList;
	public:
		CAssetLib(const char* name);

		bool AddTexture(const char* name);
		bool AddTexture(CTexture* texture);
		CModel* AddModel(CModel* model);
		CTexPalette* AddPalette(CTexPalette* palette, bool checkDuplicate);

		bool IsNamed(const char* name) const;
		char* RootName() const;

		char* m_name;

		CModelVector m_models;
		CTexList m_textures;
		CTexPalList m_palettes;

		bool m_autoload;
		bool m_locked;
		bool m_gearlib;

		_RenderPhase m_renderphase;

		void* m_texture_buffer;
		void* m_model_buffer;

		s32 m_iRefCount;
		/* @socom-skeleton decl Q23zdb9CAssetLib */
public:
		~CAssetLib();
		char * RootName();
		bool IsNamed(const char *);
		static int m_conflictresolver;
		/* @socom-skeleton end Q23zdb9CAssetLib */
	};

	class CAssetList : public std::list<CAssetLib*>
	{
	public:
		CTexHandle* GetTexHandle(const char* name);
		CAssetLib* FindLib(const char* name);
		CModel* GetModel(const char* name);

		CModel* m_cache_model;
		/* @socom-skeleton decl Q23zdb10CAssetList */
public:
		void Clear();
		zdb::CAssetLib * FindLib(zdb::_RenderPhase);
		/* @socom-skeleton end Q23zdb10CAssetList */
	};

	class CAssetMgr
	{
	public:
		static CAssetLib* GetLoadedLibRef(const char* name);

		static CAssetList m_assets;
		/* @socom-skeleton decl Q23zdb9CAssetMgr */
public:
		static void ReleaseLibRef(zdb::CAssetLib *);
		/* @socom-skeleton end Q23zdb9CAssetMgr */
	};
}

extern void HookupLib(zdb::CAssetLib* lib);
/* @socom-skeleton decl 5CWind */
class CWind
{
public:
	static void RegisterAnimCommands();
	static _zanim_cmd_hdr * CmdParseWind(_zrdr *);
	static bool CmdTickWind(_zanim_cmd_hdr *, float *);
	void Tick(float);
	void TickGoal(float);
	void Reset();

	/* members: DWARF CWind (global), 104 bytes */
	f32 m_AzimuthGoal;
	f32 m_ZenithGoal;
	f32 m_SpeedGoal;
	f32 m_AzimuthGoalDelta;
	f32 m_ZenithGoalDelta;
	f32 m_SpeedGoalDelta;
	f32 m_Azimuth;
	CPnt4D m_Wind;
	f32 m_Zenith;
	f32 m_Speed;
	f32 m_AzimuthOffset;
	f32 m_MinAzimuthOffset;
	f32 m_MaxAzimuthOffset;
	f32 m_ZenithOffset;
	f32 m_MinZenithOffset;
	f32 m_MaxZenithOffset;
	f32 m_AzimuthOffsetVelocity;
	f32 m_ZenithOffsetVelocity;
	f32 m_SpeedOffset;
	f32 m_MinSpeedOffset;
	f32 m_MaxSpeedOffset;
	f32 m_SpeedOffsetVelocity;
	bool m_TickAzimuth;
	bool m_TickZenith;
	bool m_TickSpeed;
	bool m_TickGoal;
};
/* @socom-skeleton end 5CWind */
/* @socom-skeleton decl Q23zdb26CTextureAssetCharacterList */
namespace zdb {
class CTextureAssetCharacterList : public std::list<void const*> /* port: element type from MSL pointer storage in DWARF; real element unproven */
{
public:
	void TestFOV(zdb::CCamera *, zdb::CTextureAssetCharacters **);
};
}
/* @socom-skeleton end Q23zdb26CTextureAssetCharacterList */
/* @socom-skeleton decl Q23zdb23CTextureAssetCharacters */
namespace zdb {
class CTextureAssetCharacters
{
public:
	void TestFOV(zdb::CCamera *);
	CTextureAssetCharacters(zdb::CAssetLib *, zdb::CNode *, zdb::CDynTexList *);
};
}
/* @socom-skeleton end Q23zdb23CTextureAssetCharacters */
namespace zdb {
/* DWARF zdb::CTickLight: 12 bytes (element of CTickLightList) */
class CTickLight
{
public:
	CLight* m_pLight;
	u8 m_state; /* port: unproven (1-byte state or flag) */
	f32 m_scale;
};
}
/* @socom-skeleton decl Q23zdb14CTickLightList */
namespace zdb {
class CTickLightList : public std::vector<CTickLight>
{
public:
};
}
/* @socom-skeleton end Q23zdb14CTickLightList */
namespace zdb
{
	void EmptyAssetRecycleBin(); /* EmptyAssetRecycleBin__3zdbFv (node_assetlib.cpp) */
}
#endif