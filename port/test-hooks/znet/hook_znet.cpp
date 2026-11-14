/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/znet/build.sh); never part of a normal build.
 *
 * The demo's main menu has no multiplayer entry (its multiplayer_button is OPTIONS), so this hook
 * opens the disc's online screens from dlgMenu and lets their own anims run the zNetwork code
 * offline (socom-port-mod-znet):
 *  - dlgNetConnect (ONSTART init_socom_online: INITNETWORK -> CZOnlineLobby::Open, the connect
 *    thread -> AuxInitNetwork -> DME init and MediusConnect, which fail offline -> CONNECT_ERROR ->
 *    "STATE: Connect Failure" -> exit_connect_screen: LobbyBailout, UNINITNETWORK,
 *    PREVIOUS_SCREEN back to dlgMenu);
 *  - then dlgNetConfig (ONSTART enter_net_config: NetCnfInit / NetCnfOpen "mc0:" -> CNetCnf's
 *    state machine, whose requests fail offline -> NETCNF_ERROR), and back to dlgMenu after 300
 *    reads.
 * Traced every 30 reads on those screens: the socom_online_state valve, the lobby's state / open
 * flag, the NETCNF_ERRNO valve; each dialog change with the heap. Wraps scePadRead. */
#include <string>
#define protected public
#define private public
#include "gamez/zGame/zgame.h"
#include "gamez/zUI/zui.h"
#include "gamez/zAnim/zanim.h"
#include "gamez/zValve/zvalve.h"
#include "gamez/zNetwork/znet.h"
#include <string.h>
#include <stdio.h>
#include <malloc.h>

CGameMenu *UiGetCurMenu();
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);

namespace
{
unsigned int g_reads;
std::string g_dialog;
unsigned int g_since;
int g_step;

void heap(const char *what)
{
    struct mallinfo mi = mallinfo();
    SOCOM_PORT_TRACE("HOOK: heap %s: arena %u in use %u free %u", what, (unsigned)mi.arena, (unsigned)mi.uordblks,
        (unsigned)mi.fordblks);
}

void menu_command(int type, const char *arg)
{
    CMenuStack *stack = GetMenuStack();
    stack->m_top++;
    stack->m_cmds[stack->m_top].type = type;
    strcpy(stack->m_cmds[stack->m_top].arg, arg);
    stack->m_count++;
    SOCOM_PORT_TRACE("HOOK: read %u menu command %d %s", g_reads, type, arg);
}

int valve(const char *name)
{
    CValve *v = CValve::GetByName(name);
    return v != NULL ? (int)v->m_value : -1;
}

void trace_net()
{
    SOCOM_PORT_TRACE("HOOK: read %u %s: socom_online_state %d, lobby state %d open %d init %d, network %d init %d, "
        "NETCNF_ERRNO %d, MediusEnabled %d", g_reads, g_dialog.c_str(), valve("socom_online_state"),
        (int)theLobby.m_current_state, (int)theLobby.m_isopen, (int)theLobby.m_isinit, (int)theNetwork.m_bNetwork,
        (int)theNetwork.m_network_init, valve("NETCNF_ERRNO"), (int)theNetwork.m_bMediusEnabled);
}

/* 0 dlgMenu -> 1 dlgNetConnect -> 2 dlgMenu -> 3 dlgNetConfig -> 4 dlgMenu (done) */
void watch()
{
    CGameMenu *menu = UiGetCurMenu();

    if (menu == NULL)
        return;

    std::string name = menu->m_ReaderName.c_str();

    if (name != g_dialog)
    {
        g_dialog = name;
        g_since = g_reads;
        SOCOM_PORT_TRACE("HOOK: read %u dialog %s (step %d)", g_reads, name.c_str(), g_step);
        heap(name.c_str());
        trace_net();
    }

    unsigned int t = g_reads - g_since;

    if (g_step >= 1 && g_step <= 3 && t % 30 == 15)
        trace_net();

    if (g_step == 0 && name == "dlgMenu.rdr" && t == 60)
    {
        heap("before the online screens");
        menu_command(2, "dlgNetConnect.rdr"); /* 2: a forward switch (the history keeps dlgMenu for PREVIOUS_SCREEN) */
        g_step = 1;
    }
    else if (g_step == 1 && name == "dlgMenu.rdr" && t == 60)
    {
        SOCOM_PORT_TRACE("HOOK: read %u back from dlgNetConnect", g_reads);
        heap("back from dlgNetConnect");
        menu_command(2, "dlgNetConfig.rdr");
        g_step = 3;
    }
    else if (g_step == 3 && name == "dlgNetConfig.rdr" && t == 300)
    {
        heap("dlgNetConfig");
        menu_command(5, "dlgMenu.rdr");
        g_step = 4;
    }
    else if (g_step == 4 && name == "dlgMenu.rdr" && t == 60)
    {
        SOCOM_PORT_TRACE("HOOK: read %u online screens done", g_reads);
        heap("online screens done");
        g_step = 5;
    }
}
}

extern "C" int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
    int r = __real_scePadRead(port, slot, rdata);

    if (port == 0)
    {
        g_reads++;
        watch();
    }

    return r;
}
