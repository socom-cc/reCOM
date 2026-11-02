/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body __ct__9C2DBitmapFv */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:4 */
C2DBitmap::C2DBitmap()
{
	m_pTexHandle = NULL;
	m_iWidth = 0;
	m_iHeight = 0;
	m_x = 0;
	m_y = 0;

	m_NewUV[0][0] = 0.01f;
	m_NewUV[0][1] = -0.01f;
	m_NewUV[0][2] = 0.0f;
	m_NewUV[0][3] = 0.0f;
	m_NewUV[1][0] = 0.99f;
	m_NewUV[1][1] = -0.99f;
	m_NewUV[1][2] = 1.0f;
	m_NewUV[1][3] = 0.0f;

	m_RGB[0][0] = 255.0f;
	m_RGB[0][1] = 255.0f;
	m_RGB[0][2] = 255.0f;
	m_RGB[0][3] = 100.0f;
	m_RGB[1][0] = 255.0f;
	m_RGB[1][1] = 255.0f;
	m_RGB[1][2] = 255.0f;
	m_RGB[1][3] = 100.0f;
	m_RGB[0][0] = 128.0f;
	m_RGB[0][1] = 128.0f;
	m_RGB[0][2] = 128.0f;
	m_RGB[1][0] = 128.0f;
	m_RGB[1][1] = 128.0f;
	m_RGB[1][2] = 128.0f;

	SetTrans(128.0f);
}

/* @socom-skeleton body Load__9C2DBitmapFffffPQ23zdb10CTexHandle */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:39 */
void C2DBitmap::Load(f32 x, f32 y, f32 width, f32 height, zdb::CTexHandle* handle)
{
	m_pTexHandle = handle;
	
	m_x = static_cast<s32>(x);
	m_y = static_cast<s32>(y);
	m_iWidth = static_cast<s32>(width) - m_x;
	m_iHeight = static_cast<s32>(height) - m_y;
	
	if (m_hasTexture)
	{
		
	}
}

/* @socom-skeleton body Load__9C2DBitmapFffPQ23zdb10CTexHandle */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:54 */
void C2DBitmap::Load(f32 x, f32 y, zdb::CTexHandle* handle)
{
	zdb::CTexture* texture = NULL;

	m_pTexHandle = handle;

	if (!m_hasTexture)
	{
		if (handle != NULL)
		{
			texture = handle->m_texture;
		}

		if (texture == NULL && !first)
		{
			return;
		}

		first = false;
		return;
	}

	if (m_pTexHandle == NULL)
	{
		texture = NULL;
	}
	else
	{
		texture = m_pTexHandle->m_texture;
	}

	if (texture != NULL)
	{
		m_x = static_cast<s32>(x);
		m_y = static_cast<s32>(y);
		m_iWidth = m_pTexHandle->m_texture->m_width;
		m_iWidth = m_pTexHandle->m_texture->m_height;
	}
}

/* @socom-skeleton body Draw__9C2DBitmapFRC7CMatrixPQ23zdb16CTextureRelocMgr */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:94 */
void C2DBitmap::Draw(const CMatrix& transform, zdb::CTextureRelocMgr* reloc)
{
	zdb::CTexture* texture = NULL;

	if (!IsOn())
	{
		return;
	}

	if (!m_hasTexture)
	{
		if (m_pTexHandle == NULL)
		{
			texture = NULL;
		}
		else
		{
			texture = m_pTexHandle->m_texture;
		}

		if (texture == NULL)
		{
			if (first)
			{
				first = false;
			}

			C2D::Draw(m_p2dcamera);
			return;
		}
	}

	MakePacket(m_p2dcamera, reloc, transform);
	C2D::Draw(m_p2dcamera);
}

/* @socom-skeleton body Draw__9C2DBitmapFPQ23zdb7CCamera */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:130 */
void C2DBitmap::Draw(zdb::CCamera* camera)
{
	if (!IsOn())
	{
		return;
	}

	if (!m_hasTexture)
	{
		zdb::CTexture* texture = NULL;
		
		if (!m_pTexHandle)
		{
			texture = NULL;
		}
		else
		{
			texture = m_pTexHandle->m_texture;
		}

		if (!texture)
		{
			if (first)
			{
				first = false;
			}

			/*SDL_SetRenderDrawColor(theWindow->GetRenderer(), m_RGB[0][0], m_RGB[0][1], m_RGB[0][2], 255);
			SDL_RenderFillRect(theWindow->GetRenderer(), &m_rect);*/
		}
	}
	else
	{
		/*SDL_RenderTexture(theWindow->GetRenderer(), m_pSDLTexture, NULL, &m_rect);*/
	}
}

/* @socom-skeleton body TickFade__9C2DBitmapFv */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:167 */
void C2DBitmap::TickFade()
{
	float alpha = 0.0f;
	float limit = 0.0f;

	if (m_fade_enable)
	{
		float alpha = m_RGB[0][3] + m_fade_dx;

		if (m_fade_dx < 0.0f)
		{
			float limit = m_fade_limit;

			if ((m_fade_limit <= alpha) && (limit = alpha, alpha < 0.0f))
			{
				limit = 0.0f;
			}
		}
		else
		{
			float limit = m_fade_limit;

			if ((alpha <= m_fade_limit) && (limit = 128.0f, alpha <= 128.0f))
			{
				limit = alpha;
			}
		}

		SetTrans(limit);
	}
}

/* @socom-skeleton body MakePacket__9C2DBitmapFPQ23zdb7CCameraPQ23zdb16CTextureRelocMgrRC7CMatrix */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:199 */
void C2DBitmap::MakePacket(zdb::CCamera* camera, zdb::CTextureRelocMgr* reloc, const CMatrix& transform)
{
	// TODO:
	// Add more to this function

	reloc->AddToBatch(m_pTexHandle);
}

/* @socom-skeleton body Reset__9C2DBitmapFv */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:207 */
void C2DBitmap::Reset()
{
	m_x = 0;
	m_y = 0;
	m_pTexHandle = NULL;
	m_iWidth = 0;
	m_iHeight = 0;
}

/* @socom-skeleton body GetTrans__9C2DBitmapCFv */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:216 */
bool C2DBitmap::GetTrans() const
{
	return m_isTrans;
}

/* @socom-skeleton body SetTrans__9C2DBitmapFf */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:221 */
void C2DBitmap::SetTrans(float transparency)
{
	m_RGB[0][3] = transparency;
	m_RGB[1][3] = transparency;
	m_isTrans = true;
}

/* @socom-skeleton body SetPos__9C2DBitmapFiiii */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:228 */
void C2DBitmap::SetPos(s32 x, s32 y, s32 width, s32 height)
{
	m_x = x;
	m_y = y;
	m_iWidth = width - x;
	m_iHeight = height - y;
}

/* @socom-skeleton body SetPos__9C2DBitmapFii */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:236 */
void C2DBitmap::SetPos(s32 x, s32 y)
{
	zdb::CTexture* texture = NULL;

	if (m_pTexHandle == NULL)
	{
		texture = NULL;
	}
	else
	{
		texture = m_pTexHandle->m_texture;
	}

	if (texture != NULL)
	{
		m_x = x;
		m_y = y;
		m_iWidth = m_pTexHandle->m_texture->m_width;
		m_iWidth = m_pTexHandle->m_texture->m_height;
	}
}

/* @socom-skeleton body SetUV__9C2DBitmapFffff */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:258 */
void C2DBitmap::SetUV(f32 u0, f32 v0, f32 u1, f32 v1)
{
	m_NewUV[0][0] = u0;
	m_NewUV[0][1] = -v0;
	m_NewUV[1][0] = u1;
	m_NewUV[1][1] = -v1;
}

/* @socom-skeleton body SetColor__9C2DBitmapFfff */
/* held from src/gamez/zTwoD/ztwod_bitmap.cpp:266 */
void C2DBitmap::SetColor(f32 red, f32 green, f32 blue)
{
	m_RGB[0][0] = red;
	m_RGB[0][1] = green;
	m_RGB[0][2] = blue;
	m_RGB[1][2] = red;
	m_RGB[1][2] = green;
	m_RGB[2][2] = blue;
}

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

/* @socom-skeleton body Init__3C2DFv */
/* held from src/gamez/zTwoD/ztwod_main.cpp:27 */
void C2D::Init()
{
	m_topx = 1728.0f;
	m_botx = 2368.0f;
	m_topy = 1824.0f;
	m_boty = 2272.0f;
	m_fXPixel = 1.0f / 1280.0f;
	m_fYPixel = 1.0f / 960.0f;
}

/* @socom-skeleton body Open__3C2DFv */
/* held from src/gamez/zTwoD/ztwod_main.cpp:37 */
void C2D::Open()
{
	if (m_p2dcamera == NULL)
		m_p2dcamera = new zdb::CCamera();
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

/* @socom-skeleton body Draw__3C2DFPQ23zdb7CCamera */
/* held from src/gamez/zTwoD/ztwod_main.cpp:59 */
void C2D::Draw(zdb::CCamera* camera)
{
	if (!m_on)
		return;

	for (auto i = begin(); i != end(); ++i)
		(*i)->Draw(camera);
}

/* @socom-skeleton body Enable__3C2DFb */
/* held from src/gamez/zTwoD/ztwod_main.cpp:68 */
void C2D::Enable(bool enable)
{
	m_on = enable;
}

/* @socom-skeleton body SetUseFrameBufferAlpha__3C2DFb */
/* held from src/gamez/zTwoD/ztwod_main.cpp:73 */
void C2D::SetUseFrameBufferAlpha(bool enable)
{
	m_isFrameAlpha = enable;
}

/* @socom-skeleton body IsOn__3C2DCFv */
/* held from src/gamez/zTwoD/ztwod_main.cpp:78 */
bool C2D::IsOn() const
{
	return m_on == true;
}

/* @socom-skeleton body On__3C2DFv */
/* held from src/gamez/zTwoD/ztwod_main.cpp:83 */
void C2D::On()
{
	m_on = true;
}

/* @socom-skeleton body Off__3C2DFv */
/* held from src/gamez/zTwoD/ztwod_main.cpp:88 */
void C2D::Off()
{
	m_on = false;
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
