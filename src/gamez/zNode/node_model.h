#ifndef NODE_MODEL_H
#define NODE_MODEL_H
#include <vector>

#include "znode.h"

#include "gamez/zAssetLib/assetlib_vector.h"

namespace zdb
{
	class CModel : public CNode
	{
	public:
		CModel(const char* name);

		static CModel* Create(CSaveLoad& sload, CAssetLib* library);

		bool Read(CSaveLoad& sload);
		void Release(CNode* node);

		s32 m_variant;
		bool m_bForceExport;
		bool m_bbox_valid;
		CRefList m_list;
		CAssetLib* m_AssetLib;
		/* @socom-skeleton decl Q23zdb6CModel */
public:
		virtual ~CModel();
		/* @socom-skeleton end Q23zdb6CModel */
	};

	class CModelVector : public std::vector<CModel*>
	{
	public:
		CModelVector() {}

		CModel* GetModel(const char* name);
	};
}
#endif