#ifndef NODE_SHADOW_H
#define NODE_SHADOW_H
#include "node_light.h"
/* @socom-skeleton decl forward */
namespace zdb {
class _tag_render_map_type;
}
/* @socom-skeleton end forward */

namespace zdb
{
	// TODO:
	// figure out what is in this unknown struct
	// it is taken as a parameter in the constructor of
	// CRenderMap::CRenderMap(CNode*, tag_render_map_type, CTexture*)
	struct tag_render_map_type
	{

	};

	class CRenderMap : public CLightMap
	{
	public:
		CRenderMap(CNode*, tag_render_map_type, CTexture*);

		void Update();
		/* @socom-skeleton decl Q23zdb10CRenderMap */
public:
		virtual ~CRenderMap();
		CRenderMap(zdb::CNode *, zdb::_tag_render_map_type, const zdb::CTexture *);
		/* @socom-skeleton end Q23zdb10CRenderMap */
	};
}
#endif