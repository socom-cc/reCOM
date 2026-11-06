/* Port compatibility header: the 989snd EE client library the game calls (header name
 * unproven). Sound is offline in the port (user decision: silent stubs), implemented
 * in port/compat/snd989_offline.c. Prototypes follow the game's call sites. Shared and
 * append-only: add declarations, never rewrite or reorder others' lines. */
#ifndef SOCOM_COMPAT_989SND_H
#define SOCOM_COMPAT_989SND_H

#include <libcdvd.h> /* sceCdRMode */

#ifdef __cplusplus
extern "C" {
#endif

/* CD access that cooperates with 989snd streaming (0x2ea6d0 / 0x2ea630 / 0x2ea600).
 * With streaming not initialised they are sceCdRead / sceCdSync / sceCdGetError. */
int snd_StreamSafeCdRead(unsigned int lsn, unsigned int sectors, void *buf, sceCdRMode *mode);
int snd_StreamSafeCdSync(int mode);
int snd_StreamSafeCdGetError(void);

/* Sound-system start and set-up the game calls from CSnd::Init (0x2ee2c4-0x2ee31c) and
 * CSnd::UIOpen (0x2ee124); argument meanings unproven, return values unused there. */
int snd_StartSoundSystem(void);
void snd_SetReverbType(int core, int type);
void snd_AutoReverb(int core, int depth, int time, int channels);
int snd_InitVAGStreamingEx(int streams, int buffer_size, int a2, int a3);

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_989SND_H */
