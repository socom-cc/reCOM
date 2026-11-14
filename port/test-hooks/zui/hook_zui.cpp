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
 *  - SOCOM_HOOK_SKB: after the lists, the soft keyboard is raised on dlgMenu (UiGetTextFromUser's
 *    path is the anims'; here the hook calls the keyboard entry the UI command uses).
 * Each step is traced (HOOK:) with the heap. */
#include <string>
#define protected public
#define private public
#include "gamez/zGame/zgame.h"
#include "gamez/zUI/zui.h"
#include "gamez/zAnim/zanim.h"
#include "gamez/zReader/zrdr_local.h"
#include <string.h>
#include <stdio.h>
#include <malloc.h>
#include <unistd.h>

#ifndef SOCOM_HOOK_ROWS
#define SOCOM_HOOK_ROWS 12
#endif

CGameMenu *UiGetCurMenu();
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);

namespace
{
enum { B_UP = 0x1000, B_DOWN = 0x4000, B_CROSS = 0x0040, B_TRIANGLE = 0x0010 };

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
/* step 0 dlgMenu -> 1 dlgDebriefing list -> 2 -> 3 dlgPBMenu list -> 4 -> 5 dlgMenu -> 6 dlgNotEnoughSpace
 * (wrapped text) -> 7 dlgMenu -> 8 done */
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

    return r;
}
