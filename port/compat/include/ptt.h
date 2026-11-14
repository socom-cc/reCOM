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
void PTT_HeartbeatPrepare();

int PTTServer_Init();
int PTTServer_Start(const char *server, unsigned short port);
int PTTServer_Sync(void *result, int size, int wait);
int PTTServer_QueryWANAddress();
int PTTServer_PermitWANAddress(unsigned int address, unsigned int port);
int PTTServer_Stop();
int PTTServer_Shutdown();

#endif /* SOCOM_COMPAT_PTT_H */
