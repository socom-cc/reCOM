/* Functional port lane: the PS2 SDK libmpeg interface the game's movie player calls
 * (src/gamez/zMPEG/playpss.cpp; Sony's library is linked into socom.elf at
 * 0x154be8-0x15a4a0 as a provider). Not Sony code and no evidence for the matching lane.
 *
 * Built on what the pinned ps2sdk ships:
 *   - video: ps2sdk's IPU MPEG-1/2 decoder (ee/lib/libmpeg.a: MPEG_Initialize,
 *     MPEG_Picture, MPEG_Destroy). It pulls bitstream through a data callback that must
 *     DMA to the IPU (toIPU, channel 4) - the same contract as the game's no-data
 *     callback (nodataCallback 0x334d80 programs D4 itself), so that callback is called
 *     from here. Pictures come out as RGBA32 16x16 macroblocks in row order; the game
 *     builds its PATH3 chains for column order (setLoadImageTagsYX 0x3356e0), so each
 *     picture is copied into the caller's buffer column by column. ps2sdk's decoder keeps its
 *     reference frames itself, so the work area sceMpegCreate is given (Sony's decoder works
 *     in it) holds that row-ordered output picture when it is large enough (else one is
 *     allocated).
 *   - demultiplexing: a program-stream parser here (pack/system headers, PES packets):
 *     video PES (0xE0 + channel) payloads go to the M2V stream callback, private stream 1
 *     (0xBD, SPU2 PCM) payloads to the PCM callback. A callback answering 0 (no room)
 *     stops the parse; the packet stays unconsumed. Packets cut by the end of a read are
 *     kept here and completed by the next call. After the program end code (0x000001B9)
 *     nothing more is taken.
 * The decoder runs during sceMpegGetPicture only (it uses scratchpad 0x0000-0x3bff, which
 * is saved and restored around it).
 *
 * A fix for the pinned ps2sdk (v2.0.0): its colour conversion (CSC) of a picture runs in
 * chunks of 1023 macroblocks; the chunks after the first are started from its DMAC channel 3
 * handler (_mpeg_dmac_handler), which swaps the two quadword counts (D3, the RGBA32 output,
 * gets the macroblocks' input size, 24 qw each, and D4, the input, gets 64 qw each). A
 * picture of more than 1023 macroblocks (640x448: 1120, the menus' 448-line movies) then
 * leaves 40 qw per macroblock of the second chunk in the IPU output FIFO, the IPU stays busy
 * and the next picture hangs in the decoder's IPU wait. ps2sdk fixed the handler upstream on
 * 2026-11-01 (commit 10c8b450). Here a second channel 3 handler, ahead of ps2sdk's, finishes
 * the second chunk: when D3 stops at the end of the short output count it is restarted for
 * the rest of the picture (ps2sdk's handler is not run for that interrupt); at the picture's
 * end the overlong input transfer is stopped and ps2sdk's handler ends the conversion. Only
 * two chunks (up to 2046 macroblocks) are handled; the disc's movies have at most 1120. */
#define SOCOM_COMPAT_PS2SDK_LIBMPEG
#include <libmpeg.h> /* the Sony-style interface (port/compat/include), then ps2sdk's
                        (MPEG_Initialize, MPEG_Picture, MPEG_Destroy) */
#include <kernel.h>
#include <malloc.h>
#include <string.h>

void socom_port_trace(const char *fmt, ...);

#define D4_CHCR (*(volatile unsigned int *)0x1000b400)
#define D4_MADR (*(volatile unsigned int *)0x1000b410)
#define D4_QWC (*(volatile unsigned int *)0x1000b420)

#define SPR_SAVE_SIZE 0x3c00
#define CARRY_SIZE (65536 + 16)

typedef struct {
    sceMpegCallback cb[7];
    void *cbdata[7];
    sceMpegCallback video;
    void *video_data;
    int video_ch;
    sceMpegCallback pcm;
    void *pcm_data;
    unsigned char *frame; /* decoder output (row-major macroblocks) */
    int frame_size;
    int frame_owned;      /* allocated here (else the caller's work area) */
    unsigned char *work;  /* the caller's decoder work area (sceMpegCreate) */
    int work_size;
    s64 pts;
    int inited;
    int ended;            /* the decoder reached the end */
    int stream_end;       /* the demuxer saw the program end code */
    int pictures;
    int idle;             /* data requests in a row that sent nothing */
    int carry_len;
} mpeg_sys;

static mpeg_sys s_sys;
static unsigned char s_carry[CARRY_SIZE] __attribute__((aligned(64)));
static unsigned char s_spr_save[SPR_SAVE_SIZE] __attribute__((aligned(64)));

/* ---- the CSC second-chunk fix (see the top) ---- */

#define D3_CHCR (*(volatile unsigned int *)0x1000b000)
#define D3_MADR (*(volatile unsigned int *)0x1000b010)
#define D3_QWC (*(volatile unsigned int *)0x1000b020)
#define D_ENABLER (*(volatile unsigned int *)0x1000f520)
#define D_ENABLEW (*(volatile unsigned int *)0x1000f590)
#define CSC_CHUNK 0x3ff

static unsigned int s_csc_dst;  /* the picture's RGBA32 output (physical) */
static int s_csc_mbs;           /* its macroblocks */
static int s_csc_id = -1;       /* the handler's id */
static volatile int s_csc_fixed; /* second chunks finished here */

static int csc_fix_handler(int channel, void *arg, void *addr)
{
    unsigned int madr, short_end, end;
    int n = s_csc_mbs - CSC_CHUNK;

    (void)channel;
    (void)arg;
    (void)addr;
    if (s_csc_dst == 0 || n <= 0 || n > CSC_CHUNK)
        return 0;
    madr = D3_MADR & 0x0fffffff;
    short_end = s_csc_dst + (CSC_CHUNK * 64 + n * 24) * 16;
    end = s_csc_dst + s_csc_mbs * 1024;
    if (madr == short_end) {
        /* the rest of the second chunk's output; ps2sdk's handler would end the CSC here */
        D3_QWC = (end - short_end) >> 4;
        D3_CHCR = 0x100;
        return -1;
    }
    if (madr == end && D4_QWC != 0) {
        /* the input count was 64 qw a macroblock: stop the rest (the IPU took what the CSC
         * needed; ps2sdk's resume clears the input FIFO with BCLR) */
        D_ENABLEW = D_ENABLER | 0x10000;
        D4_CHCR &= ~0x100u;
        D4_QWC = 0;
        D_ENABLEW = D_ENABLER & ~0x10000u;
        s_csc_fixed++;
    }
    return 0;
}

static void csc_fix_add(void)
{
    s_csc_id = AddDmacHandler2(3, csc_fix_handler, 0, NULL);
}

static void csc_fix_remove(void)
{
    if (s_csc_id >= 0)
        RemoveDmacHandler(3, s_csc_id);
    s_csc_id = -1;
    s_csc_dst = 0;
}

/* ---- decoder side ---- */

static void *init_cb(void *param, MPEGSequenceInfo *si)
{
    sceMpeg *mp = (sceMpeg *)param;
    mpeg_sys *sys = (mpeg_sys *)mp->sys;
    int size = ((si->m_Width + 15) & ~15) * ((si->m_Height + 15) & ~15) * 4;

    mp->width = si->m_Width;
    mp->height = si->m_Height;
    if (sys->frame == NULL || sys->frame_size < size) {
        if (sys->frame != NULL && sys->frame_owned)
            free(sys->frame);
        if (sys->work != NULL && sys->work_size >= size && ((unsigned int)sys->work & 63) == 0) {
            /* Sony's decoder works in the caller's area (2880 bytes a line + 5992); ps2sdk's keeps
             * its own reference frames, so the area holds the output picture (w * h * 4) */
            sys->frame = sys->work;
            sys->frame_size = sys->work_size;
            sys->frame_owned = 0;
        } else {
            sys->frame = (unsigned char *)memalign(64, size);
            sys->frame_size = size;
            sys->frame_owned = 1;
        }
    }
    s_csc_dst = (unsigned int)sys->frame & 0x0fffffff;
    s_csc_mbs = ((si->m_Width + 15) >> 4) * ((si->m_Height + 15) >> 4);
    socom_port_trace("MPEG: sequence %dx%d, %d ms per frame, output %p", si->m_Width, si->m_Height,
        si->m_MSPerFrame, sys->frame);
    return sys->frame;
}

/* the decoder wants bitstream in the IPU: the game's no-data callback DMAs the next piece
 * of its video ring; 0 (end of data) once the stream has ended and nothing more comes, or
 * when nothing has come for a long time (no hang in the port) */
static int data_cb(void *param)
{
    sceMpeg *mp = (sceMpeg *)param;
    mpeg_sys *sys = (mpeg_sys *)mp->sys;
    sceMpegCbData cbd;
    unsigned int madr = D4_MADR;

    if (sys->cb[sceMpegCbNodata] == NULL)
        return 0;
    cbd.type = sceMpegCbNodata;
    cbd.mp = mp;
    sys->cb[sceMpegCbNodata](mp, &cbd, sys->cbdata[sceMpegCbNodata]);
    if ((D4_CHCR & 0x100) || D4_QWC != 0 || D4_MADR != madr) {
        sys->idle = 0;
        return 1;
    }
    sys->idle++;
    if (sys->stream_end && sys->idle > 8)
        return 0;
    if (sys->idle > 4000) {
        socom_port_trace("MPEG: no bitstream for %d requests: ending the movie", sys->idle);
        return 0;
    }
    return 1;
}

int sceMpegInit(void)
{
    return 0;
}

int sceMpegCreate(sceMpeg *mp, unsigned char *work_area, int work_area_size)
{
    if (s_sys.inited) {
        csc_fix_remove();
        MPEG_Destroy();
        s_sys.inited = 0;
    }
    if (s_sys.frame != NULL && s_sys.frame_owned)
        free(s_sys.frame);
    memset(&s_sys, 0, sizeof(s_sys));
    s_sys.work = work_area;
    s_sys.work_size = work_area_size;
    mp->sys = &s_sys;
    mp->width = 0;
    mp->height = 0;
    mp->frameCount = 0;
    MPEG_Initialize(data_cb, mp, init_cb, mp, &s_sys.pts);
    csc_fix_add(); /* after ps2sdk's channel 3 handler, so it runs first */
    s_sys.inited = 1;
    return 0;
}

int sceMpegReset(sceMpeg *mp)
{
    (void)mp;
    D4_CHCR &= ~0x100u; /* stop feeding the IPU */
    return 0;
}

int sceMpegDelete(sceMpeg *mp)
{
    mpeg_sys *sys = (mpeg_sys *)mp->sys;

    if (sys == NULL)
        return 0;
    if (sys->inited) {
        csc_fix_remove();
        MPEG_Destroy();
        sys->inited = 0;
    }
    if (sys->frame != NULL) {
        if (sys->frame_owned)
            free(sys->frame);
        sys->frame = NULL;
    }
    socom_port_trace("MPEG: decoder closed after %d pictures", sys->pictures);
    return 0;
}

int sceMpegIsEnd(sceMpeg *mp)
{
    mpeg_sys *sys = (mpeg_sys *)mp->sys;
    return sys != NULL && sys->ended;
}

sceMpegCallback sceMpegAddCallback(sceMpeg *mp, sceMpegCbType type, sceMpegCallback callback, void *anyData)
{
    mpeg_sys *sys = (mpeg_sys *)mp->sys;
    sceMpegCallback old;

    if ((unsigned int)type >= 7)
        return NULL;
    old = sys->cb[type];
    sys->cb[type] = callback;
    sys->cbdata[type] = anyData;
    return old;
}

sceMpegCallback sceMpegAddStrCallback(sceMpeg *mp, sceMpegStrType strType, int ch, sceMpegCallback callback, void *anyData)
{
    mpeg_sys *sys = (mpeg_sys *)mp->sys;
    sceMpegCallback old = NULL;

    if (strType == sceMpegStrM2V) {
        old = sys->video;
        sys->video = callback;
        sys->video_data = anyData;
        sys->video_ch = ch;
    } else if (strType == sceMpegStrPCM) {
        old = sys->pcm;
        sys->pcm = callback;
        sys->pcm_data = anyData;
    }
    return old;
}

/* one picture into rgb32 (column-major macroblocks, at most mbcount); 0, also at the end */
int sceMpegGetPicture(sceMpeg *mp, void *rgb32, int mbcount)
{
    mpeg_sys *sys = (mpeg_sys *)mp->sys;
    unsigned char *dst = (unsigned char *)rgb32;
    int got, mbw, mbh, x, y, n, fixed;

    if (sys->ended)
        return 0;
    if (sys->cb[sceMpegCbBackground] != NULL) {
        sceMpegCbData cbd;
        cbd.type = sceMpegCbBackground;
        cbd.mp = mp;
        sys->cb[sceMpegCbBackground](mp, &cbd, sys->cbdata[sceMpegCbBackground]);
    }

    if (sys->frame != NULL) {
        s_csc_dst = (unsigned int)sys->frame & 0x0fffffff;
        s_csc_mbs = ((mp->width + 15) >> 4) * ((mp->height + 15) >> 4);
    }
    fixed = s_csc_fixed;
    memcpy(s_spr_save, (void *)0x70000000, SPR_SAVE_SIZE);
    got = MPEG_Picture(sys->frame, &sys->pts);
    memcpy((void *)0x70000000, s_spr_save, SPR_SAVE_SIZE);

    if (!got) {
        sys->ended = 1;
        socom_port_trace("MPEG: end of video after %d pictures", sys->pictures);
        return 0;
    }

    if (fixed == 0 && s_csc_fixed != 0)
        socom_port_trace("MPEG: %d macroblocks a picture: the colour conversion's second chunk finished here (ps2sdk 2.0.0 handler)", s_csc_mbs);
    mp->frameCount = sys->pictures++;
    mp->pts = sys->pts;
    mbw = (mp->width + 15) >> 4;
    mbh = (mp->height + 15) >> 4;
    InvalidDCache(sys->frame, sys->frame + mbw * mbh * 1024 - 1);
    n = 0;
    for (x = 0; x < mbw; x++)
        for (y = 0; y < mbh; y++) {
            if (n >= mbcount)
                break;
            memcpy(dst + n * 1024, sys->frame + (y * mbw + x) * 1024, 1024);
            n++;
        }
    SyncDCache(dst, dst + n * 1024 - 1);
    return 0;
}

/* ---- program stream demultiplexer ---- */

/* bytes of the unit (pack header, end code, PES packet) starting at p, or -1 while its
 * header is incomplete, 0 when p is not at a start code */
static int unit_length(const unsigned char *p, int avail)
{
    if (avail < 4)
        return -1;
    if (p[0] != 0 || p[1] != 0 || p[2] != 1)
        return 0;
    if (p[3] == 0xb9)
        return 4;
    if (p[3] == 0xba) {
        if (avail < 5)
            return -1;
        if ((p[4] >> 6) == 1) {
            if (avail < 14)
                return -1;
            return 14 + (p[13] & 7);
        }
        return 12;
    }
    if (p[3] < 0xbb)
        return 0;
    if (avail < 6)
        return -1;
    return 6 + (p[4] << 8 | p[5]);
}

/* a PES packet's payload: MPEG-2 header (10xx xxxx), else MPEG-1 (stuffing, STD, PTS/DTS) */
static int pes_payload(const unsigned char *p, int len, const unsigned char **data, s64 *pts)
{
    int i = 6;

    *pts = -1;
    if (len > 9 && (p[6] >> 6) == 2) {
        int hl = p[8];
        if (p[7] & 0x80)
            *pts = (s64)((p[9] >> 1) & 7) << 30 | (s64)p[10] << 22 | (s64)(p[11] >> 1) << 15 |
                   (s64)p[12] << 7 | (s64)(p[13] >> 1);
        i = 9 + hl;
    } else {
        while (i < len && p[i] == 0xff)
            i++;
        if (i < len && (p[i] >> 6) == 1)
            i += 2;
        if (i < len && (p[i] >> 4) == 2)
            i += 5;
        else if (i < len && (p[i] >> 4) == 3)
            i += 10;
        else
            i++;
    }
    if (i > len)
        i = len;
    *data = p + i;
    return len - i;
}

/* 1 = consumed, 0 = refused by a stream callback */
static int dispatch(sceMpeg *mp, mpeg_sys *sys, const unsigned char *p, int len)
{
    sceMpegCbDataStr rec;
    sceMpegCallback cb = NULL;
    void *data = NULL;
    int id = p[3];

    if (id == 0xb9) {
        sys->stream_end = 1;
        socom_port_trace("MPEG: program end code");
        return 1;
    }
    if (id == 0xe0 + (sys->video_ch & 0xf) && sys->video != NULL) {
        cb = sys->video;
        data = sys->video_data;
        rec.type = (sceMpegCbType)sceMpegCbStr;
    } else if (id == 0xbd && sys->pcm != NULL) {
        cb = sys->pcm;
        data = sys->pcm_data;
        rec.type = (sceMpegCbType)sceMpegCbStr;
    }
    if (cb == NULL)
        return 1;
    rec.mp = mp;
    rec.len = (unsigned int)pes_payload(p, len, (const unsigned char **)&rec.data, &rec.pts);
    rec.dts = -1;
    return cb(mp, (sceMpegCbData *)&rec, data) != 0;
}

int sceMpegDemuxPss(sceMpeg *mp, unsigned char *pss, int pss_size)
{
    mpeg_sys *sys = (mpeg_sys *)mp->sys;
    int pos = 0;

    if (sys->stream_end)
        return 0;

    /* finish a packet cut by the previous read */
    while (sys->carry_len > 0) {
        int need = unit_length(s_carry, sys->carry_len);
        if (need < 0 || need > sys->carry_len) {
            int want = need < 0 ? 16 : need - sys->carry_len;
            if (want > pss_size - pos)
                want = pss_size - pos;
            if (sys->carry_len + want > CARRY_SIZE)
                want = CARRY_SIZE - sys->carry_len;
            if (want <= 0)
                return pos;
            memcpy(s_carry + sys->carry_len, pss + pos, want);
            sys->carry_len += want;
            pos += want;
            continue;
        }
        if (need == 0) { /* not a start code: drop a byte */
            memmove(s_carry, s_carry + 1, --sys->carry_len);
            continue;
        }
        if (!dispatch(mp, sys, s_carry, need))
            return pos;
        memmove(s_carry, s_carry + need, sys->carry_len - need);
        sys->carry_len -= need;
        if (sys->stream_end) {
            sys->carry_len = 0;
            return pss_size;
        }
    }

    while (pos < pss_size) {
        int len = unit_length(pss + pos, pss_size - pos);
        if (len == 0) {
            pos++;
            continue;
        }
        if (len < 0 || pos + len > pss_size) {
            int rest = pss_size - pos;
            if (rest > CARRY_SIZE)
                rest = CARRY_SIZE;
            memcpy(s_carry, pss + pos, rest);
            sys->carry_len = rest;
            return pos + rest;
        }
        if (!dispatch(mp, sys, pss + pos, len))
            return pos;
        pos += len;
        if (sys->stream_end)
            return pss_size;
    }
    return pos;
}
