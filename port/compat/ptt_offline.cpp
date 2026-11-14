/* Functional port lane: offline stand-ins for the push-to-talk voice library (libptt; provider code
 * in the ELF). Not provider code; nothing here is evidence for the matching lane. Voice chat needs
 * a network game and a USB headset, neither of which the port has (HEADSETO.IRX and the PTT
 * modules are offline, port/compat/sce_iop.c). Every call answers -1, which CZNetVoice
 * (src/gamez/zNetwork/zNetVoice.cpp) takes as "no voice": PTT_Init's failure turns m_do_voice off,
 * so nothing else is reached; a failed Sync or request is skipped by each caller. The heartbeat
 * answers 0 (no time taken). */
#include <ptt.h>

int PTT_Init(const char *server, unsigned int port) { (void)server; (void)port; return -1; }
int PTT_Destroy() { return -1; }
int PTT_DebugForceVolume(int left, int right) { (void)left; (void)right; return -1; }
int PTT_Sync(void *result, int size, int wait) { (void)result; (void)size; (void)wait; return -1; }
int PTT_QueryWANAddress() { return -1; }
int PTT_PermitWANAddress(unsigned int address, unsigned int port) { (void)address; (void)port; return -1; }
int PTT_JoinGame(unsigned int *addresses, unsigned int *ports, unsigned short channel) { (void)addresses; (void)ports; (void)channel; return -1; }
int PTT_LeaveGame() { return -1; }
int PTT_SetChannel(int channel) { (void)channel; return -1; }
int PTT_PushToTalk(int channel) { (void)channel; return -1; }
int PTT_ReleaseTalk() { return -1; }
int PTT_Status() { return -1; }
int PTT_Heartbeat(int microseconds) { (void)microseconds; return 0; }

int PTTServer_Init() { return -1; }
int PTTServer_Start(const char *server, unsigned short port) { (void)server; (void)port; return -1; }
int PTTServer_Sync(void *result, int size, int wait) { (void)result; (void)size; (void)wait; return -1; }
int PTTServer_QueryWANAddress() { return -1; }
int PTTServer_PermitWANAddress(unsigned int address, unsigned int port) { (void)address; (void)port; return -1; }
int PTTServer_Stop() { return -1; }
int PTTServer_Shutdown() { return -1; }
