/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include "ztwod.h"
#include "gamez/zVideo/zvid.h"
#include "gamez/zCamera/zcam.h"
#include "gamez/zMath/zmath.h"
#include "gamez/zTexture/ztex.h"
#include "gamez/zInput/zinput.h"
#include "gamez/zNode/node_assetlib.h"
#include "gamez/zReader/zrdr.h"

/* @socom-skeleton body __ct__7C2DFadeFv */
/* held from src/gamez/zTwoD/ztwod_fade.cpp:3 */
C2DFade::C2DFade()
{
	m_fade_enable = false;
	m_fade_dx = 0.0f;
	m_fade_limit = 128.0f;
}

/* @socom-skeleton body m_p2dcamera__3C2D */
/* held from src/gamez/zTwoD/ztwod_main.cpp:5 */
zdb::CCamera* C2D::m_p2dcamera;

/* @socom-skeleton body m_topx__3C2D */
/* held from src/gamez/zTwoD/ztwod_main.cpp:7 */
f32 C2D::m_topx;

/* @socom-skeleton body m_botx__3C2D */
/* held from src/gamez/zTwoD/ztwod_main.cpp:8 */
f32 C2D::m_botx;

/* @socom-skeleton body m_topy__3C2D */
/* held from src/gamez/zTwoD/ztwod_main.cpp:9 */
f32 C2D::m_topy;

/* @socom-skeleton body m_boty__3C2D */
/* held from src/gamez/zTwoD/ztwod_main.cpp:10 */
f32 C2D::m_boty;

/* @socom-skeleton body m_fXPixel__3C2D */
/* held from src/gamez/zTwoD/ztwod_main.cpp:11 */
f32 C2D::m_fXPixel;

/* @socom-skeleton body m_fYPixel__3C2D */
/* held from src/gamez/zTwoD/ztwod_main.cpp:12 */
f32 C2D::m_fYPixel;

/* @socom-skeleton body __ct__3C2DFv */
/* held from src/gamez/zTwoD/ztwod_main.cpp:14 */
C2D::C2D()
{
	m_on = true;
	first = true;
	m_isAA = false;
	m_isTrans = false;
	m_hasTexture = true;
	m_isFrameAlpha = false;
	
	m_uivar = NULL;
	m_active_and_handling_input = true;
}

/* @socom-skeleton body CanHandleInput__3C2DFv */
/* held from src/gamez/zTwoD/ztwod_main.cpp:43 */
bool C2D::CanHandleInput()
{
	return m_active_and_handling_input;
}

/* @socom-skeleton body SetCanHandleInput__3C2DFb */
/* held from src/gamez/zTwoD/ztwod_main.cpp:48 */
void C2D::SetCanHandleInput(bool enable)
{
	m_active_and_handling_input = enable;
}

/* @socom-skeleton body GetAssetLibs__3C2DFRQ23C2D8CLibList */
/* held from src/gamez/zTwoD/ztwod_main.cpp:53 */
void C2D::GetAssetLibs(CLibList& libs)
{
	for (auto i = begin(); i != end(); ++i)
		(*i)->GetAssetLibs(libs);
}

/* @socom-skeleton body SetUseFrameBufferAlpha__3C2DFb */
/* held from src/gamez/zTwoD/ztwod_main.cpp:73 */
void C2D::SetUseFrameBufferAlpha(bool enable)
{
	m_isFrameAlpha = enable;
}

/* @socom-skeleton body Load__9C2DStringFPCcP10C2DTTFFontiiii */
/* held from src/gamez/zTwoD/ztwod_string.cpp:85 */
void C2DString::Load(const char* message, C2DTTFFont* font, s32 x, s32 y, s32 width, s32 height)
{
    m_pos.x = x;
    m_pos.y = y;
    SetString(message);

    if (m_color.w >= 128.0f)
    {
        SetTrans(m_color.w);
    }

    m_charwidth = width;
    m_charheight = height;
}

/* @socom-skeleton body Load__9C2DStringFPCcP10C2DTTFFontii */
/* held from src/gamez/zTwoD/ztwod_string.cpp:100 */
void C2DString::Load(const char* message, C2DTTFFont* font, s32 x, s32 y)
{
    m_pos.x = x;
    m_pos.y = y;
    SetString(message);

    if (m_color.w >= 128.0f)
    {
        SetTrans(m_color.w);
    }
}

/* @socom-skeleton body Load__9C2DStringFfPCcP10C2DTTFFontii */
/* held from src/gamez/zTwoD/ztwod_string.cpp:112 */
void C2DString::Load(f32 scale, const char* message, C2DTTFFont* font, s32 x, s32 y)
{
    m_scale = scale;
    Load(message, font, x, y);
}

/* port: stub __dt__7C2DLineFv (no owner in the render) */
/* port: stage-4 left 0x2fe8e0 without an owner */
C2DLine::~C2DLine()
{
}
