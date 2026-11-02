#ifndef NODE_ASSETLIB_H
#define NODE_ASSETLIB_H
#include <list>

#include "gamez/zNode/node_model.h"
#include "gamez/zTexture/ztex.h"
#include "gamez/zSystem/zsys.h"
/* @socom-skeleton decl forward */
namespace zdb {
class CTextureAssetCharacters;
}
/* @socom-skeleton end forward */

enum class _RenderPhase;

namespace zdb
{
	class CModel;
	class CTexture;
	class CTexPalette;
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
};
/* @socom-skeleton end 5CWind */
/* @socom-skeleton decl Q23zdb26CTextureAssetCharacterList */
namespace zdb {
class CTextureAssetCharacterList : public std::list
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
/* @socom-skeleton decl Q23zdb14CTickLightList */
namespace zdb {
class CTickLightList : public std::vector
{
public:
};
}
/* @socom-skeleton end Q23zdb14CTickLightList */
#endif