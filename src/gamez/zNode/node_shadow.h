#ifndef NODE_SHADOW_H
#define NODE_SHADOW_H
#include "node_light.h"
/* @socom-skeleton decl forward */
namespace zdb {
/* enum: the CRenderMap constructor stores it with sb and masks it with 0xff (0x22bca8) */
enum _tag_render_map_type : unsigned char {}; /* port: unproven - enumerators unknown */
}
/* @socom-skeleton end forward */

namespace zdb
{
	class CRenderMap : public CLightMap
	{
	public:
		/* constructor: the binary has only CRenderMap(CNode*, _tag_render_map_type, const CTexture*), declared below */

		void Update();
		/* @socom-skeleton decl Q23zdb10CRenderMap */
public:
		virtual ~CRenderMap();
		CRenderMap(zdb::CNode *, zdb::_tag_render_map_type, const zdb::CTexture *);
		zdb::CNode* m_node; /* port: unproven name - the CNode* at +0x180, right after CLightMap (CRenderMap::Update 0x22b310, CPipe::RenderWorld 0x2449ac) */
		/* @socom-skeleton end Q23zdb10CRenderMap */
	};
}
#endif