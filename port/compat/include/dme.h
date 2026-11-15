/* Port compatibility header: declarations the game source takes from the SCE-RT
 * Medius DME library ("dme version: 1.16.S033", string at 0x43e1f8; C API such as
 * NetCreateObject at 0x41cb18). The original header name is unknown: `dme.h` is a
 * port guess. Shared and append-only: add declarations, never rewrite or reorder
 * others' lines. The online layer is stubbed offline later; these exist so the
 * declarations in src compile. */
#ifndef SOCOM_COMPAT_DME_H
#define SOCOM_COMPAT_DME_H

/* Passed by value in one GPR word (CZNetwork::zNetCreateObject 0x321860 forwards
 * a2/a3 to NetCreateObject; CZBroadcastSchedule::CZBroadcastSchedule 0x322300 stores
 * a2 with sw). Enumerators unknown: port: unproven. */
enum NetOwnershipStatus {};
enum NetObjectLifespan {};
enum NetThresholdMethod {};

/* By value in cbDMENetPingCallback__F12NetErrorCodePcUi (zNetMedius.cpp). Enumerators
 * unknown: port: unproven. */
enum NetErrorCode {};

/* ---- socom-port-mod-znet (2026-11-14): the records and calls of the DME layer (zNetDme.cpp) and
 * the lobby (zNetMedius.cpp). No DWARF for any SDK record: layouts from the game's copies and
 * stack frames (offsets given), member names guessed where noted. The calls are C (unmangled
 * symbols); the port's offline stand-ins are in port/compat/dme_offline.cpp. */

/* a server connection's address and keys (156 bytes; copied by value: CZOnlineLobby::
 * SetConnectionInfo 0x329f00, AuxInitNetwork 0x328b90) */
typedef struct NetConnectionInfo
{
    int Type;                    /* +0x0 */
    unsigned char Address[48];   /* +0x4 port: what MediusSetDefaultConnectInfo fills (not read by the game) */
    int WorldID;                 /* +0x34 port: name guessed */
    unsigned char ServerKey[64]; /* +0x38 an RSA public key (AuxInitNetwork clears it) */
    char SessionKey[17];         /* +0x78 */
    char AccessKey[17];          /* +0x89 */
} NetConnectionInfo;

/* NetInitialize's parameters (CZNetwork::zNetInitialize 0x321ca0, 32 bytes) */
typedef struct NetInitializeParams
{
    int Unknown_00;
    int Unknown_04;              /* +0x4 256 */
    int Unknown_08;              /* +0x8 10020 */
    unsigned char *KeyPair;      /* +0xc CZOnlineLobby::GetKeyPair */
    unsigned char Unknown_10[16];
} NetInitializeParams;

/* the result blocks of NetInitialize / NetConnect: the error code at +0x4 (and the connection
 * index at +0x8) */
typedef struct NetOutParams
{
    int Unknown_00;
    int ErrorCode;               /* +0x4 0 = success */
    int ConnectionIndex;         /* +0x8 (NetConnect) */
    int Unknown_0c;
} NetOutParams;

/* NetConnect's parameters (CZNetwork::zNetConnect 0x321630, 208 bytes) */
typedef struct NetConnectParams
{
    int Unknown_00;
    NetConnectionInfo ConnectInfo;                         /* +0x4 */
    unsigned char Unknown_a0[24];
    int Unknown_b8;                                        /* +0xb8 0 */
    int Unknown_bc;                                        /* +0xbc 0 */
    void (*ConnectCallback)(int, int, const char *);       /* +0xc0 */
    void (*DisconnectCallback)(int, int, const char *);    /* +0xc4 */
    unsigned char Unknown_c8[8];
} NetConnectParams;

/* NetJoin's 50-byte parameter block (CZNetwork::zNetJoin 0x3215b0 copies a zeroed one) */
typedef struct NetJoinParams
{
    unsigned char Data[50];
} NetJoinParams;

#ifdef __cplusplus
extern "C" {
#endif
int NetSetDefaultInitializeParams(NetInitializeParams *params);
int NetInitialize(NetInitializeParams *params, NetOutParams *out);
int NetGetMyIpAddress(char *address);
int NetClose(void);
int NetTick(void);
int NetUpdate(void);
int NetSetDefaultConnectParams(NetConnectParams *params);
int NetConnect(NetConnectParams *params, NetOutParams *out);
int NetDisconnect(int connection);
int NetJoin(int connection, NetJoinParams *params, int numObjects, int numStreams, int unknown_t0, int unknown_t1,
    void (*joinCallback)(int, int), void (*leaveCallback)(int, int));
int NetLeave(int connection);
int NetGetValidClientCount(int *count, int connection);
int NetGetSessionMasterClientIndex(int *index, int connection);
int NetGetMyClientIndex(int *index, int connection);
int NetGetClient(void **client, int connection, int index);
int NetGetObject(void **object, int index);
int NetGetLocalTime(int *time);
int NetGetTime(int *time);
int NetCreateObject(int *index, enum NetOwnershipStatus ownership, enum NetObjectLifespan lifespan, unsigned int a,
    int b, unsigned int c, int d, void *data, char *name, int e);
int NetSendApplicationMessage(int messageClass, int connection, int client, int type, int length, unsigned char *data);
int NetRegisterRemoteObjectCallback(int type, void (*createCallback)(int, int), void (*updateCallback)(int, int, int),
    void (*destroyCallback)(int, int));
#ifdef __cplusplus
}
#endif

/* ---- socom-port-mod-znet2 (2026-11-14): the lobby's ping of its connection
 * (LobbyReadyToConnectStateHandler 0x32ccc0: the lobby connection, 0xffff, cbDMENetPingCallback, which
 * gets the error, a text and the time) */
#ifdef __cplusplus
extern "C" {
#endif
int NetPing(int connection, int unknown, void (*callback)(enum NetErrorCode, char *, unsigned int));
/* the application packets (DMERegister 0x201920, src/gamez/zFTS/fts_network_dme.cpp): a message
 * started, one field per member of a template (the field's address in the template, its size, its
 * count), then registered with its packet-type word and handler; and the client's own net object
 * (ftsNetworkPlayerInit 0x2014d0) */
int NetRegisterMessageStart(void);
int NetMessageField(void *message, void *field, int size, int count);
int NetRegisterApplicationMessage(int *packetType, int (*handler)(int, int, int, void *));
int NetSetMyClientObject(int object);
#ifdef __cplusplus
}
#endif

/* ---- socom-port-mod-final (2026-11-14): the net object structures (CZ*State::zNetRegister*: a structure
 * started, one field per member - its id word, offset, size, type, count, broadcast schedule - registered
 * by name and size), an object freed (NetFreeObject 0x41a370) and its full update sent (0x41d4b0) */
#ifdef __cplusplus
extern "C" {
#endif
int NetRegisterObjectStart(void);
int NetObjectField(int *fieldId, int offset, int size, int type, int count, void *schedule);
int NetRegisterStructure(int *index, const char *name, int size);
int NetFreeObject(int index);
int NetSendObjectFullUpdate(int client, int index);
#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_DME_H */
