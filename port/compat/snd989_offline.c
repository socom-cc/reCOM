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
