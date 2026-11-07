/* Functional port lane: the EE half of SCEA's 989snd sound library, rewritten for ps2sdk.
 * Not Sony/989 Studios code; nothing here is evidence for the matching lane.
 *
 * Provider: socom.elf links 989snd's EE client (989snd.c, 0x2ea400-0x2ebd20). The IOP
 * half is the disc's RUN\IRX\SOUND\989SND.IRX (snd989 1.08, "989snd v2.9.0"), loaded with
 * 989DSTRM.IRX, LIBSD.IRX and SDRDRV.IRX by CIOPManager::RebootIOP (0x2f4e90). This file
 * is the client side of that module's two SIF RPC servers, rebuilt from the ELF's code:
 *
 *   0x123456  commands. rpc 77 sends a batch buffer; any other rpc number runs that one
 *             command at once ("AndWait", or a data-less command with no callback).
 *   0x123457  bank loader. rpc 2 = load by file name, rpc 3 = load by CD location.
 *
 * Batch buffer (2 x 4096 bytes, filled alternately): word 0 = command count (<= 256),
 * then per command a 16-bit id, a 16-bit data size and the data, padded to 4 bytes.
 * The IOP answers into a return buffer of count + 2 words: word 0 and word count + 1 are
 * set to -1 when the answer is complete, words 1..count are the commands' results, and
 * each command's completion callback (if any) gets its result in snd_FlushSoundCommands.
 * Single commands answer into 3 words the same way (result in word 1). Bank loads answer
 * one word (the bank handle, 0 = failure) into a slot preset to -1.
 *
 * Port deviations (behaviour kept, mechanism changed):
 *  - the words the IOP writes by DMA (return buffers, gStats, the load result) are read
 *    and written through the uncached segment instead of relying on FlushCache(0) before
 *    each read; the original FlushCache(0) calls stay where 989snd.c has them;
 *  - each IOP-written buffer sits in its own 64-byte block;
 *  - the library's printf messages go to the port trace with an "SND:" prefix. */
#include <kernel.h>
#include <sifrpc.h>
#include <stdio.h>
#include <string.h>
#include <989snd.h>

void socom_port_trace(const char *fmt, ...);

#define SND_RPC_COMMANDS 0x123456
#define SND_RPC_LOADER   0x123457
#define SND_RPC_BATCH    77
#define SND_BUFFER_BYTES 4096
#define SND_MAX_COMMANDS 256

/* Uncached view of a word the IOP writes by SIF DMA. */
#define SND_UNCACHED(p) ((volatile int *)UNCACHED_SEG(p))

typedef struct
{
    SndCompleteProc proc;
    unsigned long user;
} SndReturnDef;

/* 0x509b50 / 0x50e5a0 */
static SifRpcClientData_t gSLClientData __attribute__((aligned(64)));
static SifRpcClientData_t gSLClientLoaderData __attribute__((aligned(64)));
/* 0x509b80: single-command answer {-1, result, -1} */
static int gSyncBuffer[16] __attribute__((aligned(64)));
/* 0x509bc0: single-command data */
static unsigned char gSyncSendBuffer[64] __attribute__((aligned(64)));
/* 0x509c00: snd_BankLoad request {flags, name} */
static unsigned char gSyncStringBuffer[256] __attribute__((aligned(64)));
/* 0x509d00 / 0x50ad00 */
static int gSndCommandBuffer1[SND_BUFFER_BYTES / 4] __attribute__((aligned(64)));
static int gSndCommandBuffer2[SND_BUFFER_BYTES / 4] __attribute__((aligned(64)));
/* 0x50bd00 / 0x50cd00 (EE only: callbacks of the queued commands) */
static SndReturnDef gSndCommandReturnDef1[SND_MAX_COMMANDS];
static SndReturnDef gSndCommandReturnDef2[SND_MAX_COMMANDS];
/* 0x50dd00 / 0x50e140: 0x440 bytes each */
static int gActualReturnValues1[272] __attribute__((aligned(64)));
static int gActualReturnValues2[272] __attribute__((aligned(64)));
/* 0x50e580: IOP status block; word 0 = CD read in progress, word 4 = CD error */
static int gStats[16] __attribute__((aligned(64)));
/* 0x50e600 / 0x50e640 */
static int gLoadReturnValue[16] __attribute__((aligned(64)));
static int gLoadParams[16] __attribute__((aligned(64)));
/* 0x43a640 */
static SndReturnDef gLoadReturnDef;

/* 0x475370.. (sdata) */
static int *gSndCommandBuffePtr[2];
static int gCommandBuffeBytesAvail[2];
static SndReturnDef *gSndCommandReturnDefPtr[2];
static int *gReturnValuesPtr[2];

/* 0x476404.. (sbss) */
static volatile int *gCommBusy;
static int gAwaitingInts;
static int gStreamingInited;
static void (*gCdCallback)(int);
static int gSSRead;
static int gSSReadDone;
static int gLoadingFromFS;
static int gCommandFillBuffer;
static int gCaching;
static int gLoadBusy;
static SndCompleteProc gLoadCB;
static unsigned long gLoadUserData;

static int snd_trace_plays[3]; /* port: first plays traced (one-shot, with callback, stream) */
#ifdef SOCOM_PORT_SOUND_PROBE
static int snd_probe_counts[80]; /* commands queued, by id */
#endif
#ifdef SOCOM_PORT_SOUND_PROBE
static void snd_ProbeFrame(void);
#endif

/* The answer gCommBusy points at is complete (989snd.c tests this inline). */
static int snd_CommandDone(void)
{
    volatile int *busy = gCommBusy;

    if (busy == NULL)
        return 1;

    busy = SND_UNCACHED(busy);

    if (busy[0] == -1 && busy[gAwaitingInts + 1] == -1)
    {
        gCommBusy = NULL;
        return 1;
    }

    return 0;
}

/* CD read issued through the IOP finished (gStats word 0 back to 0). */
static int snd_StatsCdIdle(void)
{
    return SND_UNCACHED(gStats)[0] == 0;
}

static void snd_WaitClientIdle(SifRpcClientData_t *client, int flush)
{
    while (sceSifCheckStatRpc(client))
    {
        socom_port_trace("SND: 989snd.c: RPC collision!");
        if (flush)
            snd_FlushSoundCommands();
        FlushCache(0);
    }
}

/* Send the filling batch buffer and switch to the other one (inline in 0x2eb108 and
 * 0x2eba18). */
static void snd_SendFillBuffer(void)
{
    int fill = gCommandFillBuffer;
    int count = gSndCommandBuffePtr[fill][0];
    volatile int *answer = SND_UNCACHED(gReturnValuesPtr[fill]);

    gAwaitingInts = count;
    gCommBusy = gReturnValuesPtr[fill];
    answer[count + 1] = 0;
    answer[0] = 0;
    snd_WaitClientIdle(&gSLClientData, 0);
    sceSifCallRpc(&gSLClientData, SND_RPC_BATCH, SIF_RPC_M_NOWAIT, gSndCommandBuffePtr[fill],
        SND_BUFFER_BYTES - gCommandBuffeBytesAvail[fill], gReturnValuesPtr[fill], count * 4 + 8, NULL, NULL);
    gCommandFillBuffer = fill == 1 ? 0 : 1;
    gSndCommandBuffePtr[gCommandFillBuffer][0] = 0;
    gCommandBuffeBytesAvail[gCommandFillBuffer] = SND_BUFFER_BYTES - 4;
}

/* 0x2ebb70 */
int snd_StartSoundSystem(void)
{
    void *stats = gStats;
    int r;

    gSndCommandBuffePtr[0] = gSndCommandBuffer1;
    gSndCommandBuffePtr[1] = gSndCommandBuffer2;
    gReturnValuesPtr[0] = gActualReturnValues1;
    gReturnValuesPtr[1] = gActualReturnValues2;
    gSndCommandReturnDefPtr[0] = gSndCommandReturnDef1;
    gSndCommandReturnDefPtr[1] = gSndCommandReturnDef2;
    sceSifInitRpc(0);

    do
    {
        volatile int delay;

        if (sceSifBindRpc(&gSLClientData, SND_RPC_COMMANDS, 0) < 0)
        {
            socom_port_trace("SND: error: sceSifBindRpc in %s, at line %d", "989snd.c", 109);
            for (;;)
                ;
        }

        for (delay = 10000; delay--;)
            ;
    } while (gSLClientData.server == NULL);

    gLoadBusy = 0;
    gLoadReturnDef.proc = NULL;
    gLoadReturnDef.user = 0;
    SND_UNCACHED(gLoadReturnValue)[0] = 0;

    do
    {
        volatile int delay;

        if (sceSifBindRpc(&gSLClientLoaderData, SND_RPC_LOADER, 0) < 0)
        {
            socom_port_trace("SND: error: sceSifBindRpc in %s, at line %d", "989snd.c", 130);
            for (;;)
                ;
        }

        for (delay = 10000; delay--;)
            ;
    } while (gSLClientLoaderData.server == NULL);

    SND_UNCACHED(gStats)[0] = 0;
    SND_UNCACHED(gStats)[4] = 0;
    gCommandBuffeBytesAvail[0] = SND_BUFFER_BYTES - 4;
    gSndCommandBuffer1[0] = 0;
    gCommandBuffeBytesAvail[1] = SND_BUFFER_BYTES - 4;
    gSndCommandBuffer2[0] = 0;
    r = snd_SendIOPCommandAndWait(0, 4, (char *)&stats);
    socom_port_trace("SND: sound system started (RPC 0x%x and 0x%x bound, start -> %d)", SND_RPC_COMMANDS, SND_RPC_LOADER, r);
    return r;
}

/* 0x2eb7c0 */
int snd_StopSoundSystem(void)
{
    int r = snd_SendIOPCommandAndWait(1, 0, NULL);
    gStreamingInited = 0;
    return r;
}

/* 0x2eaaa0 */
void snd_SendIOPCommandNoWait(int command, int size, char *data, SndCompleteProc proc, unsigned long user)
{
    int restoreCaching = 0;
    int waits = 0;
    int bytes;
    int fill;
    int count;
    char *entry;
    int i;

    if (!gCaching && gCommBusy == NULL && size == 0 && proc == NULL)
    {
        /* a data-less command without callback runs as its own call */
        gAwaitingInts = 1;
        SND_UNCACHED(gSyncBuffer)[2] = 0;
        gCommBusy = gSyncBuffer;
        SND_UNCACHED(gSyncBuffer)[0] = 0;
        snd_WaitClientIdle(&gSLClientData, 1);
        sceSifCallRpc(&gSLClientData, command, SIF_RPC_M_NOWAIT, NULL, 0, gSyncBuffer, 12, NULL, NULL);
        return;
    }

    bytes = size + 4;
    if (bytes % 4)
        bytes += 4 - bytes % 4;

    while (gSndCommandBuffePtr[gCommandFillBuffer][0] == SND_MAX_COMMANDS || gCommandBuffeBytesAvail[gCommandFillBuffer] < bytes)
    {
        if (gCaching)
        {
            gCaching = 0;
            restoreCaching = 1;
        }

        snd_FlushSoundCommands();

        if (waits == 1)
            socom_port_trace("SND: snd_SendIOPCommandNoWait: BUFFER %d FULL(%d)! Sound stalled waiting for IOP comands to finish!",
                gCommandFillBuffer, gSndCommandBuffePtr[gCommandFillBuffer][0]);

        waits++;

        if (waits % 5000 == 0)
            socom_port_trace("SND: waiting in snd_SendIOPCommandNoWait loop for 5000 loops");
    }

    if (waits)
        socom_port_trace("SND: snd_SendIOPCommandNoWait: continueing (%d).", waits);

    if (restoreCaching)
        gCaching = 1;

#ifdef SOCOM_PORT_SOUND_PROBE
    if (command >= 0 && command < 80)
        snd_probe_counts[command]++;
#endif
    fill = gCommandFillBuffer;
    entry = (char *)gSndCommandBuffePtr[fill] + (SND_BUFFER_BYTES - 4 - gCommandBuffeBytesAvail[fill]) + 4;
    ((short *)entry)[0] = (short)command;
    ((short *)entry)[1] = (short)size;

    for (i = 0; i < size; i++)
        entry[4 + i] = data[i];

    gCommandBuffeBytesAvail[fill] -= bytes;
    count = gSndCommandBuffePtr[fill][0];
    gSndCommandReturnDefPtr[fill][count].proc = proc;
    gSndCommandReturnDefPtr[fill][count].user = user;
    gSndCommandBuffePtr[fill][0] = count + 1;
    snd_FlushSoundCommands();
}

/* 0x2eae30 */
int snd_SendIOPCommandAndWait(int command, int size, char *data)
{
    long long waits = 0;
    int result;
    int i;

    for (i = 0; i < size; i++)
        gSyncSendBuffer[i] = data[i];

    while (gCommBusy != NULL)
    {
        snd_FlushSoundCommands();
        FlushCache(0);
        waits++;

        if (waits % 5000 == 0)
            socom_port_trace("SND: waiting in snd_SendIOPCommandAndWait loop for 5000 loops");
    }

    gAwaitingInts = 1;
    SND_UNCACHED(gSyncBuffer)[2] = 0;
    gCommBusy = gSyncBuffer;
    SND_UNCACHED(gSyncBuffer)[0] = 0;
    snd_WaitClientIdle(&gSLClientData, 1);

    if (size != 0)
        sceSifCallRpc(&gSLClientData, command, SIF_RPC_M_NOWAIT, gSyncSendBuffer, size, gSyncBuffer, 12, NULL, NULL);
    else
        sceSifCallRpc(&gSLClientData, command, SIF_RPC_M_NOWAIT, NULL, 0, gSyncBuffer, 12, NULL, NULL);

    do
        FlushCache(0);
    while (!snd_CommandDone());

    result = SND_UNCACHED(gSyncBuffer)[1];

    if (gSndCommandBuffePtr[gCommandFillBuffer][0] != 0 && !gCaching)
        snd_SendFillBuffer();

    return result;
}

/* 0x2eb7f0: completion callbacks of a finished answer, the bank-load callback, the
 * next batch, and the IOP CD read callback; returns whether a call is outstanding. */
int snd_FlushSoundCommands(void)
{
    if (gCommBusy != NULL)
    {
        FlushCache(0);

        if (snd_CommandDone())
        {
            if (gLoadingFromFS)
            {
                if (gLoadCB != NULL)
                    gLoadCB(SND_UNCACHED(gSyncBuffer)[1], gLoadUserData);

                gLoadCB = NULL;
                gLoadingFromFS = 0;
            }
            else
            {
                /* ELF quirk: this also runs after a single-command answer, so the last
                 * batch's callbacks then get their (old) results again. */
                int sent = gCommandFillBuffer == 1 ? 0 : 1;
                int count = gSndCommandBuffePtr[sent][0];
                volatile int *answer = SND_UNCACHED(gReturnValuesPtr[sent]);
                int i;

                for (i = 0; i < count; i++)
                {
                    SndReturnDef *def = &gSndCommandReturnDefPtr[sent][i];

                    if (def->proc != NULL)
                        def->proc(answer[i + 1], def->user);
                }
            }
        }
    }

    if (gLoadBusy)
    {
        FlushCache(0);

        if (SND_UNCACHED(gLoadReturnValue)[0] != -1)
        {
            if (gLoadReturnDef.proc != NULL)
            {
                SndCompleteProc proc = gLoadReturnDef.proc;
                unsigned long user = gLoadReturnDef.user;

                gLoadReturnDef.proc = NULL;
                gLoadReturnDef.user = 0;
                proc(SND_UNCACHED(gLoadReturnValue)[0], user);
            }

            gLoadBusy = 0;
            SND_UNCACHED(gLoadReturnValue)[0] = 0;
        }
    }

    if (gCommBusy == NULL && gSndCommandBuffePtr[gCommandFillBuffer][0] != 0 && !gCaching)
        snd_SendFillBuffer();

    if (gSSRead)
    {
        int done;

        if (!gStreamingInited)
        {
            sceCdSync(1);
            done = gSSReadDone;
        }
        else
        {
            FlushCache(0);
            gSSReadDone = snd_StatsCdIdle();
            done = gSSReadDone;
        }

        if (done)
        {
            void (*callback)(int) = gCdCallback;

            gSSRead = 0;
            gSSReadDone = 0;

            if (callback != NULL)
                callback(1);
        }
    }

    return gCommBusy != NULL || gLoadBusy ? 1 : 0;
}

/* 0x2eaa90 / 0x2eaa80: hold queued commands until snd_SendCache */
void snd_StartCaching(void)
{
    gCaching = 1;
}

int snd_SendCache(void)
{
#ifdef SOCOM_PORT_SOUND_PROBE
    snd_ProbeFrame();
#endif
    gCaching = 0;
    return snd_FlushSoundCommands();
}

/* 0x2eb6b0 */
int snd_BankLoad(const char *name, int offset)
{
    int bank;

    if (gLoadBusy)
    {
        socom_port_trace("SND: snd_BankLoad: Load already in progress!");
        return 0;
    }

    *(int *)gSyncStringBuffer = offset;
    strcpy((char *)gSyncStringBuffer + 4, name);
    SND_UNCACHED(gLoadReturnValue)[0] = -1;
    snd_WaitClientIdle(&gSLClientLoaderData, 1);
    sceSifCallRpc(&gSLClientLoaderData, 2, SIF_RPC_M_NOWAIT, gSyncStringBuffer, strlen(name) + 5, gLoadReturnValue, 4, NULL, NULL);

    while (SND_UNCACHED(gLoadReturnValue)[0] == -1)
        FlushCache(0);

    bank = SND_UNCACHED(gLoadReturnValue)[0];
    socom_port_trace("SND: bank load %s -> 0x%x", name, bank);
    return bank;
}

/* 0x2eb540 */
int snd_BankLoadByLoc(int sector, int offset)
{
    int bank;

    if (gLoadBusy)
    {
        socom_port_trace("SND: snd_BankLoadByLoc: Load already in progress!");
        return 0;
    }

    if (snd_StreamSafeCdSync(1) == 1)
    {
        socom_port_trace("SND: snd_BankLoadByLoc: CD BUSY!");
        return 0;
    }

    SND_UNCACHED(gLoadParams)[0] = sector;
    SND_UNCACHED(gLoadReturnValue)[0] = -1;
    SND_UNCACHED(gLoadParams)[1] = offset;
    snd_WaitClientIdle(&gSLClientLoaderData, 1);
    sceSifCallRpc(&gSLClientLoaderData, 3, SIF_RPC_M_NOWAIT, gLoadParams, 8, gLoadReturnValue, 4, NULL, NULL);

    while (SND_UNCACHED(gLoadReturnValue)[0] == -1)
        FlushCache(0);

    bank = SND_UNCACHED(gLoadReturnValue)[0];
    socom_port_trace("SND: bank load at sector %d + %d -> 0x%x", sector, offset, bank);
    return bank;
}

/* 0x2eb520 */
void snd_ResolveBankXREFS(void)
{
    snd_SendIOPCommandNoWait(8, 0, NULL, NULL, 0);
}

/* 0x2eb4f0 */
void snd_UnloadBank(int bank)
{
    snd_SendIOPCommandNoWait(6, 4, (char *)&bank, NULL, 0);
}

/* 0x2eb4b0 */
void snd_SetMasterVolume(int group, int volume)
{
    int data[2];

    data[0] = group;
    data[1] = volume;
    snd_SendIOPCommandNoWait(9, 8, (char *)data, NULL, 0);
}

/* 0x2eb480 */
int snd_GetMasterVolume(int group)
{
    return snd_SendIOPCommandAndWait(10, 4, (char *)&group);
}

/* 0x2eb450 / 0x2eb440 */
void snd_SetPlaybackMode(int mode)
{
    snd_SendIOPCommandNoWait(11, 4, (char *)&mode, NULL, 0);
}

int snd_GetPlaybackMode(void)
{
    return snd_SendIOPCommandAndWait(12, 0, NULL);
}

/* 0x2eb5c0 / 0x2ea580 */
void snd_SetReverbType(int core, int type)
{
    int data[2];

    data[0] = core;
    data[1] = type;
    snd_SendIOPCommandNoWait(14, 8, (char *)data, NULL, 0);
}

void snd_AutoReverb(int core, int depth, int time, int channels)
{
    int data[4];

    data[0] = core;
    data[1] = depth;
    data[2] = time;
    data[3] = channels;
    snd_SendIOPCommandNoWait(16, 16, (char *)data, NULL, 0);
}

static void snd_TracePlay(int kind, const char *what, int bank, int sound, int volume, int pan)
{
    if (snd_trace_plays[kind] < 12)
    {
        snd_trace_plays[kind]++;
        socom_port_trace("SND: %s bank 0x%x sound %d vol %d pan %d", what, bank, sound, volume, pan);
    }
}

#ifdef SOCOM_PORT_SOUND_PROBE
/* Test hook, off by default (scratch builds add -DSOCOM_PORT_SOUND_PROBE): one-shot plays
 * are sent as the callback variant and their handles polled once per snd_SendCache (once
 * per sound frame) with snd_SoundIsStillPlaying_CB until 989snd reports them ended; the
 * trace gives how long each voice ran. */
#define SND_PROBES 8
static struct
{
    unsigned int handle; /* 0 free, 0xffffffff waiting for an answer */
    int bank, sound, frames, queries;
} snd_probe[SND_PROBES];
static int snd_probe_frame;
static int snd_probe_reported;

static void snd_ProbeAnswer(unsigned int result, unsigned long slot)
{
    if (snd_probe[slot].queries == 0)
        socom_port_trace("SND: probe: bank 0x%x sound %d started, handle 0x%x (frame %d)",
            snd_probe[slot].bank, snd_probe[slot].sound, result, snd_probe_frame);
    else if (result == 0)
        socom_port_trace("SND: probe: bank 0x%x sound %d ended after %d frames (%d queries)",
            snd_probe[slot].bank, snd_probe[slot].sound, snd_probe_frame - snd_probe[slot].frames, snd_probe[slot].queries);

    snd_probe[slot].queries++;
    snd_probe[slot].handle = result;
}

static int snd_ProbeStart(int bank, int sound, int volume, int pan, int pitch_mod, int pitch_bend)
{
    int data[6];
    int i;

    for (i = 0; i < SND_PROBES; i++)
        if (snd_probe[i].handle == 0)
            break;

    if (i == SND_PROBES)
        return 0;

    snd_probe[i].handle = 0xffffffff;
    snd_probe[i].bank = bank;
    snd_probe[i].sound = sound;
    snd_probe[i].frames = snd_probe_frame;
    snd_probe[i].queries = 0;
    data[0] = bank;
    data[1] = sound;
    data[2] = volume;
    data[3] = pan;
    data[4] = pitch_mod;
    data[5] = pitch_bend;
    snd_SendIOPCommandNoWait(17, 24, (char *)data, snd_ProbeAnswer, i);
    return 1;
}

static void snd_ProbeFrame(void)
{
    int i;

    snd_probe_frame++;

    if (!snd_probe_reported && gSndCommandBuffePtr[0] != NULL)
    {
        snd_probe_reported = 1;
        socom_port_trace("SND: probe: master volumes %d %d %d %d %d %d %d %d %d, playback mode %d",
            snd_GetMasterVolume(0), snd_GetMasterVolume(1), snd_GetMasterVolume(2), snd_GetMasterVolume(3),
            snd_GetMasterVolume(4), snd_GetMasterVolume(5), snd_GetMasterVolume(6), snd_GetMasterVolume(7),
            snd_GetMasterVolume(8), snd_GetPlaybackMode());
    }

    if (snd_probe_frame % 600 == 0)
        socom_port_trace("SND: probe: frame %d: queued play %d+%d one-shot, stream %d, still-playing %d, params %d, "
            "stop %d, vol/pan %d, autovol %d, CD reads %d, streaming %d",
            snd_probe_frame, snd_probe_counts[17], snd_probe_counts[18], snd_probe_counts[44], snd_probe_counts[25],
            snd_probe_counts[33], snd_probe_counts[21], snd_probe_counts[27], snd_probe_counts[34], snd_probe_counts[56],
            gStreamingInited);

    for (i = 0; i < SND_PROBES; i++)
    {
        unsigned int handle = snd_probe[i].handle;

        if (handle != 0 && handle != 0xffffffff)
        {
            snd_probe[i].handle = 0xffffffff;
            snd_SendIOPCommandNoWait(25, 4, (char *)&handle, snd_ProbeAnswer, i);
        }
    }
}
#endif

/* 0x2eb3a0 */
void snd_PlaySoundVolPanPMPB_CB(int bank, int sound, int volume, int pan, int pitch_mod, int pitch_bend,
    SndCompleteProc proc, unsigned long user)
{
    int data[6];

    snd_TracePlay(1, "play", bank, sound, volume, pan);
    data[0] = bank;
    data[1] = sound;
    data[2] = volume;
    data[3] = pan;
    data[4] = pitch_mod;
    data[5] = pitch_bend;
    snd_SendIOPCommandNoWait(17, 24, (char *)data, proc, user);
}

/* 0x2eb3f0 */
void snd_PlaySoundVolPanPMPB_A(int bank, int sound, int volume, int pan, int pitch_mod, int pitch_bend)
{
    int data[6];

    snd_TracePlay(0, "play one-shot", bank, sound, volume, pan);
#ifdef SOCOM_PORT_SOUND_PROBE
    if (snd_ProbeStart(bank, sound, volume, pan, pitch_mod, pitch_bend))
        return;
#endif
    data[0] = bank;
    data[1] = sound;
    data[2] = volume;
    data[3] = pan;
    data[4] = pitch_mod;
    data[5] = pitch_bend;
    snd_SendIOPCommandNoWait(18, 24, (char *)data, NULL, 0);
}

/* 0x2eb340 / 0x2eb310 / 0x2eb370 */
void snd_PauseSound(unsigned int handle)
{
    snd_SendIOPCommandNoWait(19, 4, (char *)&handle, NULL, 0);
}

void snd_ContinueSound(unsigned int handle)
{
    snd_SendIOPCommandNoWait(20, 4, (char *)&handle, NULL, 0);
}

void snd_StopSound(unsigned int handle)
{
    snd_SendIOPCommandNoWait(21, 4, (char *)&handle, NULL, 0);
}

/* 0x2eb2e0 */
void snd_SoundIsStillPlaying_CB(unsigned int handle, SndCompleteProc proc, unsigned long user)
{
    snd_SendIOPCommandNoWait(25, 4, (char *)&handle, proc, user);
}

/* 0x2eb2a0 */
void snd_SetSoundVolPan(unsigned int handle, int volume, int pan)
{
    int data[3];

    data[0] = (int)handle;
    data[1] = volume;
    data[2] = pan;
    snd_SendIOPCommandNoWait(27, 12, (char *)data, NULL, 0);
}

/* 0x2eb260 */
void snd_SetSoundPitch(unsigned int handle, int pitch)
{
    int data[2];

    data[0] = (int)handle;
    data[1] = pitch;
    snd_SendIOPCommandNoWait(30, 8, (char *)data, NULL, 0);
}

/* 0x2eb210 */
void snd_SetSoundParams_CB(unsigned int handle, int mask, int volume, int pan, int pitch_mod, int pitch_bend,
    SndCompleteProc proc, unsigned long user)
{
    int data[6];

    data[0] = (int)handle;
    data[1] = mask;
    data[2] = volume;
    data[3] = pan;
    data[4] = pitch_mod;
    data[5] = pitch_bend;
    snd_SendIOPCommandNoWait(33, 24, (char *)data, proc, user);
}

/* 0x2eb1d0 */
void snd_AutoVol(unsigned int handle, int volume, int time, int mode)
{
    int data[4];

    data[0] = (int)handle;
    data[1] = volume;
    data[2] = time;
    data[3] = mode;
    snd_SendIOPCommandNoWait(34, 16, (char *)data, NULL, 0);
}

/* 0x2ea950: the IOP's streaming result; from here on CD reads go through the IOP */
int snd_InitVAGStreamingEx(int streams, int buffer_size, int a2, int a3)
{
    int data[4];

    if (gStreamingInited == 1)
        return 0;

    if (gLoadBusy)
        while (snd_FlushSoundCommands())
            ;

    snd_StreamSafeCdSync(0);
    data[0] = streams;
    data[1] = buffer_size;
    data[2] = a2;
    data[3] = a3;
    gStreamingInited = snd_SendIOPCommandAndWait(42, 16, (char *)data);
    socom_port_trace("SND: VAG streaming init (%d streams, 0x%x bytes) -> %d", streams, buffer_size, gStreamingInited);
    return gStreamingInited;
}

/* 0x2ea850 */
void snd_CloseVAGStreaming(void)
{
    if (!gStreamingInited)
        return;

    if (gLoadBusy)
        while (snd_FlushSoundCommands())
            ;

    snd_StreamSafeCdSync(0);
    snd_SendIOPCommandAndWait(53, 0, NULL);
    gStreamingInited = 0;
    socom_port_trace("SND: VAG streaming closed");
}

/* 0x2ea930 */
void snd_StopAllStreams(void)
{
    snd_SendIOPCommandNoWait(52, 0, NULL, NULL, 0);
}

/* 0x2ea7e0: offsets and volume/pan share words (offset in the low 16 bits) */
void snd_PlayVAGStreamByLoc_CB(int loc1, int loc2, int offset1, int offset2, int volume, int pan, int vol_group,
    int a7, int a8, SndCompleteProc proc, unsigned long user)
{
    int data[7];

    if (snd_trace_plays[2] < 12)
    {
        snd_trace_plays[2]++;
        socom_port_trace("SND: stream sectors %d/%d (+%d/+%d) vol %d pan %d group %d", loc1, loc2, offset1, offset2,
            volume, pan, vol_group);
    }

    data[0] = loc1;
    data[1] = loc2;
    data[2] = (volume << 16) | (offset1 & 0xffff);
    data[3] = (pan << 16) | (offset2 & 0xffff);
    data[4] = vol_group;
    data[5] = a7;
    data[6] = a8;
    snd_SendIOPCommandNoWait(44, 28, (char *)data, proc, user);
}

/* 0x2ea7b0 */
int snd_StreamSafeCheckCDIdle(int wait)
{
    return snd_SendIOPCommandAndWait(54, 4, (char *)&wait);
}

/* 0x2ea6d0: through the IOP once streaming runs (the read mode is not sent) */
int snd_StreamSafeCdRead(unsigned int lsn, unsigned int sectors, void *buf, sceCdRMode *mode)
{
    unsigned int data[3];

    if (!gStreamingInited)
        return sceCdRead(lsn, sectors, buf, mode);

    FlushCache(0);
    gSSReadDone = snd_StatsCdIdle();

    if (!gSSReadDone)
        return 0;

    SND_UNCACHED(gStats)[0] = 1;
    SND_UNCACHED(gStats)[4] = 0;
    data[0] = lsn;
    data[1] = sectors;
    data[2] = (unsigned int)buf;
    snd_SendIOPCommandNoWait(56, 12, (char *)data, NULL, 0);
    gSSReadDone = 0;
    gSSRead = 1;
    return 1;
}

/* 0x2ea630: 0 = idle; mode 1 polls once (1 = busy), other modes wait */
int snd_StreamSafeCdSync(int mode)
{
    if (!gStreamingInited)
        return sceCdSync(mode);

    FlushCache(0);
    gSSReadDone = snd_StatsCdIdle();

    if (gSSReadDone == 1)
        return 0;

    if (mode == 1)
        return 1;

    while (!gSSReadDone)
    {
        int idle = snd_StatsCdIdle();

        snd_FlushSoundCommands();
        gSSReadDone = idle;
    }

    return 0;
}

/* 0x2ea600 */
int snd_StreamSafeCdGetError(void)
{
    if (gStreamingInited)
        return SND_UNCACHED(gStats)[4];

    return sceCdGetError();
}

/* 0x2ea540 / 0x2ea530 / 0x2ea520 / 0x2ea4f0 / 0x2ea4e0: MPEG audio */
int snd_InitMovieSound(int a0, int a1, int a2, int a3)
{
    int data[4];

    data[0] = a0;
    data[1] = a1;
    data[2] = a2;
    data[3] = a3;
    return snd_SendIOPCommandAndWait(59, 16, (char *)data);
}

int snd_CloseMovieSound(void)
{
    return snd_SendIOPCommandAndWait(60, 0, NULL);
}

int snd_ResetMovieSound(void)
{
    return snd_SendIOPCommandAndWait(61, 0, NULL);
}

int snd_StartMovieSound(int a0, int a1, int a2)
{
    int data[3];

    data[0] = a0;
    data[1] = a1;
    data[2] = a2;
    return snd_SendIOPCommandAndWait(62, 12, (char *)data);
}

int snd_GetTransStatus(void)
{
    return snd_SendIOPCommandAndWait(64, 0, NULL);
}

/* 0x2ea4a0 / 0x2ea450 / 0x2ea400: a call into an IOP module through 989snd */
int snd_DoExternCall(int a0, int a1, int a2, int a3, int a4, int a5, int a6)
{
    int data[7];

    data[0] = a0;
    data[1] = a1;
    data[2] = a2;
    data[3] = a3;
    data[4] = a4;
    data[5] = a5;
    data[6] = a6;
    return snd_SendIOPCommandAndWait(76, 28, (char *)data);
}

void snd_DoExternCall_A(int a0, int a1, int a2, int a3, int a4, int a5, int a6)
{
    int data[7];

    data[0] = a0;
    data[1] = a1;
    data[2] = a2;
    data[3] = a3;
    data[4] = a4;
    data[5] = a5;
    data[6] = a6;
    snd_SendIOPCommandNoWait(76, 28, (char *)data, NULL, 0);
}

void snd_DoExternCall_CB(int a0, int a1, int a2, int a3, int a4, int a5, int a6, SndCompleteProc proc, unsigned long user)
{
    int data[7];

    data[0] = a0;
    data[1] = a1;
    data[2] = a2;
    data[3] = a3;
    data[4] = a4;
    data[5] = a5;
    data[6] = a6;
    snd_SendIOPCommandNoWait(76, 28, (char *)data, proc, user);
}
