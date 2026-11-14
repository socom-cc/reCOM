/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-mod-hud. Shows the network-only HUD elements in single-player
 * m8, linked together with ../state/hook_state.cpp (which drives the menus, skips the intro movie
 * with CROSS and the briefing cameras with X, and traces the heap; build.sh links both):
 *  - CHUD::Init wrap: the floating team-mate names (CTeamMateNames, network only) are set up and
 *    switched on; CHUD::Tick wrap: they tick every frame (letterbox margin as CHUD::Tick sets it);
 *  - after the briefing cameras: for SOCOM_HOOK_NAMES_TIME s the test camera stands in front of the
 *    player looking back at him and the team (hook_freecam.h), the names traced every 2 s;
 *  - then the respawn loadout menu (CInGameWeaponSel, network only: CHUD::Tick runs it only for a
 *    dead network player) is opened and driven with a test pad (a copy of pad 0 with only the
 *    scripted button falling): DOWN, DOWN, Action (select), DOWN, Action, UP, Inventory (close).
 *    Its state, current weapon, SELECTED marks and loadout are traced.
 *  - -DSOCOM_HOOK_LENSCAM: the test camera also looks at the lens-flare light (when lensflare.rdr
 *    made the effect active) for 8 s after the menu closes. */
#include <map>
#include <string>
#include <vector>
#include <list>
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zGame/zgame.h"
#include "gamez/zInput/zinput.h"
#include "gamez/zWeapon/zweapon.h"
#include "Apps/FTS/state/state.h"
#include "Apps/FTS/hud/hud.h"
#include <string.h>
#include <stdio.h>
#include <math.h>
#define HOOK_FREECAM_WRAP
#include "hook_freecam.h"

#ifndef SOCOM_HOOK_NAMES_TIME
#define SOCOM_HOOK_NAMES_TIME 15.0f
#endif

namespace
{
bool g_mission_on;
bool g_cam_seen;
float g_quiet;          /* seconds since a briefing camera last played */
float g_t = -1.0f;      /* script time, from the end of the cameras */
float g_last_names = -10.0f;
int g_step;
int g_last_state = -1;
int g_last_item = -1;
bool g_menu_opened;
bool g_menu_done;

struct Step
{
    float at;
    int kind; /* 0 pad button, 1 Action, 2 Inventory */
    int button;
    const char *what;
};

const Step g_steps[] = {
    { 3.0f, 0, (int)PAD_BUTTON::PAD_DOWN, "DOWN" },
    { 5.0f, 0, (int)PAD_BUTTON::PAD_DOWN, "DOWN" },
    { 7.0f, 1, 0, "Action (select)" },
    { 9.0f, 0, (int)PAD_BUTTON::PAD_DOWN, "DOWN" },
    { 11.0f, 1, 0, "Action (select)" },
    { 13.0f, 0, (int)PAD_BUTTON::PAD_UP, "UP" },
    { 20.0f, 2, 0, "Inventory (close)" },
};

const char *weapon_name(int index)
{
    CZWeapon *w = CZWeapon::m_listWeapons.GetWeaponByIndex(index);
    return w != NULL && w->GetName() != NULL ? w->GetName() : "-";
}

/* the button a pad function is mapped to (the first that reads falling) */
int button_for(PadBtnFunc::_ func, const CPad &pad)
{
    for (int b = 0; b < (int)PAD_BUTTON::PAD_MAX_BUTTONS; b++)
    {
        CPad test = pad;

        for (int i = 0; i < (int)PAD_BUTTON::PAD_MAX_BUTTONS; i++)
            test.m_state[i] = KEY_UP;

        test.m_state[b] = KEY_FALLING;

        if (CCtrlrConfigs::GetButtonState(func, test) == KEY_FALLING)
            return b;
    }

    return -1;
}

void trace_names(CHUD *hud)
{
    char line[600];
    int n = 0;
    int on = 0;

    for (int i = 0; i < 15; i++)
    {
        C2DString &s = hud->m_teamMateNames.m_teamMateNames[i];

        if (!s.m_on)
            continue;

        on++;
        n += snprintf(line + n, sizeof(line) - n, " | %s at %d,%d trans %.0f", s.m_string != NULL ? s.m_string : "-",
            s.m_pos.x >> 4, s.m_pos.y >> 4, s.m_color.w);

        if (n >= (int)sizeof(line) - 1)
            break;
    }

    if (on == 0)
        line[0] = 0;

    SOCOM_PORT_TRACE("HOOK: hudmp t %.1f team-mate names on %d (box on %d)%s", g_t, on, (int)hud->m_teamMateNames.m_on, line);
}

void trace_menu(CHUD *hud, const char *why)
{
    CInGameWeaponSel &m = hud->m_ingameweaponsel;
    char loadout[200];
    int n = 0;

    for (int i = 0; i < 6; i++)
    {
        int id = (int)(unsigned char)m.m_selected_item_index[i];
        CZWeapon *w = id != 0xff ? CZWeapon::m_listWeapons.GetWeapon(m.m_selected_item_index[i]) : NULL;
        n += snprintf(loadout + n, sizeof(loadout) - n, "%s%s", i ? ", " : "", id == 0xff ? "-" : (w != NULL ? w->GetName() : "?"));
    }

    SOCOM_PORT_TRACE("HOOK: hudmp t %.1f menu %s: state %d item %d %s (slots %s / %s / %s, SELECTED %d %d %d) name '%s' on %d "
        "ammo '%s' mags '%s' bkrnd on %d arrows %d %d | loadout %s",
        g_t, why, m.m_openstate, m.m_current_item, weapon_name(m.m_current_item), weapon_name(m.m_selected[0]),
        weapon_name(m.m_selected[1]), weapon_name(m.m_selected[2]), m.m_icon_selected[0], m.m_icon_selected[1],
        m.m_icon_selected[2], m.m_weaponname.m_string != NULL ? m.m_weaponname.m_string : "-", (int)m.m_weaponname.m_on,
        m.m_ammocount.m_string != NULL && m.m_ammocount.m_on ? m.m_ammocount.m_string : "-",
        m.m_magcount.m_string != NULL && m.m_magcount.m_on ? m.m_magcount.m_string : "-", (int)m.m_weaponselbkrnd.m_on,
        (int)m.m_arrow[0].m_on, (int)m.m_arrow[1].m_on, loadout);
}

void look_at_team()
{
    CZSealBody *player = ftsGetPlayer();

    if (player == NULL)
        return;

    CPnt3D head;
    CPnt3D dir;
    player->GetHeadParams(&head, &dir);
    dir.y = 0.0f;
    float len = sqrtf(dir.x * dir.x + dir.z * dir.z);

    if (len < 0.001f)
        return;

    dir.x /= len;
    dir.z /= len;
    const CPnt3D *pos = player->GetPosW();
    CPnt3D eye(pos->x + dir.x * 7.0f, pos->y + 2.5f, pos->z + dir.z * 7.0f);
    CPnt3D target(pos->x - dir.x * 3.0f, pos->y + 1.0f, pos->z - dir.z * 3.0f);
    freecam_look(eye, target);
}
}

extern "C" void __real__ZN4CHUD4InitEPN3zdb6CWorldE(CHUD *hud, zdb::CWorld *world);

extern "C" void __wrap__ZN4CHUD4InitEPN3zdb6CWorldE(CHUD *hud, zdb::CWorld *world)
{
    __real__ZN4CHUD4InitEPN3zdb6CWorldE(hud, world);
    hud->m_teamMateNames.Init(hud->m_myfont);
    hud->m_teamMateNames.On();
    g_mission_on = true;
    g_cam_seen = false;
    g_quiet = 0.0f;
    g_t = -1.0f;
    g_step = 0;
    g_menu_opened = false;
    g_menu_done = false;
    SOCOM_PORT_TRACE("HOOK: hudmp CHUD::Init: team-mate names on (network-only element), lens flare active %d glare %d flare %d",
        (int)hud->m_LensFlareFade.m_Active, (int)hud->m_LensFlareFade.m_GlareActive, (int)hud->m_LensFlareFade.m_LensFlareActive);
}

extern "C" void __real__ZN4CHUD4TickEf(CHUD *hud, float dT);

extern "C" void __wrap__ZN4CHUD4TickEf(CHUD *hud, float dT)
{
    __real__ZN4CHUD4TickEf(hud, dT);

    if (!g_mission_on || hud != theHUD)
        return;

    /* the team-mate names, as CHUD::Tick does in a network game */
    hud->m_teamMateNames.xMargin = hud->m_letterbox.m_curpos;
    hud->m_teamMateNames.Tick(dT);

    bool playing = hud->m_missioncams.IsPlaying() != 0;

    if (playing)
    {
        g_cam_seen = true;
        g_quiet = 0.0f;
        return;
    }

    g_quiet += dT;

    if (g_t < 0.0f)
    {
        if (!(g_cam_seen ? g_quiet > 2.0f : g_quiet > 30.0f))
            return;

        g_t = 0.0f;
        SOCOM_PORT_TRACE("HOOK: hudmp script starts (cameras seen %d)", (int)g_cam_seen);
    }

    g_t += dT;

    if (g_t < SOCOM_HOOK_NAMES_TIME)
        look_at_team();
    else if (g_freecam.on && !g_menu_opened)
        freecam_off();

    if (g_t >= g_last_names + 2.0f)
    {
        g_last_names = g_t;
        trace_names(hud);
    }

    CInGameWeaponSel &menu = hud->m_ingameweaponsel;
    CZSealBody *player = ftsGetPlayer();
    u32 padid = player != NULL ? static_cast<CSealCtrl*>(player->m_control)->m_padid : 2;
    CPad *pad = padid < 2 ? CInput::m_pads[padid] : NULL;

    if (pad == NULL)
        return;

    float menu_t = g_t - SOCOM_HOOK_NAMES_TIME;

    if (!g_menu_opened && menu_t >= 0.0f)
    {
        g_menu_opened = true;
        SOCOM_PORT_TRACE("HOOK: hudmp t %.1f open the loadout menu (Action = button %d, Inventory = button %d, %d weapons listed)",
            g_t, button_for(PadBtnFunc::Action, *pad), button_for(PadBtnFunc::Inventory, *pad), (int)CZWeapon::m_listWeapons.size());
        menu.OnOpen();
        trace_menu(hud, "opened");
    }

    if (!g_menu_opened || g_menu_done)
    {
#ifdef SOCOM_HOOK_LENSCAM
        if (g_menu_done && hud->m_LensFlareFade.m_Active && menu_t < 40.0f)
        {
            const CPnt3D &light = hud->m_LensFlareFade.m_LightPos;
            const CPnt3D *pos = player->GetPosW();
            CPnt3D eye(pos->x, pos->y + 2.0f, pos->z);
            freecam_look(eye, light);
        }
        else if (g_freecam.on && g_menu_done)
        {
            freecam_off();
        }
#endif
        return;
    }

    CPad test = *pad;

    for (int i = 0; i < (int)PAD_BUTTON::PAD_MAX_BUTTONS; i++)
        test.m_state[i] = KEY_UP;

    if (g_step < (int)(sizeof(g_steps) / sizeof(g_steps[0])) && menu_t >= g_steps[g_step].at)
    {
        const Step &s = g_steps[g_step];
        int b = s.kind == 0 ? s.button : button_for(s.kind == 1 ? PadBtnFunc::Action : PadBtnFunc::Inventory, *pad);

        if (b >= 0)
            test.m_state[b] = KEY_FALLING;

        SOCOM_PORT_TRACE("HOOK: hudmp t %.1f menu press %s (button %d)", g_t, s.what, b);
        g_step++;
    }

    menu.HudTick(&test, dT);

    if (menu.m_openstate != g_last_state || menu.m_current_item != g_last_item)
    {
        trace_menu(hud, "tick");
        g_last_state = menu.m_openstate;
        g_last_item = menu.m_current_item;
    }

    if (menu.m_openstate == 0 && g_step > 0)
    {
        g_menu_done = true;
        SOCOM_PORT_TRACE("HOOK: hudmp t %.1f loadout menu closed, character weapons %d", g_t,
            player != NULL && player->GetCharacter() != NULL ? (int)player->GetCharacter()->m_weapons.size() : -1);
    }
}
