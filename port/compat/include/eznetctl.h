/* Port compatibility header: the SDK sample ezNetCtl (EE client of eznetctl.irx, which brings an
 * interface up from a network configuration), as CNetCnf::InitFromCombo (0x3feb80) calls it.
 * Prototypes from that call site; the offline stand-ins are in port/compat/libnet_offline.c. */
#ifndef SOCOM_COMPAT_EZNETCTL_H
#define SOCOM_COMPAT_EZNETCTL_H

#include <netcnfif.h>

#ifdef __cplusplus
extern "C" {
#endif

int initEzNetCtl(void);
int ezNetCtlSetProperties(sceNetcnfifData *data);
int ezNetCtlUpInterface(int id);

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_EZNETCTL_H */
