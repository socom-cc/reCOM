/* Functional port lane: offline stand-ins for the SDK's libnet (EE client of LIBNETB.IRX over the
 * msifrpc multi-RPC), its inet calls, and the ezNetCtl sample client (EZNETCTL.IRX). Not Sony
 * code; nothing here is evidence for the matching lane. The port has no network stack: the game's
 * callers (CNetCnf in zNetCnf.cpp, the DME layer in zNetDme.cpp) see a client that cannot bind
 * and a machine with no network interface:
 *   - sceSifMInitRpc / libnet_init / libnet_term / sceSifMExitRpc: nothing to start or stop (0);
 *   - reg_handler: -1 (no libnet server to register with): CNetCnf::Init and LibNETSetup then
 *     register no IOP reboot callback, and LibNETSetup answers false (InitFromCombo gives up);
 *   - sceInetGetInterfaceList: 0 interfaces (the network-configuration screens list none);
 *   - sceInetInterfaceControl: -1 (no such interface; never reached with 0 interfaces);
 *   - ezNetCtl: -1 (unreachable: InitFromCombo stops at LibNETSetup). */
#include <stddef.h>
#include <libnet.h>
#include <eznetctl.h>

void socom_port_trace(const char *fmt, ...);

int sceSifMInitRpc(unsigned int mode)
{
    (void)mode;
    return 0;
}

void sceSifMExitRpc(void)
{
}

int libnet_init(void *cd, int buffersize, int stacksize, int priority)
{
    (void)cd;
    (void)buffersize;
    (void)stacksize;
    (void)priority;
    return 0;
}

int libnet_term(void *cd)
{
    (void)cd;
    return 0;
}

int reg_handler(void *cd, void *net_buf)
{
    (void)cd;
    (void)net_buf;
    socom_port_trace("NET: reg_handler: no libnet server (network offline in the port) -> -1");
    return -1;
}

int unreg_handler(void *cd, void *net_buf)
{
    (void)cd;
    (void)net_buf;
    return 0;
}

int sceInetGetInterfaceList(void *cd, void *net_buf, int *interface_ids, int count)
{
    (void)cd;
    (void)net_buf;
    (void)interface_ids;
    (void)count;
    return 0;
}

int sceInetInterfaceControl(void *cd, void *net_buf, int interface_id, int code, void *ptr, int len)
{
    (void)cd;
    (void)net_buf;
    (void)interface_id;
    (void)code;
    (void)ptr;
    (void)len;
    return -1;
}

/* no name service: -1 (zNetInitEx keeps the configured address; unreachable offline: the
 * modules do not come up) */
int sceInetName2Address(void *cd, void *net_buf, int flags, void *address, const char *name, int ms, int retries)
{
    (void)cd; (void)net_buf; (void)flags; (void)address; (void)name; (void)ms; (void)retries;
    return -1;
}

int sceInetAddress2String(void *cd, void *net_buf, char *text, int length, void *address)
{
    (void)cd; (void)net_buf; (void)address;
    if (text != NULL && length > 0)
        text[0] = '\0';
    return -1;
}

int initEzNetCtl(void)
{
    return -1;
}

int ezNetCtlSetProperties(sceNetcnfifData *data)
{
    (void)data;
    return -1;
}

int ezNetCtlUpInterface(int id)
{
    (void)id;
    return -1;
}
