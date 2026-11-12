#ifndef ZMPEG_H
#define ZMPEG_H

#include <libmpeg.h> /* sceMpeg, sceMpegCbData, sceMpegCbDataStr (PS2 SDK libmpeg; port: port/compat) */

/* port: no DWARF type; the 48-byte resource block rsrcs (0x52cb90) as CMPEG::Init (0x333f90),
 * startPss (0x335440), tickPss (0x335220) and initPssAudio (0x335670) use it. Words +0x20,
 * +0x28 and +0x2c are never accessed. Names invented. */
class playPssRsrcs
{
public:
	unsigned char* mpegBuff;      /* +0x00: decoder work area (sceMpegCreate) */
	int mpegBuffSize;             /* +0x04 */
	unsigned char* rgb32;         /* +0x08: decoded picture, 1024-byte macroblocks */
	unsigned int* path3tag;       /* +0x0c: two GIF DMA chains (one per frame buffer) */
	unsigned char* demuxBuff;     /* +0x10: video bitstream ring (IPU input) */
	int demuxBuffSize;            /* +0x14 */
	unsigned char* audioBuff;     /* +0x18: PCM ring */
	int audioBuffSize;            /* +0x1c */
	int unused_20;
	int iopBuffSize;              /* +0x24: IOP-side PCM buffer (snd_InitMovieSound) */
	int unused_28;
	int unused_2c;
};

/* port: no DWARF type; the 92-byte audioDec (0x52cbc0) as audiodec.cpp (0x334460-0x334c40)
 * uses it. Names invented. */
class AudioDec
{
public:
	int state;                    /* +0x00: 0 header, 1 preset, 2 playing, 3 (stopped) */
	unsigned char hdr[40];        /* +0x04: SShd + SSbd headers */
	int hdrCount;                 /* +0x2c */
	unsigned char* data;          /* +0x30: EE PCM ring */
	int put;                      /* +0x34: ring write position */
	int count;                    /* +0x38: bytes in the ring */
	int size;                     /* +0x3c: ring size */
	int totalBytes;               /* +0x40 */
	int iopBuff;                  /* +0x44: IOP buffer address (snd_InitMovieSound) */
	int iopBuffSize;              /* +0x48 */
	int iopLastPos;               /* +0x4c */
	int iopPausePos;              /* +0x50 */
	int totalBytesSent;           /* +0x54 */
	int unused_58;
};

/* strfile.cpp */
unsigned char strFileOpen(const char *);
unsigned char strFileRewind();
unsigned char strFileClose();
int strFileRead(void *, int);
void setLoadImageTags(unsigned int *, void *, int, int, unsigned int);
void setLoadImageTagsYX(unsigned int *, void *, int, int, int, unsigned int);
void loadImage(unsigned int *);

/* audiodec.cpp */
unsigned char audioDecCreate(AudioDec *, unsigned char *, int, int);
void audioDecReset(AudioDec *);
unsigned char audioDecDelete(AudioDec *);
void audioDecBeginPut(AudioDec *, unsigned char **, int *, unsigned char **, int *);
void audioDecEndPut(AudioDec *, int);
unsigned char audioDecIsPreset(AudioDec *);
void audioDecStart(AudioDec *);
int audioDecSendToIOP(AudioDec *);
int sendToIOP2area(int, int, int, int, unsigned char *, int, unsigned char *, int);

/* playpss.cpp */
void initPssAudio(playPssRsrcs *);
void uninitPssAudio();
sceMpeg* startPss(sceMpeg *, int (*)(void *, int), playPssRsrcs *, unsigned int, unsigned int);
int tickPss(sceMpeg *, playPssRsrcs *, unsigned int);
unsigned char testdonePss(sceMpeg *);
void stopPss(sceMpeg *);
void playPss(int (*)(void *, int), playPssRsrcs *);
int fillBuff(sceMpeg *, int);

extern unsigned char OKtoFillBuff;
extern int _Max_Height;
extern int _Display_Height;

class CMPEG
{
public:
	static void Uninit(); /* port: static - 0x333ec0 uses no object (CCinematicState::UnInit 0x17d90c passes its own this through) */
	/* @socom-skeleton decl 5CMPEG */
public:
	static bool Init(void *, int);
	static bool Run(const char *, bool, bool);
	static void Tick(int);
	static void IdleTick();
	static void End();
	static unsigned char Done();
	static bool Loop(); /* port: static - 0x333ab0 uses no object */
	static void SetMaxHeight(int);
	static void SetDisplayHeight(int);
	/* @socom-skeleton end 5CMPEG */
};
#endif
