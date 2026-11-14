/* Port compatibility header: the Sony EE sifrpc.h. ps2sdk ships a sifrpc.h with the same
 * sceSif* RPC calls; this header chains to it and adds the Sony type names it lacks.
 * Shared and append-only. */
#ifndef SOCOM_COMPAT_SIFRPC_H
#define SOCOM_COMPAT_SIFRPC_H

#include_next <sifrpc.h>

/* Sony's client block (40 bytes, the server pointer at +0x24): ps2sdk's has the same layout */
typedef SifRpcClientData_t sceSifClientData;

#endif /* SOCOM_COMPAT_SIFRPC_H */
