#ifndef ZVIDEO_H
#define ZVIDEO_H

#include "gamez/zMath/zmath.h"

class _zvid_public;

class CValve;
class CWindow;
class CRdrFile;

enum _zvid_mode
{
	ZVID_MODE_NTSC,
	ZVID_MODE_PAL,
	ZVID_MODE_DTV480P,
	ZVID_MODE_NUM
};

void zVid_Init(_zvid_mode mode);
void zVid_Uninit();
void zVid_Open();
void zVid_Swap(bool doSwap);
void zVid_FrameRestore();
void zVid_ClearColor(u32* color); /* port: binary has only zVid_ClearColor__FPUi */
void SetGSReg(short reg, u64 value); /* port: SetGSReg__FsUl (0x308500); MW unsigned long is 64-bit */
void zVid_Sync0();
void zVid_ZTestOn();
void zVid_ZTestOff();
void zVid_ZTestOnWriteSet(bool set);

void zvid_MpegReset();
void zvid_SetVideoMode(_zvid_mode mode, bool sync); /* port: zvid_SetVideoMode__F10_zvid_modeb */

void uninitPssAudio();

extern bool doAudio;
extern _zvid_public zVid;

#include <libgraph.h> /* sceGsDBuff */

/* port: no DWARF type for zvid (624 bytes at 0x511040); layout from its accesses in
 * zvid_SetVideoMode (0x3087e0), zVid_Init (0x308690), zVid_Open (0x308590) and
 * zVid_Swap (0x307bc0). Member names are invented. */
struct _zvid_private
{
	sceGsDBuff db;                /* 0x000: sceGsSetDefDBuff target */
	u32 vsync_odd;                /* 0x230: !sceGsSyncV() of the last swap */
	u16* frame_fbp;               /* 0x234: framecode FBP field (framecode + 0x30) */
	u16* frame_fbmsk;             /* 0x238: framecode + 0x44, set to 0x7200 each swap */
	u32 pad_23c[2];
	u16* frame_restore;           /* 0x244: framecode + 0x80 */
	u32 interlace;                /* 0x248: sceGsResetGraph inter */
	u32 field_mode;               /* 0x24c: sceGsResetGraph ffmode (SMODE2.FFMD) */
	u32 output_mode;              /* 0x250: sceGsResetGraph omode */
	u32 draw_psm;                 /* 0x254: sceGsSetDefDBuff psm */
	u32 disp_psm;                 /* 0x258: DISPFB PSM */
	u32 display_height;           /* 0x25c */
	u32 bgcolor;                  /* 0x260: RGBA; alpha 0xff selects PMODE 0x62 */
	u32 pad_264[3];
};

extern _zvid_private zvid;
extern CWindow* theWindow;

extern CValve* lodLevel;

class _zvid_public
{
public:
	u32 wideFrameFlag;

	bool showTextureBuffer;
	bool showTextureBufferFormat;

	s64 frameNumber;
	u32 frameRate;
	f32 frameTime;
	f32 runTime;
	f32 procTime;

	f32 aspect[2];
	u32 displayBuf; /* DWARF uint: GS frame buffer page (FBP) */
	u32 renderBuf;
	u32 renderWidth;
	u32 renderHeight;
	f32 minZ;
	f32 maxZ;

	u32 textureBaseAddr;
	u32 textureEndAddr;

	_zvid_mode videoMode;
	_zvid_mode vidMode;

	f32 hblnkRate;

	bool doMpeg224;

	bool pcrtcDo;
	IPNT2D pcrtcOffset;

	u16* ztest_on; /* DWARF uint16 * (VIF packets ztest_on_vif / ztest_off_vif) */
	u16* ztest_off;

	s64 dmaFrameRestore;
};

class CVideo
{
public:
	static void Clear(u8 r, u8 g, u8 b, u8 a) { }
	static f32 MaxFrameRate(s32 fr);

	static s32 m_defaultFrameRate;
	/* @socom-skeleton decl 6CVideo */
public:
	void Fade(float, unsigned char, unsigned char, unsigned char);
	static void RestoreImage(char *);
	void ReadGsMemory(unsigned int, unsigned __int128 *, unsigned int);
	void WriteGsMemory(unsigned int, unsigned __int128 *, unsigned int);
	/* @socom-skeleton end 6CVideo */
};
#endif