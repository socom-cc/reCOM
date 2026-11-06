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
void zVid_ClearColor(f32 red, f32 green, f32 blue); /* port: unproven, no such symbol in the binary; kept for existing callers */
void zVid_Sync0();
void zVid_ZTestOn();
void zVid_ZTestOff();
void zVid_ZTestOnWriteSet(bool set);

void zvid_MpegReset();
void zvid_SetVideoMode(_zvid_mode mode, bool sync); /* port: zvid_SetVideoMode__F10_zvid_modeb */

void uninitPssAudio();

extern bool doAudio;
extern _zvid_public zVid;
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
	void* displayBuf;
	void* renderBuf;
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

	s64 ztest_on;
	s64 ztest_off;

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