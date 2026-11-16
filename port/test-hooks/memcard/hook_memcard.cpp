/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-memcard, the game's own memory-card paths. The demo's
 * reachable screens never start a card animation (its intro screen and options leave skip them),
 * so the hook starts the menu scripts' own animations from dlgOptions_Menu, which loads them
 * (uianim.rdr -> UIIntro.rdr: intro_onstart, the format questions and do_formatting;
 * UIMemCardAnim.rdr: load_initial_config, save_and_leave, Ensure_MC_Dirs), and answers their
 * pop-ups with the pad from what the game shows: the open dialog (CGameMenu::m_ReaderName) and
 * the waiting YESNO pop-up (CMenuStack::m_popup, its valve at 0).
 *  - SOCOM_HOOK_MC_PLAN 0 (default, the probe): intro_onstart, load_initial_config, the audio
 *    screen (music volume up), save_and_leave. 1 (format and save): intro_onstart, audio,
 *    save_and_leave, load_initial_config. 2 (load): load_initial_config, then the audio screen, staying there.
 *  - pop-ups: intro_onstart's format questions (valve AreYouSure) get SOCOM_HOOK_MC_FORMAT_ANSWER
 *    (2: "Yes" in both: RIGHT, CROSS); every other AreYouSure gets YES (1: CROSS: "save");
 *    AcceptNoFormat / SitHere ("press X to continue") CROSS.
 *  - dialogs: dlgMenu DOWN + CROSS (Options) while the plan has steps; intro / cinematic /
 *    attract screens CROSS; dlgOptions_Menu: the next step (an anim, or CROSS into Audio);
 *    dlgOptions_Audio RIGHT x SOCOM_HOOK_MC_RIGHTS (MUSIC_VOLUME), then TRIANGLE back.
 *  - -DSOCOM_HOOK_MC_FORMAT=1: socom_port_memcard_format = 1 (port/compat/libmc.c: the game's
 *    FormatMemCard may format the card, only when the layer's last info reply said "unformatted").
 *    Only for the dedicated test card. Default 0: the format is refused.
 *  - -DSOCOM_HOOK_MC_ICONS: after the first SaveConfig, CMemCard::CreateIconFiles once more (the
 *    game writes its icons only when it makes its directory).
 *  - -DSOCOM_HOOK_MC_FIOTEST: at pad read 30, the disc read CreateIconFiles makes (sceOpen /
 *    sceRead of RUN\ICONS\LIST.ICO) against ps2sdk's fio, and fio opens of other disc files.
 *  - -DSOCOM_HOOK_MC_LAYER=0 / 1: socom_port_memcard before the game's first card call (default 1).
 * Traced (HOOK: MC ...): every CMemCard call the menus make with its answer, the persistent UI
 * variables (names, values) at each SaveConfig / LoadConfig, MUSIC_VOLUME, the card's directory
 * listing (sceMcGetDir, names and sizes) after each save and load, the layer's poll timings. */
#include <string>
#include <map>
#include <vector>
#include <list>
#define protected public
#define private public
#include "gamez/zUtil/zutil.h"
#include "gamez/zSave/zsave.h"
#include "gamez/zUI/zui.h"
#include "gamez/zAnim/zanim.h"
#include "gamez/zValve/zvalve.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zGame/zgame.h"
#include "Apps/FTS/state/state.h"
#include <string.h>
#include <stdio.h>
#include <libmc.h>
#include <sifdev.h>
#include "hook_clock.h"

#ifndef SOCOM_HOOK_MC_FORMAT
#define SOCOM_HOOK_MC_FORMAT 0
#endif
#ifndef SOCOM_HOOK_MC_FORMAT_ANSWER
#define SOCOM_HOOK_MC_FORMAT_ANSWER 2
#endif
#ifndef SOCOM_HOOK_MC_PLAN
#define SOCOM_HOOK_MC_PLAN 0
#endif
#ifndef SOCOM_HOOK_MC_RIGHTS
#define SOCOM_HOOK_MC_RIGHTS 3
#endif
#ifndef SOCOM_HOOK_MC_LAYER
#define SOCOM_HOOK_MC_LAYER 1
#endif

void socom_port_trace(const char *fmt, ...);
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);
extern "C" int socom_port_memcard;
extern "C" int socom_port_memcard_format;
extern "C" void socom_port_memcard_poll_stats(int port, unsigned int *polls, unsigned int *total_us, unsigned int *max_us);
extern COurGame theGame;
extern CMenuStack g_MenuStack;
CZAnimSet *GetLocalAnims(); /* zui.cpp 0x384ee0: the open menu's own anim set */

namespace
{
enum { B_UP = 0x1000, B_RIGHT = 0x2000, B_DOWN = 0x4000, B_LEFT = 0x8000, B_TRIANGLE = 0x0010, B_CROSS = 0x0040 };

/* the layer's switches before any game code runs (global constructors come before main) */
struct Switches
{
	Switches()
	{
		socom_port_memcard = SOCOM_HOOK_MC_LAYER;
		socom_port_memcard_format = SOCOM_HOOK_MC_FORMAT;
	}
} switches;

unsigned int reads;
unsigned short press_bits;
unsigned int press_at, press_until;
unsigned int next_action;
char dialog[64];
unsigned int dialog_since;
const void *top_seen;

const char *dialog_name()
{
	if (theGame.m_menuState.m_menu == NULL)
		return "";
	return theGame.m_menuState.m_menu->m_ReaderName.c_str();
}

void press(unsigned short bits, unsigned int delay, const char *why)
{
	press_bits = bits;
	press_at = reads + delay;
	press_until = press_at + 3;
	next_action = press_until + 20;
	SOCOM_PORT_TRACE("HOOK: MC read %u press %04x in %u (%s; dialog %s)", reads, bits, delay, why, dialog);
}

void trace_var(const char *where, const char *name)
{
	CUIVariable *var = theUIVarManager.Find(name);
	if (var == NULL)
		SOCOM_PORT_TRACE("HOOK: MC %s: %s not defined", where, name);
	else if (var->type == ZRDR_REAL)
		SOCOM_PORT_TRACE("HOOK: MC %s: %s = %.3f (longevity %d)", where, name, var->real, (int)var->m_longevity);
	else if (var->type == ZRDR_INTEGER)
		SOCOM_PORT_TRACE("HOOK: MC %s: %s = %d (longevity %d)", where, name, var->integer, (int)var->m_longevity);
	else if (var->type == ZRDR_STRING)
		SOCOM_PORT_TRACE("HOOK: MC %s: %s = '%s' (longevity %d)", where, name, var->string != NULL ? var->string : "", (int)var->m_longevity);
	else
		SOCOM_PORT_TRACE("HOOK: MC %s: %s type %d (longevity %d)", where, name, (int)var->type, (int)var->m_longevity);
}

void trace_persistent(const char *where)
{
	char line[480];
	int n = 0, count = 0;
	line[0] = 0;
	for (CUIVarManager::iterator it = theUIVarManager.begin(); it != theUIVarManager.end(); ++it) {
		if (it->m_longevity != UIVL_PERSISTENT || it->m_varname == NULL)
			continue;
		count++;
		if (it->type == ZRDR_REAL)
			n += snprintf(line + n, sizeof(line) - n, " %s=%.3f", it->m_varname, it->real);
		else if (it->type == ZRDR_INTEGER)
			n += snprintf(line + n, sizeof(line) - n, " %s=%d", it->m_varname, it->integer);
		else if (it->type == ZRDR_STRING)
			n += snprintf(line + n, sizeof(line) - n, " %s='%s'", it->m_varname, it->string != NULL ? it->string : "");
		else
			n += snprintf(line + n, sizeof(line) - n, " %s(type %d)", it->m_varname, (int)it->type);
		if (n >= (int)sizeof(line) - 1) {
			SOCOM_PORT_TRACE("HOOK: MC %s: persistent UI variables:%s", where, line);
			n = 0;
			line[0] = 0;
		}
	}
	SOCOM_PORT_TRACE("HOOK: MC %s: persistent UI variables (%d):%s", where, count, line);
}

void list_dir(const char *where, const char *pattern)
{
	static sceMcTblGetDir table[24] __attribute__((aligned(64)));
	int cmd = 0, result = -999;
	int port = theMemCard.m_card_port, slot = theMemCard.m_card_slot;
	if (sceMcGetDir(port, slot, pattern, 0, 24, table) < 0) {
		SOCOM_PORT_TRACE("HOOK: MC %s: GetDir %s not registered", where, pattern);
		return;
	}
	sceMcSync(0, &cmd, &result);
	SOCOM_PORT_TRACE("HOOK: MC %s: GetDir %s -> %d entries", where, pattern, result);
	for (int i = 0; i < result && i < 24; i++)
		SOCOM_PORT_TRACE("HOOK: MC %s:   %-32s %7u bytes attr 0x%04x", where, (const char *)table[i].EntryName,
			table[i].FileSizeByte, table[i].AttrFile);
	int type = -1, free = -1, format = -1;
	if (sceMcGetInfo(port, slot, &type, &free, &format) == 0) {
		sceMcSync(0, &cmd, &result);
		SOCOM_PORT_TRACE("HOOK: MC %s: card port %d: type %d free %d KB format %d (result %d)", where, port, type, free, format, result);
	}
}

void poll_stats(const char *where)
{
	for (int p = 0; p < 2; p++) {
		unsigned int polls, total, max;
		socom_port_memcard_poll_stats(p, &polls, &total, &max);
		if (polls != 0)
			SOCOM_PORT_TRACE("HOOK: MC %s: port %d: %u info polls, %u us in all, %u us mean, %u us longest", where, p, polls, total,
				total / polls, max);
	}
}

bool in_format_step();

/* the waiting YESNO pop-up: answer it */
bool popup_waiting()
{
	static bool waiting;
	static unsigned int since;
	CPopUpDialog *popup = g_MenuStack.m_popup;
	if (popup == NULL || popup->m_valve == NULL || (u16)popup->m_valve->m_value != 0) {
		waiting = false;
		return false;
	}
	if (!waiting) {
		/* a new wait: give the script 30 reads to show the pop-up */
		waiting = true;
		since = reads;
		SOCOM_PORT_TRACE("HOOK: MC read %u pop-up waits on valve %s (dialog %s)", reads,
			popup->m_valve->m_name != NULL ? popup->m_valve->m_name : "?", dialog);
	}
	if (reads < since + 30 || reads < next_action)
		return true;
	const char *valve = popup->m_valve->m_name != NULL ? popup->m_valve->m_name : "?";
	int want = 1;
	if (strcmp(valve, "AreYouSure") == 0 && in_format_step())
		want = SOCOM_HOOK_MC_FORMAT_ANSWER;
	if (popup->m_selection != want) {
		char why[96];
		snprintf(why, sizeof(why), "pop-up valve %s: selection %d, wanted %d", valve, popup->m_selection, want);
		press(B_RIGHT, 1, why);
	} else {
		char why[96];
		snprintf(why, sizeof(why), "pop-up valve %s: choose %d", valve, want);
		press(B_CROSS, 1, why);
	}
	return true;
}

/* the plan: the card animations of the demo's own menu scripts, started one after the other
 * from dlgOptions_Menu (it loads uianim.rdr with UIIntro.rdr, and UIMemCardAnim.rdr) because the
 * demo's reachable screens never start them (docs/port/notes/memcard.md) */
const char *const plan_format[] = { "intro_onstart", "AUDIO", "save_and_leave", "load_initial_config", NULL };
const char *const plan_load[] = { "load_initial_config", "AUDIOSTAY", NULL };
const char *const plan_probe[] = { "intro_onstart", "load_initial_config", "AUDIO", "save_and_leave", NULL };
#if SOCOM_HOOK_MC_PLAN == 1
const char *const *plan = plan_format;
#elif SOCOM_HOOK_MC_PLAN == 2
const char *const *plan = plan_load;
#else
const char *const *plan = plan_probe;
#endif
int step;              /* the plan entry being worked on */
bool step_started;     /* its anim was activated / the audio screen entered */
unsigned int step_at;  /* read it started */
bool left_options;     /* the dialog left dlgOptions_Menu since */
int audio_step;

const char *current()
{
	return plan[step];
}

bool in_format_step()
{
	return current() != NULL && strcmp(current(), "intro_onstart") == 0;
}

void next_step(const char *why)
{
	SOCOM_PORT_TRACE("HOOK: MC read %u plan step %d (%s) done: %s", reads, step, current() != NULL ? current() : "-", why);
	step++;
	step_started = false;
	left_options = false;
	audio_step = 0;
	if (current() == NULL) {
		SOCOM_PORT_TRACE("HOOK: MC read %u plan finished", reads);
		poll_stats("plan finished");
	}
}

bool activate(const char *name)
{
	CZAnimSet *local = GetLocalAnims();
	CZAnim *anim = local != NULL ? local->Anim(name) : NULL;
	if (anim == NULL)
		anim = ZAnim.GetAnim(name, NULL);
	SOCOM_PORT_TRACE("HOOK: MC read %u activate the menu script's %s -> %p", reads, name, (void *)anim);
	if (anim == NULL)
		return false;
	anim->Activate(NULL);
	return true;
}

void drive()
{
	const char *name = dialog_name();
	if (strcmp(name, dialog) != 0) {
		if (strcmp(dialog, "dlgOptions_Menu.rdr") == 0)
			left_options = true;
		snprintf(dialog, sizeof(dialog), "%s", name);
		dialog_since = reads;
		SOCOM_PORT_TRACE("HOOK: MC read %u dialog %s", reads, dialog);
		if (strcmp(dialog, "dlgOptions_Audio.rdr") == 0)
			trace_var("audio screen", "MUSIC_VOLUME");
	}

	const void *top = NULL;
	for (unsigned int i = 0; i < 16; i++)
		if (theGame.m_Stack[i] != NULL)
			top = theGame.m_Stack[i];
	if (top != top_seen) {
		top_seen = top;
		SOCOM_PORT_TRACE("HOOK: MC read %u state %s", reads, top == &theGame.m_cinematicSubState ? "cinematic" :
			top == &theGame.m_menuState ? "menu" : "other");
		if (top == &theGame.m_cinematicSubState)
			press(B_CROSS, 40, "cinematic");
	}

	if (reads < next_action || press_bits != 0)
		return;
	if (popup_waiting())
		return;
	if (top != &theGame.m_menuState)
		return;

	static unsigned int idle_next;
	unsigned int on = reads - dialog_since;
	const char *what = current();
	bool done = what == NULL;
	if (strcmp(dialog, "dlgMenu.rdr") == 0) {
		static unsigned int menu_seen_at = ~0u;
		static int menu_step;
		if (menu_seen_at != dialog_since) {
			menu_seen_at = dialog_since;
			menu_step = 0;
		}
		if (!done && menu_step == 0 && on >= 60) {
			menu_step = 1;
			press(B_DOWN, 1, "main menu: to Options");
		} else if (!done && menu_step == 1) {
			menu_step = 2;
			press(B_CROSS, 1, "main menu: Options");
		}
	} else if (strstr(dialog, "Cinematic") != NULL || strcmp(dialog, "dlgIntroScreen.rdr") == 0 || strcmp(dialog, "dlgHype.rdr") == 0) {
		if (on >= 60 && reads >= idle_next) {
			idle_next = reads + 150;
			press(B_CROSS, 1, "intro / cinematic / attract: CROSS");
		}
	} else if (strcmp(dialog, "dlgOptions_Menu.rdr") == 0 && !done && on >= 90) {
		if (strncmp(what, "AUDIO", 5) == 0) {
			if (!step_started) {
				step_started = true;
				step_at = reads;
				press(B_CROSS, 1, "options: Audio");
			} else {
				next_step("back from the audio screen");
			}
		} else if (!step_started) {
			step_started = true;
			step_at = reads;
			left_options = false;
			if (!activate(what))
				next_step("no such anim");
		} else if (left_options || reads >= step_at + 900) {
			next_step(left_options ? "the script left the options screen" : "the script ran 900 reads");
		}
	} else if (strcmp(dialog, "dlgOptions_Audio.rdr") == 0 && !done && strncmp(what, "AUDIO", 5) == 0) {
		if (audio_step < SOCOM_HOOK_MC_RIGHTS && on >= 120) {
			audio_step++;
			press(B_RIGHT, 1, "audio: music volume up");
		} else if (audio_step == SOCOM_HOOK_MC_RIGHTS && on >= 120 + 30 * SOCOM_HOOK_MC_RIGHTS + 60) {
			audio_step++;
			trace_var("audio screen after the presses", "MUSIC_VOLUME");
			poll_stats("audio screen");
			if (strcmp(what, "AUDIO") == 0)
				press(B_TRIANGLE, 1, "audio: back");
			else
				next_step("staying on the audio screen");
		}
	}
}
}

#ifdef SOCOM_HOOK_MC_FIOTEST
#define NEWLIB_PORT_AWARE /* the test calls fio directly, as port/compat/sce_iop.c does */
#include <fileio.h>
namespace
{
/* the disc file reads CreateIconFiles makes (sceOpen / sceRead), against ps2sdk's fio directly */
void fio_test()
{
	char path[80];
	static unsigned char buf[1024] __attribute__((aligned(64)));
	CFileIO::PS2FileName("RUN\\ICONS\\LIST.ICO", path, false);
	int fd = sceOpen(path, 1);
	int end = fd >= 0 ? sceLseek(fd, 0, 2) : -1;
	int start = fd >= 0 ? sceLseek(fd, 0, 0) : -1;
	int got = fd >= 0 ? sceRead(fd, buf, 1024) : -1;
	SOCOM_PORT_TRACE("HOOK: MC fiotest sceOpen %s -> %d, size %d, rewind %d, read %d (%02x %02x %02x %02x)", path, fd, end, start, got,
		buf[0], buf[1], buf[2], buf[3]);
	if (fd >= 0)
		sceClose(fd);
	memset(buf, 0, 4);
	fd = fioOpen(path, O_RDONLY);
	end = fd >= 0 ? fioLseek(fd, 0, 2) : -1;
	start = fd >= 0 ? fioLseek(fd, 0, 0) : -1;
	got = fd >= 0 ? fioRead(fd, buf, 1024) : -1;
	SOCOM_PORT_TRACE("HOOK: MC fiotest fioOpen -> %d, size %d, rewind %d, read %d (%02x %02x %02x %02x)", fd, end, start, got,
		buf[0], buf[1], buf[2], buf[3]);
	if (fd >= 0)
		fioClose(fd);
	SOCOM_PORT_TRACE("HOOK: MC fiotest path bytes: %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x", path[6], path[7], path[8],
		path[9], path[10], path[11], path[12], path[13], path[14], path[15]);
	static const char *const others[] = { "cdrom0:\\SYSTEM.CNF;1", "cdrom0:\\RUN\\IRX\\MCSERV.IRX;1", "cdrom0:\\RUN\\ICONS\\LIST.ICO;1",
		"cdrom0:\\run\\icons\\list.ico;1", "cdrom:\\RUN\\ICONS\\LIST.ICO;1" };
	for (unsigned i = 0; i < sizeof(others) / sizeof(others[0]); i++) {
		fd = fioOpen(others[i], O_RDONLY);
		end = fd >= 0 ? fioLseek(fd, 0, 2) : -1;
		fioLseek(fd, 0, 0);
		got = fd >= 0 ? fioRead(fd, buf, 16) : -1;
		SOCOM_PORT_TRACE("HOOK: MC fiotest %u: fioOpen -> %d, size %d, read %d", i, fd, end, got);
		if (fd >= 0)
			fioClose(fd);
	}
}
}
#endif

extern "C" int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
	int r = __real_scePadRead(port, slot, rdata);
	if (port != 0)
		return r;
	/* reads counts hook_clock.h ticks (1/30 s, the pad-read rate at 60 fps the waits were tuned
	 * at): the script runs once per tick, whatever the frame rate */
	static unsigned int clock;
	for (unsigned int n = hook_step(&clock); n > 0; n--) {
		reads++;
#ifdef SOCOM_HOOK_MC_FIOTEST
		if (reads == 30)
			fio_test();
#endif
		if (press_bits != 0 && reads >= press_until)
			press_bits = 0;
		drive();
		if (press_bits != 0 && reads >= press_at && reads < press_until) {
			unsigned short held = (unsigned short)(~((rdata[2] << 8) | rdata[3]));
			held |= press_bits;
			rdata[2] = (unsigned char)~(held >> 8);
			rdata[3] = (unsigned char)~held;
		}
	}
	return r;
}

/* the CMemCard calls the menu commands make (zanim_menu.cpp), traced with their answers */
extern "C" void __real__ZN8CMemCard4InitEv(CMemCard *self);
extern "C" void __wrap__ZN8CMemCard4InitEv(CMemCard *self)
{
	int before = CMemCard::m_initcount;
	__real__ZN8CMemCard4InitEv(self);
	SOCOM_PORT_TRACE("HOOK: MC read %u Init (count %d -> %d)", reads, before, CMemCard::m_initcount);
}

extern "C" bool __real__ZN8CMemCard10IsInsertedEv(CMemCard *self);
extern "C" bool __wrap__ZN8CMemCard10IsInsertedEv(CMemCard *self)
{
	bool r = __real__ZN8CMemCard10IsInsertedEv(self);
	SOCOM_PORT_TRACE("HOOK: MC read %u IsInserted (port %d slot %d) -> %d", reads, self->m_card_port, self->m_card_slot, r);
	return r;
}

extern "C" bool __real__ZN8CMemCard11IsFormattedEv(CMemCard *self);
extern "C" bool __wrap__ZN8CMemCard11IsFormattedEv(CMemCard *self)
{
	bool r = __real__ZN8CMemCard11IsFormattedEv(self);
	SOCOM_PORT_TRACE("HOOK: MC read %u IsFormatted -> %d", reads, r);
	return r;
}

extern "C" bool __real__ZN8CMemCard6FormatEv(CMemCard *self);
extern "C" bool __wrap__ZN8CMemCard6FormatEv(CMemCard *self)
{
	SOCOM_PORT_TRACE("HOOK: MC read %u Format (the game's FormatMemCard)", reads);
	bool r = __real__ZN8CMemCard6FormatEv(self);
	SOCOM_PORT_TRACE("HOOK: MC read %u Format -> %d", reads, r);
	return r;
}

extern "C" int __real__ZN8CMemCard12GetFreeSpaceEv(CMemCard *self);
extern "C" int __wrap__ZN8CMemCard12GetFreeSpaceEv(CMemCard *self)
{
	int r = __real__ZN8CMemCard12GetFreeSpaceEv(self);
	SOCOM_PORT_TRACE("HOOK: MC read %u GetFreeSpace -> %d KB", reads, r);
	return r;
}

extern "C" bool __real__ZN8CMemCard6ExistsEPKc(CMemCard *self, const char *name);
extern "C" bool __wrap__ZN8CMemCard6ExistsEPKc(CMemCard *self, const char *name)
{
	bool r = __real__ZN8CMemCard6ExistsEPKc(self, name);
	SOCOM_PORT_TRACE("HOOK: MC read %u Exists(%s) -> %d", reads, name, r);
	return r;
}

extern "C" bool __real__ZN8CMemCard5mkdirEPKc(CMemCard *self, const char *name);
extern "C" bool __wrap__ZN8CMemCard5mkdirEPKc(CMemCard *self, const char *name)
{
	bool r = __real__ZN8CMemCard5mkdirEPKc(self, name);
	SOCOM_PORT_TRACE("HOOK: MC read %u mkdir(%s) -> %d", reads, name, r);
	return r;
}

extern "C" bool __real__ZN8CMemCard5chdirEPKc(CMemCard *self, const char *name);
extern "C" bool __wrap__ZN8CMemCard5chdirEPKc(CMemCard *self, const char *name)
{
	bool r = __real__ZN8CMemCard5chdirEPKc(self, name);
	SOCOM_PORT_TRACE("HOOK: MC read %u chdir(%s) -> %d", reads, name, r);
	return r;
}

extern "C" bool __real__ZN8CMemCard15CreateIconFilesEv(CMemCard *self);
extern "C" bool __wrap__ZN8CMemCard15CreateIconFilesEv(CMemCard *self)
{
	bool r = __real__ZN8CMemCard15CreateIconFilesEv(self);
	SOCOM_PORT_TRACE("HOOK: MC read %u CreateIconFiles -> %d (the ELF answers false always)", reads, r);
	list_dir("after CreateIconFiles", "*");
	return r;
}

extern "C" bool __real__ZN8CMemCard10SaveConfigEPKc(CMemCard *self, const char *name);
extern "C" bool __wrap__ZN8CMemCard10SaveConfigEPKc(CMemCard *self, const char *name)
{
	trace_persistent("before SaveConfig");
	trace_var("before SaveConfig", "MUSIC_VOLUME");
	bool r = __real__ZN8CMemCard10SaveConfigEPKc(self, name);
	SOCOM_PORT_TRACE("HOOK: MC read %u SaveConfig(%s) -> %d", reads, name, r);
	list_dir("after SaveConfig", "*");
	list_dir("after SaveConfig (card root)", "/*");
#ifdef SOCOM_HOOK_MC_ICONS
	/* the game writes its icons only when it makes its directory (Ensure_MC_Dirs); once, the hook
	 * has CMemCard::CreateIconFiles write them again over the game's own (same names, same dir) */
	static bool icons;
	if (!icons) {
		icons = true;
		SOCOM_PORT_TRACE("HOOK: MC read %u CreateIconFiles again (SOCOM_HOOK_MC_ICONS)", reads);
		{
			/* the disc side of the icon copy, as CreateIconFiles does it */
			char ps2path[80];
			static unsigned char buf[1024];
			CFileIO::PS2FileName("RUN\\ICONS\\LIST.ICO", ps2path, false);
			int fd = sceOpen(ps2path, 1);
			int got = fd >= 0 ? sceRead(fd, buf, 1024) : -1;
			SOCOM_PORT_TRACE("HOOK: MC icon source %s: open %d, first read %d bytes", ps2path, fd, got);
			if (fd >= 0)
				sceClose(fd);
		}
		self->CreateIconFiles();
	}
#endif
	return r;
}

extern "C" bool __real__ZN8CMemCard10LoadConfigEPKc(CMemCard *self, const char *name);
extern "C" bool __wrap__ZN8CMemCard10LoadConfigEPKc(CMemCard *self, const char *name)
{
	trace_var("before LoadConfig", "MUSIC_VOLUME");
	list_dir("before LoadConfig", "*");
	bool r = __real__ZN8CMemCard10LoadConfigEPKc(self, name);
	SOCOM_PORT_TRACE("HOOK: MC read %u LoadConfig(%s) -> %d", reads, name, r);
	trace_persistent("after LoadConfig");
	trace_var("after LoadConfig", "MUSIC_VOLUME");
	poll_stats("after LoadConfig");
	return r;
}
