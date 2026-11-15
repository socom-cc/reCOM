/* Port compatibility header: the push-to-talk voice library (libptt client and server, EE side
 * of PTTCLNT.IRX / PTTSRVR.IRX; provider code in the ELF, C++ symbols such as PTT_Init__FPCcUi).
 * Prototypes from CZNetVoice's calls (src/gamez/zNetwork/zNetVoice.cpp); the header name is a port
 * guess. Offline stand-ins: port/compat/ptt_offline.cpp (PTT_HeartbeatPrepare is held in
 * src/gamez/zNetwork/znetwork_holding.cpp). */
#ifndef SOCOM_COMPAT_PTT_H
#define SOCOM_COMPAT_PTT_H

int PTT_Init(const char *server, unsigned int port);
int PTT_Destroy();
int PTT_DebugForceVolume(int left, int right);
int PTT_Sync(void *result, int size, int wait);
int PTT_QueryWANAddress();
int PTT_PermitWANAddress(unsigned int address, unsigned int port);
int PTT_JoinGame(unsigned int *addresses, unsigned int *ports, unsigned short channel);
int PTT_LeaveGame();
int PTT_SetChannel(int channel);
int PTT_PushToTalk(int channel);
int PTT_ReleaseTalk();
int PTT_Status();
int PTT_Heartbeat(int microseconds);
int PTT_HeartbeatPrepare(); /* socom-port-mod-znet2: int (the ELF's v0: 1 / -1) */

/* socom-port-mod-znet2 (2026-11-14): libptt's heartbeat state, which PTT_HeartbeatPrepare 0x3f02c0
 * (written from the ELF, held in src/gamez/zNetwork/znetwork_holding.cpp) uses: the client's init
 * flag (0x476c8c), the semaphore (0x476c84), the "prepared" flag (0x476c88), the 32 KB RPC buffer
 * (0x5650c0) and client record (0x56d0f0), and the RPC's end callback (0x3f0290). Offline stand-ins in
 * port/compat/ptt_offline.cpp (never initialised). */
#include <sifrpc.h>
extern bool g_isInitialized;
extern int g_heartbeatSemaphore;
extern bool g_wasPrepared;
extern unsigned int g_buffer_hb[0x8000 / 4];
extern SifRpcClientData_t g_cd_hb;
void _PTT_HeartbeatCallback(void *);

int PTTServer_Init();
int PTTServer_Start(const char *server, unsigned short port);
int PTTServer_Sync(void *result, int size, int wait);
int PTTServer_QueryWANAddress();
int PTTServer_PermitWANAddress(unsigned int address, unsigned int port);
int PTTServer_Stop();
int PTTServer_Shutdown();

#endif /* SOCOM_COMPAT_PTT_H */
