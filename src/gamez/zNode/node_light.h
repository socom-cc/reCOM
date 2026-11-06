#ifndef NODE_LIGHT_H
#define NODE_LIGHT_H
#include <list>

#include "znode.h"
/* @socom-skeleton decl forward */
namespace zdb {
class CTickLightList;
}
/* @socom-skeleton end forward */

namespace zdb
{
	class CLight : public CNode
	{
	public:
		CLight();

		CLight* _Copy(const CNode*);
		bool    _Write(CSaveLoad&);

		bool Read(CSaveLoad&);

		bool SetActive(bool);
		CBBox* UpdateBBox(bool);

		f32 m_maxRangeSq;
		f32 m_maxRange;
		f32 m_minRange;
		f32 m_invMaxRange;
		f32 m_invDeltaRange;
		f32 m_opacity;
		CPnt3D m_diffuse;
		bool m_appliedToNode;
		CPnt3D m_WorldPosition;
		/* @socom-skeleton decl Q23zdb6CLight */
public:
		virtual ~CLight();
		virtual zdb::CNode * _Copy(zdb::CNode *) const;
		static zdb::CTickLightList m_tick_list;
		/* @socom-skeleton end Q23zdb6CLight */
	};

	class CLightMap : public CLight
	{
	public:
		CLightMap();

		CLightMap* _Copy(const CNode*);

		void SetTexture(CTexture*);

		CTexture* m_pTex;
		CMatrix m_worldToUV;
		CPnt4D m_dir;
		u32 m_isShadow : 1;
		u32 m_isReflection : 1;
		BLENDMODE m_blendmode;
		f32 m_SpecularFade;
		CNode* m_instance;
		/* @socom-skeleton decl Q23zdb9CLightMap */
public:
		virtual ~CLightMap();
		virtual zdb::CNode * _Copy(zdb::CNode *) const;
		/* @socom-skeleton end Q23zdb9CLightMap */
	};

	class CLightList : public std::list<CLight*>
	{

	};
}

void LightList_Search(zdb::CNode* node, zdb::CLightList& lightList);
#endif