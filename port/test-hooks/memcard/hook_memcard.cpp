/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-mod-sys, the memory-card path (zUtil CMemCard / CMemCardIO,
 * zSave CSaveManager, zArchive writes, zReader Pack, port/compat/libmc.c) in one run. Wraps
 * scePadRead; at pad read SOCOM_HOOK_MC_AT (default 300: the title screen) it runs, once:
 *  - theMemCard.Init (UIMC_Init), IsInserted, IsFormatted, GetFreeSpace on port 0 slot 0;
 *  - mkdir / chdir SOCOM_HOOK_MC_DIR ("/SOCOMSYS");
 *  - a PERSISTENT UI variable SYSTEST = 1234, SaveConfig("SYSCFG") (theUIVarManager's
 *    Serialize through the options manager), the header read back (GetHeader);
 *  - SYSTEST set to 5678, LoadConfig("SYSCFG"): SYSTEST must be 1234 again;
 *  - Exists("SYSCFG"), CreateIconFiles;
 *  - the files and the directory deleted again (the emulator's card is the user's).
 * Each step is traced (HOOK: MC ...) with the heap. */
#include <string>
#define protected public
#define private public
#include "gamez/zUtil/zutil.h"
#include "gamez/zSave/zsave.h"
#include "gamez/zUI/zui.h"
#include <string.h>
#include <stdio.h>
#include <libmc.h>

#ifndef SOCOM_HOOK_MC_AT
#define SOCOM_HOOK_MC_AT 300
#endif
#ifndef SOCOM_HOOK_MC_DIR
#define SOCOM_HOOK_MC_DIR "/SOCOMSYS"
#endif

void socom_port_trace(const char *fmt, ...);
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);
extern "C" int socom_port_memcard;

namespace
{
int reads;

int VarInt(const char *name)
{
	CUIVariable *var = theUIVarManager.Find(name);
	if (var == NULL)
		return -1;
	return var->type == ZRDR_INTEGER ? var->integer : -2;
}

void SetVar(const char *name, int value, UIVAR_LONGEVITY longevity)
{
	_zrdr v;
	v.type = ZRDR_INTEGER;
	v.isclone = 0;
	v.packed = 0;
	v.integer = value;
	CUIVariable *var = theUIVarManager.Find(name);
	if (var == NULL)
		var = theUIVarManager.Add(name, &v, longevity);
	else
		var->Set(&v);
	if (var != NULL && var->m_longevity < longevity)
		var->m_longevity = longevity;
}

void RunTest()
{
	theMemCard.m_card_port = 0;
	theMemCard.m_card_slot = 0;
	socom_port_memcard = 1; /* the card layer is off in every build unless a test turns it on (port/compat/libmc.c) */
	theMemCard.Init();
	{
		int type = -1, free = -1, format = -1, cmd = 0, result = 0;
		int r = sceMcGetInfo(0, 0, &type, &free, &format);
		int s = sceMcSync(0, &cmd, &result);
		socom_port_trace("HOOK: MC raw GetInfo -> %d, sync %d result %d: type %d free %d format %d", r, s, result, type, free, format);
		for (int port = 0; port < 2; port++) {
			r = sceMcGetInfo(port, 0, &type, &free, &format);
			s = sceMcSync(0, &cmd, &result);
			socom_port_trace("HOOK: MC raw GetInfo port %d -> %d, sync %d result %d: type %d free %d format %d", port, r, s, result, type, free, format);
		}
	}
	bool inserted = theMemCard.IsInserted();
	bool formatted = theMemCard.IsFormatted();
	int space = theMemCard.GetFreeSpace();
	socom_port_trace("HOOK: MC init: inserted %d formatted %d free %d KB", inserted, formatted, space);
	if (!inserted || !formatted)
		return;
	bool made = theMemCard.mkdir(SOCOM_HOOK_MC_DIR);
	bool in = theMemCard.chdir(SOCOM_HOOK_MC_DIR);
	socom_port_trace("HOOK: MC mkdir %s -> %d, chdir -> %d", SOCOM_HOOK_MC_DIR, made, in);
	SetVar("SYSTEST", 1234, UIVL_PERSISTENT);
	socom_port_trace("HOOK: MC SYSTEST = %d before the save", VarInt("SYSTEST"));
	bool saved = theMemCard.SaveConfig("SYSCFG");
	CSaveManager::CSaveHeader header;
	memset(&header, 0, sizeof(header));
	bool got = theMemCard.m_config->GetHeader("SYSCFG", 1, &header);
	socom_port_trace("HOOK: MC SaveConfig -> %d; header %d: size %u version %d flags %d", saved, got,
		header.m_size, header.m_version, header.m_flags);
	SetVar("SYSTEST", 5678, UIVL_PERSISTENT);
	socom_port_trace("HOOK: MC SYSTEST = %d before the load", VarInt("SYSTEST"));
	bool loaded = theMemCard.LoadConfig("SYSCFG");
	int after = VarInt("SYSTEST");
	socom_port_trace("HOOK: MC LoadConfig -> %d; SYSTEST = %d after the load (%s)", loaded, after,
		after == 1234 ? "RESTORED" : "NOT RESTORED");
	socom_port_trace("HOOK: MC Exists(SYSCFG) -> %d", theMemCard.Exists("SYSCFG"));
	theMemCard.CreateIconFiles();
	socom_port_trace("HOOK: MC CreateIconFiles done; Exists(icon.sys) -> %d", theMemCard.Exists("icon.sys"));
	/* the card is the user's: take the test files and directory away again */
	static const char *const files[] = { "SYSCFG", "icon.sys", "LIST.ICO", "COPYING.ICO", "DELETING.ICO" };
	int cmd, result;
	for (unsigned i = 0; i < sizeof(files) / sizeof(files[0]); i++) {
		sceMcDelete(0, 0, files[i]);
		sceMcSync(0, &cmd, &result);
	}
	theMemCard.chdir("/");
	sceMcDelete(0, 0, SOCOM_HOOK_MC_DIR);
	sceMcSync(0, &cmd, &result);
	socom_port_trace("HOOK: MC clean-up: %s deleted -> %d; Exists -> %d", SOCOM_HOOK_MC_DIR, result, theMemCard.Exists(SOCOM_HOOK_MC_DIR));
}
}

extern "C" int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
	if (port == 0 && ++reads == SOCOM_HOOK_MC_AT)
		RunTest();
	return __real_scePadRead(port, slot, rdata);
}
