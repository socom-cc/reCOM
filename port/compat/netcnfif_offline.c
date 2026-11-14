/* Functional port lane: offline stand-in for the SDK's libnetcnfif (the EE side of the network
 * configuration interface, NETCNFIF.IRX; ELF 0x425280..0x425e78, provider code). Not Sony code;
 * nothing here is evidence for the matching lane. The port has no network layer and its memory-card
 * layer is off (port/compat/libmc.c), so there is no "Your Network Configuration" file to read.
 *
 * Each request completes at once (sceNetcnfifCheck answers 0 = done) with a netcnf error, which is
 * what CNetCnf's states (src/gamez/zNetwork/zNetCnf.cpp) handle: SignalNetCnfError raises the menu's
 * NETCNF_ERROR event with the message, and the state machine goes idle.
 *   - file requests on mc0: (GetCount, GetList, LoadEntry, AddEntry, DeleteAll): -3, "file open
 *     error" - the configuration file cannot be opened: no memory card in the port;
 *   - work-area requests (AllocWorkarea, GetAddr): -2, "no space for memory" - there is no IOP-side
 *     work area;
 *   - SendIOP / DmaCheck: no transfer, done at once (unreachable: GetAddr fails first). */
#include <string.h>
#include <netcnfif.h>

void socom_port_trace(const char *fmt, ...);

#define NETCNF_OPEN_ERROR (-3)
#define NETCNF_NO_MEMORY (-2)

static int s_result;

static void offline_request(const char *what, int result)
{
    socom_port_trace("NET: %s: network configuration offline in the port -> %d", what, result);
    s_result = result;
}

void sceNetcnfifInit(void)
{
}

void sceNetcnfifSetup(void)
{
}

int sceNetcnfifCheck(void)
{
    return 0;
}

void sceNetcnfifGetResult(sceNetcnfifArg *result)
{
    memset(result, 0, sizeof(*result));
    result->data = s_result;
}

void sceNetcnfifGetCount(const char *fname, int type)
{
    (void)fname;
    (void)type;
    offline_request("sceNetcnfifGetCount", NETCNF_OPEN_ERROR);
}

void sceNetcnfifGetList(const char *fname, int type, sceNetcnfifList *list, int count)
{
    (void)fname;
    (void)type;
    (void)list;
    (void)count;
    offline_request("sceNetcnfifGetList", NETCNF_OPEN_ERROR);
}

void sceNetcnfifLoadEntry(const char *fname, int type, const char *usr_name, sceNetcnfifData *data)
{
    (void)fname;
    (void)type;
    (void)usr_name;
    (void)data;
    offline_request("sceNetcnfifLoadEntry", NETCNF_OPEN_ERROR);
}

void sceNetcnfifAddEntry(const char *fname, int type, const char *usr_name)
{
    (void)fname;
    (void)type;
    (void)usr_name;
    offline_request("sceNetcnfifAddEntry", NETCNF_OPEN_ERROR);
}

void sceNetcnfifDeleteAll(const char *fname)
{
    (void)fname;
    offline_request("sceNetcnfifDeleteAll", NETCNF_OPEN_ERROR);
}

void sceNetcnfifAllocWorkarea(int size)
{
    (void)size;
    offline_request("sceNetcnfifAllocWorkarea", NETCNF_NO_MEMORY);
}

void sceNetcnfifFreeWorkarea(void)
{
}

void sceNetcnfifGetAddr(void)
{
    offline_request("sceNetcnfifGetAddr", NETCNF_NO_MEMORY);
}

int sceNetcnfifSendIOP(unsigned int data, unsigned int addr, unsigned int size)
{
    (void)data;
    (void)addr;
    (void)size;
    return 0;
}

int sceNetcnfifDmaCheck(int id)
{
    (void)id;
    return 0;
}

/* Empty settings. port guess: the SDK's exact "unset" values are not in the ELF's game code; the
 * game relies only on ifc_type -1 meaning "no settings" (CNetCnf::InitFromCombo 0x3febf0), so every
 * int is -1 and the rest is zero. */
void sceNetcnfifDataInit(sceNetcnfifData *data)
{
    memset(data, 0, sizeof(*data));
    data->ifc_type = -1;
    data->mtu = -1;
    data->ifc_idle_timeout = -1;
    data->dev_type = -1;
    data->phy_config = -1;
    data->dialing_type = -1;
    data->dev_idle_timeout = -1;
}

/* a debug print of the settings in the SDK */
void sceNetcnfifDataDump(sceNetcnfifData *data)
{
    (void)data;
}
