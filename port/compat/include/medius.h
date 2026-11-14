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
    int PlayerCount;      /* +0x60 port: names of +0x60..+0x68 guessed */
    int MaxPlayers;       /* +0x64 */
    int GameLevel;        /* +0x68 */
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
    int Unknown_a0;                  /* +0xa0 0 */
    int Unknown_a4;                  /* +0xa4 0 */
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

#endif /* SOCOM_COMPAT_MEDIUS_H */
