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

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_989SND_H */
