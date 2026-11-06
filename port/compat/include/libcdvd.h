/* Port compatibility header: the Sony EE libcdvd.h. ps2sdk ships a libcdvd.h of the
 * same name with the same sceCd* calls and types; this header chains to it and adds
 * the Sony spellings ps2sdk renamed. Shared and append-only. */
#ifndef SOCOM_COMPAT_LIBCDVD_H
#define SOCOM_COMPAT_LIBCDVD_H

#include_next <libcdvd.h>

/* sceCdMmode media (ps2sdk: SCECdMmodeCd / SCECdMmodeDvd) */
#ifndef SCECdCD
#define SCECdCD SCECdMmodeCd
#endif
#ifndef SCECdDVD
#define SCECdDVD SCECdMmodeDvd
#endif

#endif /* SOCOM_COMPAT_LIBCDVD_H */
