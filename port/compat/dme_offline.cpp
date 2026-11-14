/* Functional port lane: offline stand-ins for the SCE-RT DME library (the game-session network
 * layer, "dme version: 1.16.S033"; provider code in the ELF). Not SCE-RT code; nothing here is
 * evidence for the matching lane. The port has no network: every call answers the way the game's
 * callers (CZNetwork in src/gamez/zNetwork/zNetDme.cpp, the lobby) take as "not available":
 *   - NetInitialize / NetConnect / NetJoin: error code 1 in the result (or return), never 0: the
 *     DME layer is not initialised (m_network_init stays 0), not connected, not joined;
 *   - the getters (NetGetObject, NetGetClient, the client indices and counts, the times): a
 *     nonzero error, so the CZNetwork wrappers answer NULL / -1 / 0;
 *   - NetTick / NetUpdate / NetClose / NetLeave / NetDisconnect / the registrations: nothing to do (0;
 *     NetTickThreadEntry keeps its 1/20 s sleep);
 *   - NetSetDefault*Params: zeroed parameter blocks.
 * NetGetBandwidthInfo is another worker's (net_bandwidth_offline.c). */
#include <string.h>
#include <dme.h>

extern "C" void socom_port_trace(const char *fmt, ...);

#define NET_OFFLINE_ERROR 1 /* port: any nonzero NetErrorCode; the game only tests for 0 */

extern "C" {

int NetSetDefaultInitializeParams(NetInitializeParams *params)
{
    memset(params, 0, sizeof(*params));
    return 0;
}

int NetInitialize(NetInitializeParams *params, NetOutParams *out)
{
    (void)params;
    memset(out, 0, sizeof(*out));
    out->ErrorCode = NET_OFFLINE_ERROR;
    socom_port_trace("NET: NetInitialize: DME offline in the port -> error %d", NET_OFFLINE_ERROR);
    return NET_OFFLINE_ERROR;
}

int NetGetMyIpAddress(char *address)
{
    if (address != NULL)
        address[0] = '\0';
    return NET_OFFLINE_ERROR;
}

int NetClose(void)
{
    return 0;
}

int NetTick(void)
{
    return 0;
}

int NetUpdate(void)
{
    return 0;
}

int NetSetDefaultConnectParams(NetConnectParams *params)
{
    memset(params, 0, sizeof(*params));
    return 0;
}

int NetConnect(NetConnectParams *params, NetOutParams *out)
{
    (void)params;
    memset(out, 0, sizeof(*out));
    out->ErrorCode = NET_OFFLINE_ERROR;
    out->ConnectionIndex = -1;
    socom_port_trace("NET: NetConnect: DME offline in the port -> error %d", NET_OFFLINE_ERROR);
    return NET_OFFLINE_ERROR;
}

int NetDisconnect(int connection)
{
    (void)connection;
    return 0;
}

int NetJoin(int connection, NetJoinParams *params, int numObjects, int numStreams, int unknown_t0, int unknown_t1,
    void (*joinCallback)(int, int), void (*leaveCallback)(int, int))
{
    (void)connection; (void)params; (void)numObjects; (void)numStreams; (void)unknown_t0; (void)unknown_t1;
    (void)joinCallback; (void)leaveCallback;
    return NET_OFFLINE_ERROR;
}

int NetLeave(int connection)
{
    (void)connection;
    return 0;
}

int NetGetValidClientCount(int *count, int connection)
{
    (void)connection;
    if (count != NULL)
        *count = 0;
    return NET_OFFLINE_ERROR;
}

int NetGetSessionMasterClientIndex(int *index, int connection)
{
    (void)index;
    (void)connection;
    return NET_OFFLINE_ERROR;
}

int NetGetMyClientIndex(int *index, int connection)
{
    (void)index;
    (void)connection;
    return NET_OFFLINE_ERROR;
}

int NetGetClient(void **client, int connection, int index)
{
    (void)connection;
    (void)index;
    if (client != NULL)
        *client = NULL;
    return NET_OFFLINE_ERROR;
}

int NetGetObject(void **object, int index)
{
    (void)index;
    if (object != NULL)
        *object = NULL;
    return NET_OFFLINE_ERROR;
}

int NetGetLocalTime(int *time)
{
    (void)time;
    return NET_OFFLINE_ERROR;
}

int NetGetTime(int *time)
{
    (void)time;
    return NET_OFFLINE_ERROR;
}

int NetCreateObject(int *index, enum NetOwnershipStatus ownership, enum NetObjectLifespan lifespan, unsigned int a,
    int b, unsigned int c, int d, void *data, char *name, int e)
{
    (void)ownership; (void)lifespan; (void)a; (void)b; (void)c; (void)d; (void)data; (void)name; (void)e;
    if (index != NULL)
        *index = -1;
    return NET_OFFLINE_ERROR;
}

int NetSendApplicationMessage(int messageClass, int connection, int client, int type, int length, unsigned char *data)
{
    (void)messageClass; (void)connection; (void)client; (void)type; (void)length; (void)data;
    return NET_OFFLINE_ERROR;
}

int NetRegisterRemoteObjectCallback(int type, void (*createCallback)(int, int), void (*updateCallback)(int, int, int),
    void (*destroyCallback)(int, int))
{
    (void)type; (void)createCallback; (void)updateCallback; (void)destroyCallback;
    return 0;
}

}
