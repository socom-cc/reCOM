/* Functional port lane: offline stand-ins for the SCE-RT Medius lobby client library (provider code
 * in the ELF). Not SCE-RT code; nothing here is evidence for the matching lane. The servers are
 * gone and the port has no network, so the lobby (CZOnlineLobby, src/gamez/zNetwork/zNetMedius.cpp)
 * must reach its "connect failure" path:
 *   - MediusConnect: a nonzero error, no callback: AuxInitNetwork queues CONNECT_ERROR itself and
 *     ticks the lobby, the socom_online_state valve becomes 2 and dlgNetConnect shows
 *     "STATE: Connect Failure", then bails out to the previous screen;
 *   - MediusInitializeBare / VersionClient / GetBuildTimeStamp / SetDefaultConnectInfo: done, empty
 *     strings (the game does not read their results);
 *   - requests (MediusGetChannels): an error and no callback (nothing is listed);
 *   - MediusUpdate: 0 (no error; only ticked while connected, which never happens);
 *   - MediusDisconnect / MediusCloseBare: nothing to close (0). */
#include <string.h>
#include <medius.h>

extern "C" void socom_port_trace(const char *fmt, ...);

#define MEDIUS_OFFLINE_ERROR (-1) /* port: any nonzero MediusErrorCode; the game tests for 0 */

extern "C" {

int MediusInitializeBare(struct MediusInitializeBareParams *params, int *result)
{
    (void)params;
    if (result != NULL)
        *result = 0;
    return 0;
}

int MediusCloseBare(void)
{
    return 0;
}

int MediusVersionClient(char *version)
{
    if (version != NULL)
        version[0] = '\0';
    return 0;
}

int MediusGetBuildTimeStamp(char *stamp)
{
    if (stamp != NULL)
        stamp[0] = '\0';
    return 0;
}

int MediusSetDefaultConnectInfo(NetConnectionInfo *info, int type, const char *address, int port, int flag)
{
    (void)address; (void)port; (void)flag;
    memset(info, 0, sizeof(*info));
    info->Type = type;
    return 0;
}

int MediusConnect(struct MediusConnectRequest *request, int *result)
{
    (void)request;
    if (result != NULL)
        *result = MEDIUS_OFFLINE_ERROR;
    socom_port_trace("NET: MediusConnect: no Medius server (network offline in the port) -> %d", MEDIUS_OFFLINE_ERROR);
    return MEDIUS_OFFLINE_ERROR;
}

int MediusDisconnect(void)
{
    return 0;
}

int MediusUpdate(void)
{
    return 0;
}

int MediusGetLastNetUpdateError(void)
{
    return 0;
}

int MediusCreateMessageID(const char *sessionKey, int type, void *request)
{
    (void)sessionKey; (void)type;
    if (request != NULL)
        ((char *)request)[0] = '\0';
    return 0;
}

/* no server: no player list (no callback) */
int MediusGetLobbyPlayers(struct MediusLobbyWorldPlayerListRequest *request, void (*callback)(int, int, int, struct MediusLobbyWorldPlayerListResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

/* no server to report to */
int MediusSendEndGameReport(struct MediusEndGameReport *report)
{
    (void)report;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetChannels(struct MediusChannelListRequest *request, void (*callback)(int, int, int, struct MediusChannelListResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

}
