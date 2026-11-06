/* Functional port lane: offline 989snd client (sound is silent by user decision).
 * Not Sony/989 Studios code; nothing here is evidence for the matching lane. */
#include <989snd.h>

/* The game's 989snd never initialises streaming in the port, so the stream-safe CD
 * calls take their non-streaming branch (0x2ea6d0, 0x2ea630, 0x2ea600). */
int snd_StreamSafeCdRead(unsigned int lsn, unsigned int sectors, void *buf, sceCdRMode *mode)
{
    return sceCdRead(lsn, sectors, buf, mode);
}

int snd_StreamSafeCdSync(int mode)
{
    return sceCdSync(mode);
}

int snd_StreamSafeCdGetError(void)
{
    return sceCdGetError();
}

/* Offline: the sound system never starts, so nothing is played or streamed. */
int snd_StartSoundSystem(void)
{
    return 0;
}

void snd_SetReverbType(int core, int type)
{
    (void)core;
    (void)type;
}

void snd_AutoReverb(int core, int depth, int time, int channels)
{
    (void)core;
    (void)depth;
    (void)time;
    (void)channels;
}

int snd_InitVAGStreamingEx(int streams, int buffer_size, int a2, int a3)
{
    (void)streams;
    (void)buffer_size;
    (void)a2;
    (void)a3;
    return 0;
}

/* Offline: no sound plays, so there is nothing to stop. */
void snd_StopSound(unsigned int handle)
{
    (void)handle;
}
