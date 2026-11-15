/* Port compatibility header: declarations the game source takes from the SCE-RT
 * Medius lobby client library. The original header name is unknown: `medius.h` is a
 * port guess. Shared and append-only: add declarations, never rewrite or reorder
 * others' lines. The online layer is stubbed offline later; these exist so the
 * declarations in src compile. */
#ifndef SOCOM_COMPAT_MEDIUS_H
#define SOCOM_COMPAT_MEDIUS_H

/* By value in the lobby callbacks, e.g. cbGetMyClans__F15MediusErrorCode15MediusErrorCode
 * 15MediusErrorCodeP24MediusGetMyClansResponse and
 * LookupMediusCallbackStatus__F20MediusCallbackStatus. Enumerators unknown:
 * port: unproven. */
enum MediusErrorCode {};
enum MediusCallbackStatus {};

/* ---- socom-port-mod-znet (2026-11-14): the records and calls the lobby core uses (zNetMedius.cpp).
 * No DWARF for any SDK record: layouts from the game's copies of them (BriefingRoom's constructor
 * 0x327190, RoomGame::UpdateInfo 0x326160, MediusGameListResponse's assignment 0x327100), member
 * names after the SDK's (port guesses where noted). The calls are C (unmangled symbols); the port's
 * offline stand-ins are in port/compat/medius_offline.c. */
#include <dme.h> /* NetConnectionInfo */

/* a lobby world (room) of the channel list (104 bytes) */
struct MediusChannelListResponse
{
    char MessageID[21];   /* +0x0 */
    int StatusCode;       /* +0x18 MediusCallbackStatus */
    int MediusWorldID;    /* +0x1c (-1 for the rooms read from mp_rooms.rdr) */
    char LobbyName[64];   /* +0x20 */
    int PlayerCount;      /* +0x60 port: name guessed */
    char EndOfList;       /* +0x64 */
};

/* a game world of the game list (112 bytes) */
struct MediusGameListResponse
{
    char MessageID[21];   /* +0x0 */
    int StatusCode;       /* +0x18 */
    int MediusWorldID;    /* +0x1c (-1: none) */
    char GameName[64];    /* +0x20 */
    /* +0x60..+0x68: socom-port-mod-znet2 corrected the names (part 1 guessed PlayerCount /
     * MaxPlayers / GameLevel): cbGetRandomGameList 0x325de0 filters on +0x68 as the player count,
     * GamePassesFilters 0x32f720 on +0x60 == 3 (locked) */
    int WorldStatus;      /* +0x60 */
    int GameHostType;     /* +0x64 */
    int PlayerCount;      /* +0x68 */
    char EndOfList;       /* +0x6c */
};

/* a player of a room's player list (332 bytes; its assignment 0x330810). port: names guessed */
struct MediusLobbyWorldPlayerListResponse
{
    char MessageID[21];     /* +0x0 */
    int StatusCode;         /* +0x18 */
    int PlayerStatus;       /* +0x1c */
    int AccountID;          /* +0x20 */
    char AccountName[32];   /* +0x24 */
    char Stats[256];        /* +0x44 */
    int ConnectionClass;    /* +0x144 */
    char EndOfList;         /* +0x148 */
};

/* a chat line forwarded to the room (128 bytes; the vector copy 0x3315b0). port: names guessed */
struct MediusChatFwdMessage
{
    char MessageID[21];       /* +0x0 */
    int OriginatorAccountID;  /* +0x18 */
    char OriginatorName[32];  /* +0x1c */
    int MessageType;          /* +0x3c */
    char Message[64];         /* +0x40 */
};

/* MediusInitializeBare's parameters (AuxInitNetwork 0x328b90: the three lobby callbacks and a
 * 30000 ms value). port: names guessed */
struct MediusInitializeBareParams
{
    void (*ChatCallback)(int, int, int, struct MediusChatFwdMessage *);                          /* +0x0 */
    void (*BuddyPermissionCallback)(int, int, int, struct MediusAddToBuddyListFwdConfirmationRequest *); /* +0x4 */
    void (*ErrorCallback)(int, int, int, struct MediusErrorMessage *);                          /* +0x8 */
    int Unused;                                                                                 /* +0xc (not set by the game) */
    int TimeoutMs;                                                                              /* +0x10 */
};

/* MediusConnect's request (AuxInitNetwork): the connection, then the result callback */
struct MediusConnectRequest
{
    NetConnectionInfo ConnectInfo;   /* +0x0 */
    void (*Callback)(int);           /* +0x9c the lobby connection index, -1 on failure (cbConnect) */
    /* +0xa0 / +0xa4: 0 in AuxInitNetwork; cbClientConnect / cbClientDisconnect in
     * LobbyServerConnectStateHandler 0x32d420 (socom-port-mod-znet2: typed from there) */
    void (*ClientConnectCallback)(int, int, const char *);
    void (*ClientDisconnectCallback)(int, int, const char *);
};

/* MediusGetChannels' request (GetRoomList 0x32dfa0, 42 bytes) */
struct MediusChannelListRequest
{
    char MessageID[21];   /* +0x0 MediusCreateMessageID */
    char SessionKey[17];  /* +0x15 */
    short PageID;         /* +0x26 */
    short PageSize;       /* +0x28 (999) */
};

/* MediusSendEndGameReport's record (CZOnlineLobby::SendEndGameReport 0x322420: a 128-byte stack
 * block; only these members are set). port: names guessed */
struct MediusEndGameReport
{
    char SessionKey[17];       /* +0x0 */
    int MediusWorldID;         /* +0x14 */
    char Unknown_18[64];       /* +0x18 (first byte 0) */
    char Unknown_58[32];       /* +0x58 (first byte 0) */
    int Unknown_78;            /* +0x78 0 */
    int Unknown_7c;
};

/* MediusGetLobbyPlayers' request (CZOnlineLobby::RefreshRoomPlayerList 0x326c40, 44 bytes) */
struct MediusLobbyWorldPlayerListRequest
{
    char MessageID[21];   /* +0x0 MediusCreateMessageID (type 33) */
    char SessionKey[17];  /* +0x15 */
    int MediusWorldID;    /* +0x28 the room's world */
};

#ifdef __cplusplus
extern "C" {
#endif
int MediusGetLobbyPlayers(struct MediusLobbyWorldPlayerListRequest *request, void (*callback)(int, int, int, struct MediusLobbyWorldPlayerListResponse *));
int MediusSendEndGameReport(struct MediusEndGameReport *report);
int MediusInitializeBare(struct MediusInitializeBareParams *params, int *result);
int MediusCloseBare(void);
int MediusVersionClient(char *version);
int MediusGetBuildTimeStamp(char *stamp);
int MediusSetDefaultConnectInfo(NetConnectionInfo *info, int type, const char *address, int port, int flag);
int MediusConnect(struct MediusConnectRequest *request, int *result);
int MediusDisconnect(void);
int MediusUpdate(void);
int MediusGetLastNetUpdateError(void);
int MediusCreateMessageID(const char *sessionKey, int type, void *request);
int MediusGetChannels(struct MediusChannelListRequest *request, void (*callback)(int, int, int, struct MediusChannelListResponse *));
#ifdef __cplusplus
}
#endif

/* ---- socom-port-mod-znet2 (2026-11-14): the rest of the lobby (zNetMedius.cpp: the state handlers, clans,
 * ladders, chat, game lists). Same rules: no DWARF, layouts from the game's stack frames (memset sizes,
 * the stores into the request, the loads from the response), member names after the SDK's style and
 * guessed (port) unless the game's strings name them. A request starts with the message id (21 bytes,
 * MediusCreateMessageID) and, for most, the session key (17 bytes at +0x15); a response with the
 * message id and its MediusCallbackStatus at +0x18 (0 = success). */

/* ---- the state handlers' requests */
struct MediusSessionBeginRequest      /* SessionBeginStateHandler 0x32c2d0 (no session key yet) */
{
    char MessageID[21];       /* +0x0 "SessionBegin" */
    int ConnectionClass;      /* +0x18 1 */
};
struct MediusSessionBeginResponse
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    char SessionKey[17];      /* +0x1c */
};
struct MediusSessionEndRequest        /* EndSessionStateHandler 0x32c190 (38 bytes, type 54) */
{
    char MessageID[21];
    char SessionKey[17];
};
struct MediusSessionEndResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusVersionServerRequest     /* 38 bytes, type 0xffffff */
{
    char MessageID[21];
    char SessionKey[17];
};
struct MediusVersionServerResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusTextFilterRequest        /* AccountRegistrationStateHandler 0x32c480 (108 bytes, type 90) */
{
    char MessageID[21];
    char SessionKey[17];
    int TextFilterType;       /* +0x28 0 */
    char Text[64];            /* +0x2c */
};
struct MediusTextFilterResponse       /* cbFilterAcctName 0x32c540: the result at +0x58 (negative: refused) */
{
    char MessageID[21];
    char Text[64];            /* +0x15 */
    int StatusCode;           /* +0x58 */
};
struct MediusAccountRegistrationRequest /* cbFilterAcctName (108 bytes, type 5) */
{
    char MessageID[21];
    char SessionKey[17];
    int AccountType;          /* +0x28 1 */
    char AccountName[32];     /* +0x2c */
    char Password[32];        /* +0x4c */
};
struct MediusAccountRegistrationResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusAccountLoginRequest      /* AccountLoginStateHandler 0x32c8d0 (102 bytes, type 3) */
{
    char MessageID[21];
    char SessionKey[17];
    char AccountName[32];     /* +0x26 */
    char Password[32];        /* +0x46 */
};
struct MediusAccountLoginResponse     /* cbAccountLogin 0x32c9a0 */
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    int AccountID;            /* +0x1c */
    int Unknown_20;
    int Unknown_24;
    NetConnectionInfo ConnectInfo; /* +0x28 the lobby server (its ServerKey +0x60 = the account's public key) */
};
struct MediusCreateChannelRequest     /* CreateRoomStateHandler 0x32b300 (144 bytes, type 18) */
{
    char MessageID[21];
    char SessionKey[17];
    int ApplicationID;        /* +0x28 10020 */
    int MaxPlayers;           /* +0x2c the room's LIMIT */
    char LobbyName[64];       /* +0x30 */
    char LobbyPassword[32];   /* +0x70 */
};
struct MediusCreateChannelResponse
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    int MediusWorldID;        /* +0x1c */
};
struct MediusFindWorldByNameRequest   /* cbCreateRoom 0x32b4a0, cbCreateGame 0x32be70 (108 bytes, type 21) */
{
    char MessageID[21];
    char SessionKey[17];
    char Name[64];            /* +0x26 */
    int WorldType;            /* +0x68 1 a room, 0 a game */
};
struct MediusFindWorldByNameResponse
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    int ApplicationID;        /* +0x1c */
    char ApplicationName[32]; /* +0x20 */
    int ApplicationType;      /* +0x40 */
    int MediusWorldID;        /* +0x44 */
};
struct MediusJoinChannelRequest       /* JoinRoomStateHandler 0x32b6d0 (76 bytes, type 43) */
{
    char MessageID[21];
    char SessionKey[17];
    int MediusWorldID;        /* +0x28 */
    char LobbyPassword[32];   /* +0x2c */
};
struct MediusJoinChannelResponse
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    NetConnectionInfo ConnectInfo; /* +0x1c the room's server */
};
struct MediusJoinGameRequest          /* JoinGameStateHandler 0x32b950 (128 bytes, type 42) */
{
    char MessageID[21];
    char SessionKey[17];
    int MediusWorldID;        /* +0x28 */
    char GamePassword[32];    /* +0x2c PlayerGamePassword */
    int JoinType;             /* +0x4c 0 */
    unsigned char Unknown_50[0x30];
};
struct MediusJoinGameResponse
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    int GameHostType;         /* +0x1c */
    NetConnectionInfo ConnectInfo; /* +0x20 the game's server */
};
struct MediusCreateGameRequest        /* CreateNewGameStateHandler 0x32bbf0 (176 bytes, type 16) */
{
    char MessageID[21];
    char SessionKey[17];
    int ApplicationID;        /* +0x28 10020 */
    int MinPlayers;           /* +0x2c 2 */
    int MaxPlayers;           /* +0x30 NumPlayersValve (8) */
    int GameLevel;            /* +0x34 MapToGameLevel */
    char GameName[64];        /* +0x38 */
    char GamePassword[32];    /* +0x78 */
    int PlayerSkillLevel;     /* +0x98 0 */
    int RulesSet;             /* +0x9c 0 */
    int LobbyWorldID;         /* +0xa0 */
    int PerformanceMetric;    /* +0xa4 65000 */
    int ClanAffiliation;      /* +0xa8 g_iCreateGameClanAffiliation */
    int Unknown_ac;
};
struct MediusCreateGameResponse
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    int MediusWorldID;        /* +0x1c */
};
struct MediusPlayerInfoRequest        /* LobbyActiveStateHandler 0x32c020 (44 bytes, type 35) */
{
    char MessageID[21];
    char SessionKey[17];
    int AccountID;            /* +0x28 */
};
struct MediusPlayerInfoResponse       /* cbGetPlayerStats 0x32d8b0 */
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    char AccountName[32];     /* +0x1c */
    int ApplicationID;        /* +0x3c */
    int PlayerStatus;         /* +0x40 */
    int ConnectionClass;      /* +0x44 */
    char Stats[256];          /* +0x48 "Q<rating:10><team><j|n><description>" */
};
struct MediusGetPolicyRequest         /* 44 bytes, type 36 */
{
    char MessageID[21];
    char SessionKey[17];
    int Policy;               /* +0x28 0 */
};
struct MediusGetPolicyResponse        /* cbGetPolicyRequest 0x32dbb0 */
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    char PolicyText[256];     /* +0x1c UsagePolicy */
};
struct MediusChatToggleRequest        /* LobbyReadyToConnectStateHandler 0x32ccc0 (44 bytes, type 89) */
{
    char MessageID[21];
    char SessionKey[17];
    int ChatToggle;           /* +0x28 1 on entry, 0 on exit */
};
struct MediusChatToggleResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusUpdateClientStateRequest /* 0 / 1 / 2 by the ready-to-connect tick, cbLobbyServerConnect, the exit */
{
    char SessionKey[17];      /* +0x0 */
    int UserAction;           /* +0x14 */
};
struct MediusPlayerReport             /* LobbyReadyToConnectStateHandler's report */
{
    char SessionKey[17];      /* +0x0 */
    int MediusWorldID;        /* +0x14 */
    char Stats[256];          /* +0x18 */
};
struct MediusWorldReport              /* the session master's report of its game */
{
    char SessionKey[17];      /* +0x0 */
    int MediusWorldID;        /* +0x14 */
    int Unknown_18;           /* +0x18 0 */
    char GameName[64];        /* +0x1c */
    char GameStats[256];      /* +0x5c "0" */
    int MinPlayers;           /* +0x15c 2 */
    int MaxPlayers;           /* +0x160 NumPlayersValve */
    int FriendlyFire;         /* +0x164 mp_friendly_fire */
    int Unknown_168;          /* +0x168 0 */
    int GameLevel;            /* +0x16c the mission's number (atoi of its database name + 2) */
    int LobbyWorldID;         /* +0x170 */
    int PerformanceMetric;    /* +0x174 */
    int ClanAffiliation;      /* +0x178 */
    int WorldStatus;          /* +0x17c 3 locked, 1 in the menus, 2 else */
};
struct MediusSetGameListFilterRequest /* cbLobbyServerConnect 0x32d630 (52 bytes, type 55) */
{
    char MessageID[21];
    char SessionKey[17];
    int FilterField;          /* +0x28 7 */
    int ComparisonOperator;   /* +0x2c 2 */
    int BaselineValue;        /* +0x30 LobbyWorldID */
};
struct MediusSetGameListFilterResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusAccountUpdateStatsRequest /* cbGetPlayerStats (294 bytes, type 8) */
{
    char MessageID[21];
    char SessionKey[17];
    char Stats[256];          /* +0x26 */
};
struct MediusStatusResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusGameWorldPlayerListRequest /* RefreshDMEJoinedCount 0x32d2d0 (44 bytes, type 31) */
{
    char MessageID[21];
    char SessionKey[17];
    int MediusWorldID;        /* +0x28 */
};
struct MediusGameWorldPlayerListResponse /* one player of a game (cbRefreshDMEJoinedCount 0x32d390) */
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    int AccountID;            /* +0x1c */
    char AccountName[32];     /* +0x20 */
    char Stats[256];          /* +0x40 (Stats[12] 'j': joined the DME game) */
    int ConnectionClass;      /* +0x140 */
    char EndOfList;           /* +0x144 */
};

#ifdef __cplusplus
extern "C" {
#endif
int MediusSessionBegin(struct MediusSessionBeginRequest *request, void (*callback)(int, int, int, struct MediusSessionBeginResponse *));
int MediusSessionEnd(struct MediusSessionEndRequest *request, void (*callback)(int, int, int, struct MediusSessionEndResponse *));
int MediusVersionServer(struct MediusVersionServerRequest *request, void (*callback)(int, int, int, struct MediusVersionServerResponse *));
int MediusTextFilter(struct MediusTextFilterRequest *request, void (*callback)(int, int, int, struct MediusTextFilterResponse *));
int MediusAccountRegistration(struct MediusAccountRegistrationRequest *request, void (*callback)(int, int, int, struct MediusAccountRegistrationResponse *));
int MediusAccountLogin(struct MediusAccountLoginRequest *request, void (*callback)(int, int, int, struct MediusAccountLoginResponse *));
int MediusCreateChannel(struct MediusCreateChannelRequest *request, void (*callback)(int, int, int, struct MediusCreateChannelResponse *));
int MediusFindWorldByName(struct MediusFindWorldByNameRequest *request, void (*callback)(int, int, int, struct MediusFindWorldByNameResponse *));
int MediusJoinChannel(struct MediusJoinChannelRequest *request, void (*callback)(int, int, int, struct MediusJoinChannelResponse *));
int MediusJoinGame(struct MediusJoinGameRequest *request, void (*callback)(int, int, int, struct MediusJoinGameResponse *));
int MediusCreateGame(struct MediusCreateGameRequest *request, void (*callback)(int, int, int, struct MediusCreateGameResponse *));
int MediusGetPlayerInfo(struct MediusPlayerInfoRequest *request, void (*callback)(int, int, int, struct MediusPlayerInfoResponse *));
int MediusGetPolicy(struct MediusGetPolicyRequest *request, void (*callback)(int, int, int, struct MediusGetPolicyResponse *));
int MediusChatToggleFilter(struct MediusChatToggleRequest *request, void (*callback)(int, int, int, struct MediusChatToggleResponse *));
int MediusUpdateClientState(struct MediusUpdateClientStateRequest *request);
int MediusSendPlayerReport(struct MediusPlayerReport *report);
int MediusSendWorldReport(struct MediusWorldReport *report);
int MediusSetGameListFilter(struct MediusSetGameListFilterRequest *request, void (*callback)(int, int, int, struct MediusSetGameListFilterResponse *));
int MediusAccountUpdateStats(struct MediusAccountUpdateStatsRequest *request, void (*callback)(int, int, int, struct MediusStatusResponse *));
int MediusGetGamePlayers(struct MediusGameWorldPlayerListRequest *request, void (*callback)(int, int, int, struct MediusGameWorldPlayerListResponse *));
#ifdef __cplusplus
}
#endif

/* ---- clans */
struct MediusRemovePlayerFromClanRequest /* QuitClan 0x32db10, RemovePlayerFromClan 0x323d80 (48 bytes, type 67) */
{
    char MessageID[21];
    char SessionKey[17];
    int PlayerAccountID;      /* +0x28 */
    int ClanID;               /* +0x2c */
};
struct MediusRemovePlayerFromClanResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusClanRequest              /* the requests of one clan id: DisbandClan 0x322af0 (type 62),
                                       * GetClanRoster 0x322d80 (type 94); 44 bytes */
{
    char MessageID[21];
    char SessionKey[17];
    int ClanID;               /* +0x28 */
};
struct MediusDisbandClanResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusGetClanMemberListResponse /* one member (cbGetClanMemberList 0x322eb0: the status is at +0x3c) */
{
    char MessageID[21];
    int AccountID;            /* +0x18 */
    char AccountName[32];     /* +0x1c */
    int StatusCode;           /* +0x3c */
    char EndOfList;           /* +0x40 */
};
struct MediusLadderPositionRequest    /* GetClanMemberRanking 0x3230d0, GetLadderRanking (56 bytes, type 87) */
{
    char MessageID[21];
    char SessionKey[17];
    int AccountID;            /* +0x28 */
    int LadderStatIndex;      /* +0x2c 1 */
    int Unknown_30;           /* +0x30 10 */
    int SortOrder;            /* +0x34 1 */
};
struct MediusLadderPositionResponse   /* the status is at +0x1c */
{
    char MessageID[21];
    int LadderPosition;       /* +0x18 */
    int StatusCode;           /* +0x1c */
    int TotalRankings;        /* +0x20 */
};
struct MediusPageRequest              /* the paged clan lists: GetClanInvitationsSent (type 70),
                                       * CheckMyClanInvitations (type 69), GetMyClans (type 84); 48 bytes */
{
    char MessageID[21];
    char SessionKey[17];
    int Start;                /* +0x28 (1 for GetMyClans, else 0) */
    int PageSize;             /* +0x2c 999 */
};
struct MediusGetClanInvitationsSentResponse /* one invitation (cbGetClanInvitationsSent 0x323670) */
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    int AccountID;            /* +0x1c */
    char AccountName[32];     /* +0x20 */
    char InviteMessage[200];  /* +0x40 */
    int ResponseStatus;       /* +0x108 0 undecided, 1 accepted, 2 declined */
    int ResponseTime;         /* +0x10c */
    char EndOfList;           /* +0x110 */
};
struct MediusAddPlayerToClanRequest   /* 244 bytes, type 66 */
{
    char MessageID[21];
    char SessionKey[17];
    int PlayerAccountID;      /* +0x28 */
    char Message[200];        /* +0x2c */
};
struct MediusAddPlayerToClanResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusRevokeClanInvitationRequest /* 44 bytes, type 72 */
{
    char MessageID[21];
    char SessionKey[17];
    int PlayerAccountID;      /* +0x28 */
};
struct MediusRevokeClanInvitationResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusAccountGetIDRequest      /* InvitePlayerToClan 0x3241c0 (70 bytes, type 1) */
{
    char MessageID[21];
    char SessionKey[17];
    char AccountName[32];     /* +0x26 */
};
struct MediusAccountGetIDResponse     /* the status is at +0x1c */
{
    char MessageID[21];
    int AccountID;            /* +0x18 */
    int StatusCode;           /* +0x1c */
};
struct MediusInvitePlayerToClanRequest /* 244 bytes, type 68 */
{
    char MessageID[21];
    char SessionKey[17];
    int PlayerAccountID;      /* +0x28 */
    char InviteMessage[200];  /* +0x2c */
};
struct MediusInvitePlayerToClanResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusCreateClanRequest        /* cbFilterClanName 0x3246a0 (76 bytes, type 61) */
{
    char MessageID[21];
    char SessionKey[17];
    int ApplicationID;        /* +0x28 (not set: 0) */
    char ClanName[32];        /* +0x2c */
};
struct MediusCreateClanResponse
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    int ClanID;               /* +0x1c */
};
struct MediusUpdateClanStatsRequest   /* UpdateClanStats 0x324880 (300 bytes, type 85) */
{
    char MessageID[21];
    char SessionKey[17];
    int ClanID;               /* +0x28 */
    char Stats[256];          /* +0x2c "<badge:3><description>" */
};
struct MediusUpdateClanStatsResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusTransferClanLeadershipRequest /* TransferLeadership 0x32a330 (76 bytes, type 65) */
{
    char MessageID[21];
    char SessionKey[17];
    int NewLeaderAccountID;   /* +0x28 */
    char NewLeaderAccountName[32]; /* +0x2c */
};
struct MediusTransferClanLeadershipResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusSendClanMessageRequest   /* cbFilterClanMessage 0x32a640 (238 bytes, type 74) */
{
    char MessageID[21];
    char SessionKey[17];
    char Message[200];        /* +0x26 */
};
struct MediusSendClanMessageResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusGetMyClanMessagesResponse /* one message (cbGetMyClanMessages 0x32a790) */
{
    char MessageID[21];
    int StatusCode;           /* +0x18 (1: no messages) */
    int ClanID;               /* +0x1c */
    char Message[200];        /* +0x20 */
    char EndOfList;           /* +0xe8 */
};
struct MediusCheckMyClanInvitationsResponse /* one invitation to this player (InvitationItem's ctor 0x32acb0) */
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    int ClanInvitationID;     /* +0x1c */
    int ClanID;               /* +0x20 */
    int ResponseStatus;       /* +0x24 */
    char Message[200];        /* +0x28 */
    int LeaderAccountID;      /* +0xf0 */
    char LeaderAccountName[32]; /* +0xf4 */
    char EndOfList;           /* +0x114 */
};
struct MediusRespondToClanInvitationRequest /* Accept / DeclineClanInvitation 0x32af30 / 0x32aeb0 (248 bytes, type 71) */
{
    char MessageID[21];
    char SessionKey[17];
    int ClanInvitationID;     /* +0x28 */
    int Response;             /* +0x2c 1 accept, 2 decline */
    char Message[200];        /* +0x30 */
};
struct MediusRespondToClanInvitationResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusGetMyClansResponse       /* the player's clan (cbGetMyClans 0x32b0d0; the lobby keeps a copy:
                                       * StoredClanInfo, 368 bytes) */
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    int ClanID;               /* +0x1c */
    int ApplicationID;        /* +0x20 */
    char ClanName[32];        /* +0x24 */
    int LeaderAccountID;      /* +0x44 */
    char LeaderAccountName[32]; /* +0x48 */
    char ClanStats[256];      /* +0x68 "<badge:3><description>" */
    int ClanStatus;           /* +0x168 */
    char EndOfList;           /* +0x16c */
};

#ifdef __cplusplus
extern "C" {
#endif
int MediusRemovePlayerFromClan(struct MediusRemovePlayerFromClanRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusRemovePlayerFromClanResponse *));
int MediusDisbandClan(struct MediusClanRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusDisbandClanResponse *));
int MediusGetClanMemberList(struct MediusClanRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusGetClanMemberListResponse *));
int MediusLadderPosition(struct MediusLadderPositionRequest *request, void (*callback)(int, int, int, struct MediusLadderPositionResponse *));
int MediusGetClanInvitationsSent(struct MediusPageRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusGetClanInvitationsSentResponse *));
int MediusAddPlayerToClan(struct MediusAddPlayerToClanRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusAddPlayerToClanResponse *));
int MediusRevokeClanInvitation(struct MediusRevokeClanInvitationRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusRevokeClanInvitationResponse *));
int MediusAccountGetID(struct MediusAccountGetIDRequest *request, void (*callback)(int, int, int, struct MediusAccountGetIDResponse *));
int MediusInvitePlayerToClan(struct MediusInvitePlayerToClanRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusInvitePlayerToClanResponse *));
int MediusCreateClan(struct MediusCreateClanRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusCreateClanResponse *));
int MediusUpdateClanStats(struct MediusUpdateClanStatsRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusUpdateClanStatsResponse *));
int MediusTransferClanLeadership(struct MediusTransferClanLeadershipRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusTransferClanLeadershipResponse *));
int MediusSendClanMessage(struct MediusSendClanMessageRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusSendClanMessageResponse *));
int MediusCheckMyClanInvitations(struct MediusPageRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusCheckMyClanInvitationsResponse *));
int MediusRespondToClanInvitation(struct MediusRespondToClanInvitationRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusRespondToClanInvitationResponse *));
int MediusGetMyClans(struct MediusPageRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusGetMyClansResponse *));
#ifdef __cplusplus
}
#endif
/* ---- announcements and chat */
struct MediusGetAnnouncementsRequest  /* GetAnnouncements 0x3249c0 (44 bytes, type 24) */
{
    char MessageID[21];
    char SessionKey[17];
    int ApplicationID;        /* +0x28 (not set: 0) */
};
struct MediusGetAnnouncementsResponse /* one announcement (cbGetAnnouncements 0x324a50) */
{
    char MessageID[21];
    int StatusCode;           /* +0x18 (1: none) */
    int AnnouncementID;       /* +0x1c */
    char Announcement[1000];  /* +0x20 */
    char EndOfList;           /* +0x408 */
};
struct MediusGetMyClanMessagesRequest /* cbGetAnnouncements (52 bytes, type 73) */
{
    char MessageID[21];
    char SessionKey[17];
    int ClanID;               /* +0x28 */
    int Start;                /* +0x2c 1 */
    int PageSize;             /* +0x30 999 */
};
struct MediusChatMessageRequest       /* cbFilterChat 0x324de0 (112 bytes, type 49) */
{
    char MessageID[21];
    char SessionKey[17];
    int MessageType;          /* +0x28 0 */
    int TargetID;             /* +0x2c -1 */
    char Message[64];         /* +0x30 */
};

#ifdef __cplusplus
extern "C" {
#endif
int MediusGetAnnouncements(struct MediusGetAnnouncementsRequest *request, void (*callback)(int, int, int, struct MediusGetAnnouncementsResponse *));
int MediusGetMyClanMessages(struct MediusGetMyClanMessagesRequest *request, void (*callback)(enum MediusErrorCode, enum MediusErrorCode, enum MediusErrorCode, struct MediusGetMyClanMessagesResponse *));
int MediusSendChatMessage(struct MediusChatMessageRequest *request);
#ifdef __cplusplus
}
#endif
/* ---- the game and room lists, ladders */
struct MediusBanPlayerRequest         /* BanSelfFromGame 0x32dc10 (56 bytes, type 86) */
{
    char MessageID[21];
    char SessionKey[17];
    int PlayerAccountID;      /* +0x28 */
    int BanSeconds;           /* +0x2c 120 */
    int MediusWorldID;        /* +0x30 */
    int Unknown_34;           /* +0x34 0 */
};
struct MediusBanPlayerResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusClearGameListFilterRequest /* JoinGame 0x3254f0 "RANDOM" (44 bytes, type 12) */
{
    char MessageID[21];
    char SessionKey[17];
    int FilterField;          /* +0x28 7 */
};
struct MediusClearGameListFilterResponse
{
    char MessageID[21];
    int StatusCode;
};
struct MediusGameListRequest          /* GetGameList 0x32ea80, cbClearGameListFilter (48 bytes, type 32) */
{
    char MessageID[21];
    char SessionKey[17];
    int ApplicationID;        /* +0x28 10020 */
    short PageID;             /* +0x2c */
    short PageSize;           /* +0x2e 999 */
};
struct MediusGameInfoRequest          /* 44 bytes, type 28 */
{
    char MessageID[21];
    char SessionKey[17];
    int MediusWorldID;        /* +0x28 */
};
struct MediusGameInfoResponse         /* a game's details (cbGameInfo 0x32f200 copies it whole into the
                                       * game: RoomGame +0x74, 396 bytes). The game's use of the fields:
                                       * GameLevel = friendly fire, RulesSet = the mission number,
                                       * GenericField1..3 = the room's world, the performance metric, the
                                       * clan side (see MediusCreateGameRequest / MediusWorldReport) */
{
    char MessageID[21];       /* +0x0 (first byte 0: no details yet) */
    int StatusCode;           /* +0x18 */
    int ApplicationID;        /* +0x1c */
    int MinPlayers;           /* +0x20 */
    int MaxPlayers;           /* +0x24 */
    int GameLevel;            /* +0x28 */
    int PlayerSkillLevel;     /* +0x2c */
    int PlayerCount;          /* +0x30 */
    char GameStats[256];      /* +0x34 */
    char GameName[64];        /* +0x134 */
    int RulesSet;             /* +0x174 */
    int GenericField1;        /* +0x178 */
    int GenericField2;        /* +0x17c */
    int GenericField3;        /* +0x180 */
    int WorldStatus;          /* +0x184 (3: locked) */
    int GameHostType;         /* +0x188 */
};
struct MediusGetWorldSecurityLevelRequest /* 48 bytes, type 29 */
{
    char MessageID[21];
    char SessionKey[17];
    int MediusWorldID;        /* +0x28 */
    int AppType;              /* +0x2c 0 */
};
struct MediusGetWorldSecurityLevelResponse
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    int MediusWorldID;        /* +0x1c */
    int AppType;              /* +0x20 */
    int SecurityLevel;        /* +0x24 1: a password */
};
struct MediusChannelInfoRequest       /* cbRoomList 0x32e050 (44 bytes, type 29; message id "DoUpdate"
                                       * on the list's last room) */
{
    char MessageID[21];
    char SessionKey[17];
    int MediusWorldID;        /* +0x28 */
};
struct MediusChannelInfoResponse      /* cbChannelInfo 0x32e810 */
{
    char MessageID[21];
    int StatusCode;           /* +0x18 */
    char LobbyName[64];       /* +0x1c */
    int ActivePlayerCount;    /* +0x5c */
    int MaxPlayers;           /* +0x60 */
};
struct MediusLadderListRequest        /* GetSurroundingLadderPosition 0x3295e0 (60 bytes, type 88) */
{
    char MessageID[21];
    char SessionKey[17];
    int LadderStatIndex;      /* +0x28 1 */
    int Unknown_2c;           /* +0x2c 10 */
    int SortOrder;            /* +0x30 1 */
    int StartPosition;        /* +0x34 */
    int PageSize;             /* +0x38 */
};
struct MediusLadderListResponse       /* one row (the status is at +0x40) */
{
    char MessageID[21];
    int AccountID;            /* +0x18 */
    char AccountName[32];     /* +0x1c */
    int LadderPosition;       /* +0x3c */
    int StatusCode;           /* +0x40 */
    char EndOfList;           /* +0x44 */
};

#ifdef __cplusplus
extern "C" {
#endif
int MediusBanPlayer(struct MediusBanPlayerRequest *request, void (*callback)(int, int, int, struct MediusBanPlayerResponse *));
int MediusClearGameListFilter(struct MediusClearGameListFilterRequest *request, void (*callback)(int, int, int, struct MediusClearGameListFilterResponse *));
int MediusGetGames(struct MediusGameListRequest *request, void (*callback)(int, int, int, struct MediusGameListResponse *));
int MediusGetGameInfo(struct MediusGameInfoRequest *request, void (*callback)(int, int, int, struct MediusGameInfoResponse *));
int MediusGetWorldSecurityLevel(struct MediusGetWorldSecurityLevelRequest *request, void (*callback)(int, int, int, struct MediusGetWorldSecurityLevelResponse *));
int MediusGetChannelInfo(struct MediusChannelInfoRequest *request, void (*callback)(int, int, int, struct MediusChannelInfoResponse *));
int MediusLadderList(struct MediusLadderListRequest *request, void (*callback)(int, int, int, struct MediusLadderListResponse *));
#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_MEDIUS_H */
