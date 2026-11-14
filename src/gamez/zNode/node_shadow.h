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
		/* no DWARF record: the 736-byte layout (operator new 0x2e0 in CWorld::AddShadow
		   0x22f9f0) is from the constructor 0x22bc30, Update 0x22b310 and the destructor
		   0x22bba0; member names are the port's */
		zdb::CNode* m_node;             /* +0x180: the caster (an instance node, else NULL; RenderWorld 0x2449ac) */
		const zdb::CTexture* m_texture; /* +0x184: the render target (CWorld::m_shadowTex) */
		zdb::CLightMap* m_lightmap;     /* +0x188: the map's light map (this) */
		f32 m_screenScale;              /* +0x18c: texture width - 2 (pixels the caster spans) */
		f32 m_uvScale;                  /* +0x190: 1 - 1 / m_screenScale */
		CMatrix m_worldToView;          /* +0x1a0: a camera at the caster looking along the shadow vector */
		CMatrix m_viewToScreen;         /* +0x1e0: x / y scale, offset 2048 */
		CMatrix m_viewToUV;             /* +0x220: x / y scale, offset 0.5 */
		_word128 m_mtxTag;              /* +0x260: DMA CNT 4, VIF STCYCL 1,1, UNPACK 4 qwords to VU 4 */
		_word128 m_gifTagTag;           /* +0x280: DMA CNT 1, VIF STCYCL 1,1, UNPACK 1 qword to VU 26 */
		_word128 m_gifTag;              /* +0x290: VU 26, the shadow GIF tag (vuGatherFixKickShadow) */
		u8 m_type;                      /* +0x2a0: _tag_render_map_type (0 shadow, 1 reflection) */
		_word128 m_gsRef;               /* +0x2b0: DMA REF 13 to m_gsPacket, VIF FLUSH, DIRECT 13 */
		CPnt4D m_up;                    /* +0x2c0: the camera's up vector, across the shadow vector */
		_word128* m_gsPacket;           /* +0x2d0: shadowTemplate (13 qwords) set up for the texture */
		/* @socom-skeleton end Q23zdb10CRenderMap */
	};
}
#endif