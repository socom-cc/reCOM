/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-mod-zui2, the zUI controls the demo's offline menus do not reach
 * by themselves. Wraps scePadRead and drives the menus from the open dialog's name
 * (CGameMenu::m_ReaderName), queueing menu-stack commands as the anims' UI commands do:
 *  - dlgIntroScreen: CROSS; dlgMenu: switch to the first test dialog;
 *  - list box (SOCOM_HOOK_LIST, default on): dlgDebriefing then dlgPBMenu, each: the SavedGames UI
 *    variable is set to SOCOM_HOOK_ROWS rows (number, title, date, mission; the shape of the game's
 *    ListSavedGames, which the port lists only when a memory card answers), the SavedGames list
 *    shown (CNode::SetActive), enabled and made active (menu commands 7 and 6, as the debrief's
 *    MemCheckSave), then DOWN x (rows + 1), UP x 4, TRIANGLE (CancelLoadGame hides it); dlgPBMenu's
 *    no-memory-card pop-up is closed with CROSS first; then
 *    back to dlgMenu, then dlgNotEnoughSpace (WRAPPEDTEXT) for 150 reads and back.
 *  - SOCOM_HOOK_SKB (socom-port-mod-skb; instead of the lists): the soft keyboard, raised by the
 *    game's own anims: dlgMenu -> dlgNetPlayerName (an online screen whose player-name button runs
 *    SetSkbPurpose + GetTextInput on the MPPLAYERNAME keyboard; nothing online runs before its
 *    connect button), CROSS on the name button; on the keyboard R1 (Caps Lock), RIGHT, CROSS ("S"),
 *    R1, LEFT, CROSS ("a"), RIGHT x2, CROSS ("d"), SQUARE (backspace), CROSS ("d"), CIRCLE (accept:
 *    PLAYERNAMEVAR = "Sad", ON_SKB_APPLY); later CROSS on the active button (the keyboard again),
 *    CROSS ("a"), TRIANGLE (cancel: the variable keeps its text); TRIANGLE back to dlgMenu.
 *    Traced every 10 reads on that screen: the keyboard node, skb_done, the text on the keyboard,
 *    PLAYERNAMEVAR / PLAYERPASSWORD.
 * Each step is traced (HOOK:) with the heap. */
#include <string>
#define protected public
#define private public
#include "gamez/zGame/zgame.h"
#include "gamez/zUI/zui.h"
#include "gamez/zAnim/zanim.h"
#include "gamez/zReader/zrdr_local.h"
#include "gamez/zValve/zvalve.h"
#include <string.h>
#include <stdio.h>
#include <malloc.h>
#include <unistd.h>
#include "hook_clock.h"

#ifndef SOCOM_HOOK_ROWS
#define SOCOM_HOOK_ROWS 12
#endif

CGameMenu *UiGetCurMenu();
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);

namespace
{
enum { B_UP = 0x1000, B_DOWN = 0x4000, B_CROSS = 0x0040, B_TRIANGLE = 0x0010, B_RIGHT = 0x2000, B_LEFT = 0x8000,
    B_R1 = 0x0008, B_CIRCLE = 0x0020, B_SQUARE = 0x0080 };

struct Press
{
    unsigned int at;
    unsigned short bits;
};

Press g_queue[256];
int g_nqueue;
unsigned int g_reads;
std::string g_dialog;
unsigned int g_since;
int g_step;

void queue(unsigned int at, unsigned short bits)
{
    if (g_nqueue < 256)
    {
        g_queue[g_nqueue].at = at;
        g_queue[g_nqueue].bits = bits;
        g_nqueue++;
    }
}

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

void fill_saved_games(const char *title)
{
    CRdrEditor rdr;
    char text[64];
    rdr.push(NULL);

    for (int i = 0; i < SOCOM_HOOK_ROWS; i++)
    {
        rdr.push(NULL);
        sprintf(text, "%d", i);
        rdr.addstringnode(text);
        sprintf(text, "%s %d", title, i);
        rdr.addstringnode(text);
        sprintf(text, "11/%02d/2026", i + 1);
        rdr.addstringnode(text);
        rdr.addstringnode("m8");
        rdr.pop();
    }

    rdr.pop();
    theUIVarManager.Add("SavedGames", NULL, (UIVAR_LONGEVITY)1)->Set(&rdr);
}

void show_list(CGameMenu *menu)
{
    zdb::CNode *node = menu->m_nodeTop.FindChild("SavedGames", true);
    SOCOM_PORT_TRACE("HOOK: read %u SavedGames node %p", g_reads, node);

    if (node != NULL)
        node->SetActive(true);

    menu_command(6, "SavedGames");
    menu_command(7, "SavedGames");
}

const unsigned int LIST_START = 30;
const unsigned int LIST_END = LIST_START + 20 + 10 * (SOCOM_HOOK_ROWS + 1) + 20 + 10 * 4 + 20 + 30;

void list_test(CGameMenu *menu, const char *title)
{
    fill_saved_games(title);
    heap("list filled");
    show_list(menu);

    for (int i = 0; i < SOCOM_HOOK_ROWS + 1; i++)
        queue(g_reads + 20 + 10 * i, B_DOWN);

    unsigned int up = g_reads + 20 + 10 * (SOCOM_HOOK_ROWS + 1) + 20;

    for (int i = 0; i < 4; i++)
        queue(up + 10 * i, B_UP);

    queue(up + 10 * 4 + 20, B_TRIANGLE);
}

/* the list box's state: rows, selection, scroll (traced every 10 reads while a list test runs) */
void trace_list(CGameMenu *menu)
{
    zdb::CNode *node = menu->m_nodeTop.FindChild("SavedGames", true);
    zdb::CVisual *visual = node != NULL ? node->GetFirstVisual() : NULL;
    C2DVisual *visual2d = visual != NULL ? visual->Get2DVisual() : NULL;
    CUIListBox *list = visual2d != NULL ? dynamic_cast<CUIListBox *>(visual2d->m_2d) : NULL;

    if (list == NULL)
    {
        SOCOM_PORT_TRACE("HOOK: read %u no list box", g_reads);
        return;
    }

    SOCOM_PORT_TRACE("HOOK: read %u list: %u rows, selection %d, offset %d, top row %d, scroll %.1f, input %d, node %d",
        g_reads, (unsigned)list->m_items.size(), list->m_selection, list->m_selOffset, list->m_topRow, list->m_scroll,
        (int)list->CanHandleInput(), (int)node->m_active);
    CUIVariable *var = theUIVarManager.Find("SavedGames");
    CUIVariable *mine = list->UIVarMixin::m_uivar;
    SOCOM_PORT_TRACE("HOOK: list var %p (type %d, %u attached), found %p (type %d, %u attached)", mine,
        mine ? (int)mine->type : -1, mine ? (unsigned)mine->m_attached_items.size() : 0, var, var ? (int)var->type : -1,
        var ? (unsigned)var->m_attached_items.size() : 0);
}
#ifdef SOCOM_HOOK_SKB
const char *var_text(const char *name)
{
    CUIVariable *var = theUIVarManager.Find(name);

    if (var == NULL)
        return "(none)";

    return var->type == ZRDR_STRING && var->string != NULL ? var->string : "(not a string)";
}

/* the keyboard's node (named after it, under the foreplane) and the text it shows (its first
 * CRenderableString child is the typed text, the second the purpose) */
void trace_skb(CGameMenu *menu)
{
    zdb::CNode *node = menu->m_nodeTop.FindChild("MPPLAYERNAME", true);
    const char *texts[2] = { "-", "-" };
    int n = 0;

    for (unsigned i = 0; node != NULL && i < node->m_child.size() && n < 2; i++)
    {
        zdb::CVisual *visual = node->m_child[i]->GetFirstVisual();
        C2DVisual *visual2d = visual != NULL ? visual->Get2DVisual() : NULL;
        CRenderableString *str = visual2d != NULL ? dynamic_cast<CRenderableString *>(visual2d->m_2d) : NULL;

        if (str != NULL)
        {
            texts[n] = str->GetString() != NULL ? str->GetString() : "(null)";
            n++;
        }
    }

    CValve *done = CValve::GetByName("skb_done");
    SOCOM_PORT_TRACE("HOOK: read %u skb node %p active %d children %u, skb_done %d, text \"%s\" purpose \"%s\", "
        "PLAYERNAMEVAR \"%s\" PLAYERPASSWORD \"%s\"", g_reads, node, node != NULL ? (int)node->m_active : -1,
        node != NULL ? (unsigned)node->m_child.size() : 0, done != NULL ? (int)done->m_value : -1, texts[0], texts[1],
        var_text("PLAYERNAMEVAR"), var_text("PLAYERPASSWORD"));
}

/* dlgNetPlayerName: K = the name button's CROSS; the keyboard opens with the highlight on A */
void skb_test()
{
    unsigned int k = g_reads;
    queue(k, B_CROSS);
    queue(k + 40, B_R1);
    queue(k + 50, B_RIGHT);
    queue(k + 60, B_CROSS);   /* S (Caps Lock) */
    queue(k + 70, B_R1);
    queue(k + 80, B_LEFT);
    queue(k + 90, B_CROSS);   /* a */
    queue(k + 100, B_RIGHT);
    queue(k + 110, B_RIGHT);
    queue(k + 120, B_CROSS);  /* d */
    queue(k + 130, B_SQUARE); /* backspace */
    queue(k + 140, B_CROSS);  /* d */
    queue(k + 260, B_CIRCLE); /* accept */
    queue(k + 360, B_CROSS);  /* the active button: the keyboard again */
    queue(k + 400, B_CROSS);  /* a */
    queue(k + 440, B_TRIANGLE); /* cancel */
    queue(k + 540, B_TRIANGLE); /* back */
}
#endif

/* step 0 dlgMenu -> 1 dlgDebriefing list -> 2 -> 3 dlgPBMenu list -> 4 -> 5 dlgMenu -> 6 dlgNotEnoughSpace
 * (wrapped text) -> 7 dlgMenu -> 8 done; SOCOM_HOOK_SKB: 0 dlgMenu -> 20 dlgNetPlayerName -> 21 keyboard
 * test -> 22 dlgMenu (done) */
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
    }

    unsigned int t = g_reads - g_since;

    if ((g_step == 2 || g_step == 4) && t % 10 == 5)
        trace_list(menu);

#ifdef SOCOM_HOOK_SKB
    if (g_step == 21 && t % 10 == 5)
        trace_skb(menu);

    if (g_step == 0 && name == "dlgMenu.rdr" && t == 60)
    {
        menu_command(5, "dlgNetPlayerName.rdr");
        g_step = 20;
    }
    else if (g_step == 20 && name == "dlgNetPlayerName.rdr" && t == 60)
    {
        heap("before the keyboard");
        skb_test();
        g_step = 21;
    }
    else if (g_step == 21 && name == "dlgNetPlayerName.rdr" && (t == 400 || t == 600))
    {
        heap("keyboard");
    }
    else if (g_step == 21 && name == "dlgMenu.rdr" && t == 60)
    {
        SOCOM_PORT_TRACE("HOOK: read %u keyboard done", g_reads);
        heap("keyboard done");
        g_step = 22;
    }

    return;
#endif

    if (g_step == 0 && name == "dlgMenu.rdr" && t == 60)
    {
        menu_command(5, "dlgDebriefing.rdr");
        g_step = 1;
    }
    else if (g_step == 1 && name == "dlgDebriefing.rdr" && t == LIST_START)
    {
        list_test(menu, "Debrief game");
        g_step = 2;
    }
    else if (g_step == 2 && name == "dlgDebriefing.rdr" && t == LIST_END)
    {
        heap("list closed");
        menu_command(5, "dlgPBMenu.rdr");
        g_step = 3;
    }
    else if (g_step == 3 && name == "dlgPBMenu.rdr" && t == 15)
    {
        queue(g_reads, B_CROSS); /* the no-memory-card pop-up the menu opens */
    }
    else if (g_step == 3 && name == "dlgPBMenu.rdr" && t == LIST_START + 15)
    {
        list_test(menu, "PB game");
        g_step = 4;
    }
    else if (g_step == 4 && name == "dlgPBMenu.rdr" && t == LIST_END + 15)
    {
        heap("list closed");
        menu_command(5, "dlgMenu.rdr");
        g_step = 5;
    }
    else if ((g_step == 4 || g_step == 5) && name == "dlgMenu.rdr" && t == 60) /* 4: the menu went to the attract screen */
    {
        menu_command(5, "dlgNotEnoughSpace.rdr"); /* WRAPPEDTEXT (a memory-card screen) */
        g_step = 6;
    }
    else if (g_step == 6 && name == "dlgNotEnoughSpace.rdr" && t == 150)
    {
        menu_command(5, "dlgMenu.rdr");
        g_step = 7;
    }
    else if (g_step == 7 && name == "dlgMenu.rdr" && t == 60)
    {
        SOCOM_PORT_TRACE("HOOK: read %u lists done", g_reads);
        heap("lists done");
        g_step = 8;
    }
}
unsigned short pressed_now()
{
    unsigned short bits = 0;

    for (int i = 0; i < g_nqueue; i++)
    {
        if (g_reads >= g_queue[i].at && g_reads < g_queue[i].at + 3)
        {
            bits |= g_queue[i].bits;

            if (g_reads == g_queue[i].at)
                SOCOM_PORT_TRACE("HOOK: read %u press %04x (dialog %s)", g_reads, g_queue[i].bits, g_dialog.c_str());
        }
    }

    return bits;
}
}

extern "C" int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
    int r = __real_scePadRead(port, slot, rdata);

    if (port == 0)
    {
        static unsigned int hook_clock1;
        for (unsigned int hook_n = hook_step(&hook_clock1); hook_n > 0; hook_n--)
        {
            g_reads++;
            watch();
            unsigned short bits = pressed_now();

            if (bits != 0)
            {
                unsigned short held = (unsigned short)(~((rdata[2] << 8) | rdata[3]));
                held |= bits;
                rdata[2] = (unsigned char)~(held >> 8);
                rdata[3] = (unsigned char)~held;
            }
        }
    }

    return r;
}
