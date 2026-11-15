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


/* ---- socom-port-mod-znet2 (2026-11-14): the rest of the lobby's calls (the state handlers, clans,
 * ladders, chat, game and room lists). The lobby only reaches them once connected, which offline never
 * happens; each answers an error and calls no callback (the lobby then waits in its current state). */
int MediusSessionBegin(struct MediusSessionBeginRequest *request, void (*callback)(int, int, int, struct MediusSessionBeginResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusSessionEnd(struct MediusSessionEndRequest *request, void (*callback)(int, int, int, struct MediusSessionEndResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusVersionServer(struct MediusVersionServerRequest *request, void (*callback)(int, int, int, struct MediusVersionServerResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusTextFilter(struct MediusTextFilterRequest *request, void (*callback)(int, int, int, struct MediusTextFilterResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusAccountRegistration(struct MediusAccountRegistrationRequest *request, void (*callback)(int, int, int, struct MediusAccountRegistrationResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusAccountLogin(struct MediusAccountLoginRequest *request, void (*callback)(int, int, int, struct MediusAccountLoginResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusCreateChannel(struct MediusCreateChannelRequest *request, void (*callback)(int, int, int, struct MediusCreateChannelResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusFindWorldByName(struct MediusFindWorldByNameRequest *request, void (*callback)(int, int, int, struct MediusFindWorldByNameResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusJoinChannel(struct MediusJoinChannelRequest *request, void (*callback)(int, int, int, struct MediusJoinChannelResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusJoinGame(struct MediusJoinGameRequest *request, void (*callback)(int, int, int, struct MediusJoinGameResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusCreateGame(struct MediusCreateGameRequest *request, void (*callback)(int, int, int, struct MediusCreateGameResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetPlayerInfo(struct MediusPlayerInfoRequest *request, void (*callback)(int, int, int, struct MediusPlayerInfoResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetPolicy(struct MediusGetPolicyRequest *request, void (*callback)(int, int, int, struct MediusGetPolicyResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusChatToggleFilter(struct MediusChatToggleRequest *request, void (*callback)(int, int, int, struct MediusChatToggleResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusUpdateClientState(struct MediusUpdateClientStateRequest *request)
{
    (void)request;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusSendPlayerReport(struct MediusPlayerReport *report)
{
    (void)report;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusSendWorldReport(struct MediusWorldReport *report)
{
    (void)report;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusSetGameListFilter(struct MediusSetGameListFilterRequest *request, void (*callback)(int, int, int, struct MediusSetGameListFilterResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusAccountUpdateStats(struct MediusAccountUpdateStatsRequest *request, void (*callback)(int, int, int, struct MediusStatusResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetGamePlayers(struct MediusGameWorldPlayerListRequest *request, void (*callback)(int, int, int, struct MediusGameWorldPlayerListResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusRemovePlayerFromClan(struct MediusRemovePlayerFromClanRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusRemovePlayerFromClanResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusDisbandClan(struct MediusClanRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusDisbandClanResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetClanMemberList(struct MediusClanRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusGetClanMemberListResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusLadderPosition(struct MediusLadderPositionRequest *request, void (*callback)(int, int, int, struct MediusLadderPositionResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetClanInvitationsSent(struct MediusPageRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusGetClanInvitationsSentResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusAddPlayerToClan(struct MediusAddPlayerToClanRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusAddPlayerToClanResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusRevokeClanInvitation(struct MediusRevokeClanInvitationRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusRevokeClanInvitationResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusAccountGetID(struct MediusAccountGetIDRequest *request, void (*callback)(int, int, int, struct MediusAccountGetIDResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusInvitePlayerToClan(struct MediusInvitePlayerToClanRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusInvitePlayerToClanResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusCreateClan(struct MediusCreateClanRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusCreateClanResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusUpdateClanStats(struct MediusUpdateClanStatsRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusUpdateClanStatsResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusTransferClanLeadership(struct MediusTransferClanLeadershipRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusTransferClanLeadershipResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusSendClanMessage(struct MediusSendClanMessageRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusSendClanMessageResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusCheckMyClanInvitations(struct MediusPageRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusCheckMyClanInvitationsResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusRespondToClanInvitation(struct MediusRespondToClanInvitationRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusRespondToClanInvitationResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetMyClans(struct MediusPageRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusGetMyClansResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetAnnouncements(struct MediusGetAnnouncementsRequest *request, void (*callback)(int, int, int, struct MediusGetAnnouncementsResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetMyClanMessages(struct MediusGetMyClanMessagesRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusGetMyClanMessagesResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusSendChatMessage(struct MediusChatMessageRequest *request)
{
    (void)request;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusBanPlayer(struct MediusBanPlayerRequest *request, void (*callback)(int, int, int, struct MediusBanPlayerResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusClearGameListFilter(struct MediusClearGameListFilterRequest *request, void (*callback)(int, int, int, struct MediusClearGameListFilterResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetGames(struct MediusGameListRequest *request, void (*callback)(int, int, int, struct MediusGameListResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetGameInfo(struct MediusGameInfoRequest *request, void (*callback)(int, int, int, struct MediusGameInfoResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetWorldSecurityLevel(struct MediusGetWorldSecurityLevelRequest *request, void (*callback)(int, int, int, struct MediusGetWorldSecurityLevelResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusGetChannelInfo(struct MediusChannelInfoRequest *request, void (*callback)(int, int, int, struct MediusChannelInfoResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

int MediusLadderList(struct MediusLadderListRequest *request, void (*callback)(int, int, int, struct MediusLadderListResponse *))
{
    (void)request; (void)callback;
    return MEDIUS_OFFLINE_ERROR;
}

}
