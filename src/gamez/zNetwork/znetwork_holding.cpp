/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include "znet.h"
#include "gamez/zUI/zui.h"
#include <eekernel.h> /* WaitSema */
#include <sifrpc.h> /* sceSifCallRpc */
#include <ptt.h> /* port: libptt's heartbeat state (provider; compat header) */

/* @socom-skeleton body g_bJoiningRandomGame */
/* held from src/gamez/zNetwork/zNetMedius.cpp:6 */
bool g_bJoiningRandomGame;

/* @socom-skeleton body myConnectionIndex */
/* held from src/gamez/zNetwork/zNetMedius.cpp:7 */
s32 myConnectionIndex;

/* @socom-skeleton body uiv_LobbyWorldNameVar */
/* held from src/gamez/zNetwork/zNetMedius.cpp:9 */
CUIVariable* uiv_LobbyWorldNameVar;

/* @socom-skeleton body uiv_GameNameVar */
/* held from src/gamez/zNetwork/zNetMedius.cpp:10 */
CUIVariable* uiv_GameNameVar;

/* @socom-skeleton body uiv_ClanNameVar */
/* held from src/gamez/zNetwork/zNetMedius.cpp:11 */
CUIVariable* uiv_ClanNameVar;

/* @socom-skeleton body uiv_ClanDescription */
/* held from src/gamez/zNetwork/zNetMedius.cpp:12 */
CUIVariable* uiv_ClanDescription;

/* @socom-skeleton body dme_joined_count */
/* held from src/gamez/zNetwork/zNetMedius.cpp:14 */
s32 dme_joined_count;

/* @socom-skeleton body accum_dme_joined_count */
/* held from src/gamez/zNetwork/zNetMedius.cpp:15 */
s32 accum_dme_joined_count;

/* @socom-skeleton body ForceReport */
/* held from src/gamez/zNetwork/zNetMedius.cpp:17 */
bool ForceReport;

/* @socom-skeleton body PTT_HeartbeatPrepare__Fv */
/* held from src/gamez/zNetwork/zNetVoice.cpp:7 */
int PTT_HeartbeatPrepare()
{
	/* 0x3f02c0 (libptt): once initialised, the heartbeat request (40 in the buffer's second word)
	 * sent to PTTCLNT.IRX without waiting (RPC 8, the 32 KB buffer both ways, _PTT_HeartbeatCallback
	 * at its end, after the semaphore); 1 when sent, -1 else (offline: libptt is never initialised,
	 * port/compat/ptt_offline.cpp). The ELF returns the value in v0; CZNetVoice::PreTick ignores it */
	if (!g_isInitialized)
		return -1;
	WaitSema(g_heartbeatSemaphore);
	g_buffer_hb[1] = 40;
	if (sceSifCallRpc(&g_cd_hb, 8, 1, g_buffer_hb, 0x8000, g_buffer_hb, 0x8000, _PTT_HeartbeatCallback, NULL) < 0)
		return -1;
	g_wasPrepared = true;
	return 1;
}
