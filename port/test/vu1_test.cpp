/* Functional port lane TEST HOOK (off by default): SOCOM_PORT_VU1_TEST, port/CMakeLists.txt.
 *
 * Proves the EE -> VU1 packet contract on the menus, before the game loop is reachable:
 * at the end of each menu frame (zSysFifoEnd is wrapped with -Wl,--wrap) it kicks a
 * hand-built VU1 frame-setup packet (the layout of CCamera's tag_FrameSetup: DMA CNT 24,
 * UNPACK of 23 qwords to VU1 qword 4) and then draws one CVisual through the real EE path:
 * CVisual::Render -> VuUpdate -> VuObjectSetup / VuBatchProgram / VuExecuteState0 ->
 * CSPR::Copy / Kick -> zSysFifoKick -> VIF1 MFIFO. The visual's one-instance chain is a DMA
 * CNT carrying one batch (UNPACK with FLG) and a CNT 0 with VIF MSCNT, laid out as the VU1
 * microcode reads it (src/gamez/zRender/zrndr_vu1.vsm: vuDecompress0, vuXForm0,
 * vuGatherFixKick): one Gouraud triangle in screen pixels. Nothing here is game code or
 * evidence for the matching lane; never enable it in the default build. */
#include "gamez/zVisual/zvis.h"
#include "gamez/zCamera/zcam.h"
#include "gamez/zSystem/zsys.h"
#include "gamez/zSystem/zsys_spr.h"

extern "C" void __real__Z11zSysFifoEndv();

namespace
{
	/* the chain: header qword, CNT 18 + batch, CNT 0 + MSCNT */
	_word128 s_chain[1 + 1 + 18 + 1] __attribute__((aligned(16)));
	zdb::CVisual* s_visual;
	zdb::CCamera* s_camera;
	CMatrix s_identity;
	u32 s_frames;

	void SetQ(_word128* q, u32 x, u32 y, u32 z, u32 w)
	{
		q->u32[0] = x;
		q->u32[1] = y;
		q->u32[2] = z;
		q->u32[3] = w;
	}

	void SetF(_word128* q, f32 x, f32 y, f32 z, f32 w)
	{
		q->f32[0] = x;
		q->f32[1] = y;
		q->f32[2] = z;
		q->f32[3] = w;
	}

	void BuildChain()
	{
		_word128* header = &s_chain[0];
		_word128* tag = &s_chain[1];
		_word128* batch = &s_chain[2];
		_word128* end = &s_chain[20];

		for (u32 i = 0; i < sizeof(s_chain) / 16; i++)
			SetQ(&s_chain[i], 0, 0, 0, 0);

		header->u16[0] = 20;  /* chain qwords after the header */
		header->u8[2] = 1;    /* already "relocated" (SetBuffer is not used) */

		SetQ(tag, 0x10000000 | 18, 0, 0x01000101, 0x6c008000 | (18 << 16)); /* CNT 18; STCYCL 1,1; UNPACK V4-32 18 @0 FLG */

		/* batch[1]: GIF tag PACKED NREG 3 {ST, RGBAQ, XYZ2}, PRE, PRIM triangle + Gouraud */
		batch[1].u64[0] = (3ULL << 60) | (0x0bULL << 47) | (1ULL << 46) | 3;
		batch[1].u64[1] = 0x512;
		SetQ(&batch[2], 16, 0, 3, 1);                     /* x tri list at batch[16], z 3 vertices, w 1 triangle */
		SetF(&batch[3], 1728.0f, 1824.0f, 1048575.9f, 0.0f); /* decompress offset: GS window origin, near-max Z */

		static const s32 xy[3][2] = { { 200, 110 }, { 440, 110 }, { 320, 330 } };
		static const s32 rgba[3][4] = { { 255, 32, 32, 128 }, { 32, 255, 32, 128 }, { 32, 32, 255, 128 } };

		for (u32 v = 0; v < 3; v++)
		{
			_word128* vtx = &batch[4 + v * 3];
			SetQ(&vtx[0], xy[v][0] * 16, xy[v][1] * 16, 0, 0); /* itof4 position */
			SetQ(&vtx[1], 0, 0, 0, 0);                         /* ST, normal */
			SetQ(&vtx[2], rgba[v][0], rgba[v][1], rgba[v][2], rgba[v][3]);
		}

		SetQ(&batch[16], 0, 3, 6, 1); /* vertex offsets 3 * index into VU1_VTX_A, visible */
		SetQ(end, 0x10000000, 0, 0x17000000, 0); /* CNT 0; MSCNT */
	}

	void KickFrameSetup()
	{
		_word128* end;
		_word128* p = reinterpret_cast<_word128*>(zSysSprGetPacket(reinterpret_cast<unsigned __int128**>(&end)));

		for (u32 i = 0; i < 25; i++)
			SetQ(&p[i], 0, 0, 0, 0);

		SetQ(&p[0], 0x10000018, 0, 0, 0);                    /* CNT 24 */
		SetQ(&p[1], 0, 0x11000000, 0x01000101, 0x6c170004);  /* FLUSH; STCYCL 1,1; UNPACK 23 @4 */

		for (u32 m = 0; m < 3; m++)                          /* VU 4-15: world->screen, world->clip, clip->screen = identity */
			for (u32 r = 0; r < 4; r++)
				p[2 + m * 4 + r].f32[r] = 1.0f;

		SetQ(&p[24], 0x8000, 0x3035c000, 0x412, 0);          /* VU 26: shadow GIF tag, as CCamera::Update */
		zSysFifoKick(reinterpret_cast<unsigned __int128*>(p), 25);
	}

	void Draw()
	{
		if (s_visual == NULL)
		{
			BuildChain();
			s_camera = new zdb::CCamera();
			s_visual = new zdb::CVisual();
			s_visual->m_flag3 = 0; /* no vuFrontFace: the batch has no face plane */
			s_visual->m_buffers.push_back(&s_chain[0]);
			sceVu0UnitMatrix(s_identity.m_matrix);
			SOCOM_PORT_TRACE("VU1 TEST: one CVisual triangle per menu frame through CVisual::Render");
		}

		KickFrameSetup();

		zdb::CVisual::m_camera = s_camera;
		zdb::CVisual::m_ModelToWorld = &s_identity;
		sceVu0UnitMatrix(zdb::CVisual::m_WorldToModel.m_matrix);
		zdb::CVisual::m_fovStatus = 1; /* ZVIS_FOV_ALL_IN: no clipping program */
		zdb::CVisual::m_fovClipWord = 0;
		zdb::CVisual::m_fogEnable = false;
		zdb::CVisual::m_lightingEnable = false;
		zdb::CVisual::m_applyLocalLights = false;
		zdb::CVisual::m_applyMultipass = false;
		zdb::CVisual::m_applyScaleColor = false;
		zdb::CVisual::m_renderMap = false;

		zdb::CVisual::m_stack_vid.push_back(0);
		s_visual->Render(&s_identity);
		zdb::CVisual::m_stack_vid.pop_back();
	}
}

extern "C" void __wrap__Z11zSysFifoEndv()
{
	if (++s_frames > 120)
		Draw();

	__real__Z11zSysFifoEndv();
}
