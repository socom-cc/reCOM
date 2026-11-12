/*
 * Port compatibility: the PS2 SDK libmpeg interface the game's movie player uses
 * (src/gamez/zMPEG: playpss.cpp, zmpeg.cpp). The reference ELF links Sony's libmpeg
 * (0x154be8-0x15a4a0, provider); the pinned ps2sdk has no such library, so
 * port/compat/libmpeg.c implements this interface over ps2sdk's own IPU decoder
 * (ps2sdk ee/lib/libmpeg.a, MPEG_Initialize/MPEG_Picture) and a program-stream demuxer.
 *
 * Only the members the game reads are given meaning (offsets from the ELF: tickPss
 * 0x335220 reads width +0, height +4, frameCount +8; audioCallback 0x334ec0 and
 * videoCallback 0x334fb0 read data +8 and len +12 of the stream callback record).
 * The game allocates sceMpeg itself (72 bytes, playPss 0x3350b0 / CMPEG::Run 0x333e64).
 */
#ifndef SOCOM_COMPAT_LIBMPEG_H
#define SOCOM_COMPAT_LIBMPEG_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct sceMpeg {
	int width;           /* +0x00 picture width (pixels) */
	int height;          /* +0x04 picture height */
	int frameCount;      /* +0x08 pictures returned before the last one */
	int pad0c;
	long long pts;       /* +0x10 */
	long long dts;       /* +0x18 */
	unsigned long long flags; /* +0x20 */
	long long pts2nd;    /* +0x28 */
	long long dts2nd;    /* +0x30 */
	unsigned long long flags2nd; /* +0x38 */
	void *sys;           /* +0x40 decoder state (port/compat/libmpeg.c) */
	int pad44;
} sceMpeg;

/* callback types (sceMpegAddCallback 0x159878: error 0, nodata 1, background 4) */
typedef enum {
	sceMpegCbError = 0,
	sceMpegCbNodata = 1,
	sceMpegCbStopDMA = 2,
	sceMpegCbRestartDMA = 3,
	sceMpegCbBackground = 4,
	sceMpegCbTimeStamp = 5,
	sceMpegCbStr = 6
} sceMpegCbType;

/* elementary stream types (sceMpegAddStrCallback 0x158b50: video 0, PCM 2) */
typedef enum {
	sceMpegStrM2V = 0,
	sceMpegStrIPU = 1,
	sceMpegStrPCM = 2,
	sceMpegStrADPCM = 3,
	sceMpegStrDATA = 4
} sceMpegStrType;

typedef struct sceMpegCbData {
	sceMpegCbType type;
	sceMpeg *mp;
} sceMpegCbData;

typedef struct sceMpegCbDataStr {
	sceMpegCbType type;  /* +0x00 */
	sceMpeg *mp;         /* +0x04 */
	unsigned char *data; /* +0x08 PES payload */
	unsigned int len;    /* +0x0c */
	long long pts;
	long long dts;
} sceMpegCbDataStr;

typedef int (*sceMpegCallback)(sceMpeg *mp, sceMpegCbData *cbdata, void *anyData);

int sceMpegInit(void);
int sceMpegCreate(sceMpeg *mp, unsigned char *work_area, int work_area_size);
int sceMpegDelete(sceMpeg *mp);
int sceMpegReset(sceMpeg *mp);
int sceMpegGetPicture(sceMpeg *mp, void *rgb32, int mbcount);
int sceMpegIsEnd(sceMpeg *mp);
sceMpegCallback sceMpegAddCallback(sceMpeg *mp, sceMpegCbType type, sceMpegCallback callback, void *anyData);
sceMpegCallback sceMpegAddStrCallback(sceMpeg *mp, sceMpegStrType strType, int ch, sceMpegCallback callback, void *anyData);
int sceMpegDemuxPss(sceMpeg *mp, unsigned char *pss, int pss_size);

#ifdef __cplusplus
}
#endif

#endif

/* port/compat/libmpeg.c also needs ps2sdk's own libmpeg.h (same file name, later in the
 * include path) */
#if defined(SOCOM_COMPAT_PS2SDK_LIBMPEG) && !defined(__LIBMPEG_H__)
#include_next <libmpeg.h>
#endif
