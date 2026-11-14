/* Port compatibility header: the SDK's libnet (EE client of libnetb.irx over the msifrpc
 * multi-RPC, sceSifM*) and its inet calls, as the game calls them (CNetCnf in zNetCnf.cpp, the DME
 * layer in zNetDme.cpp). The client block and the net buffer are the game's own storage
 * (CNetCnf::libnetCd, 60 bytes; CNetCnf::libnetBuffer, 5184 bytes); the port passes them opaque.
 * Prototypes from the call sites; names after the SDK. The port's offline stand-ins are in
 * port/compat/libnet_offline.c. */
#ifndef SOCOM_COMPAT_LIBNET_H
#define SOCOM_COMPAT_LIBNET_H

#ifdef __cplusplus
extern "C" {
#endif

/* msifrpc (libmrpc) */
int sceSifMInitRpc(unsigned int mode);
void sceSifMExitRpc(void);

/* libnet */
int libnet_init(void *cd, int buffersize, int stacksize, int priority);
int libnet_term(void *cd);
int reg_handler(void *cd, void *net_buf);
int unreg_handler(void *cd, void *net_buf);
int sceInetGetInterfaceList(void *cd, void *net_buf, int *interface_ids, int count);
int sceInetInterfaceControl(void *cd, void *net_buf, int interface_id, int code, void *ptr, int len);
/* name lookup (CZNetwork::zNetInitEx 0x321d60: the Medius server name, 6000 ms, 4 tries) */
int sceInetName2Address(void *cd, void *net_buf, int flags, void *address, const char *name, int ms, int retries);
int sceInetAddress2String(void *cd, void *net_buf, char *text, int length, void *address);

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_LIBNET_H */
