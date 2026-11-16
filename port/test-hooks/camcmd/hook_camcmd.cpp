/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-small3, the camera animation commands' text parsers
 * (src/gamez/zCamera/zcam_main.cpp). The disc's anims come compiled, so the parsers only run on
 * text: the hook serves its own reader file "ztest/camcmd.rdr" from memory (a CBufferIO::Open wrap,
 * as port/test-hooks/zreader does), reads it with zrdr_read and feeds every command of it through
 * the zAnim text path's CZAnimMain::AnimParseCmd (the registered parser by name, data type set).
 * Each record is dumped (header, the record's own fields, the CAMERA_PARAMS keys), then given to
 * the command's registered begin / tick (the ticks of DYNAMICS_*, SET / GET_CAMERA_REGION_TEST and
 * CAMERA_INDOORS; CAMERA_PARAMS SAVE + keys at t = 1 s, then RESTORE) with the switches and the
 * world camera's fields of view, planes, fog and range scale traced before / after; the switches
 * are put back. It runs once, SOCOM_CAMCMD_DELAY HUD ticks (default 300) after the mission
 * cameras have stopped playing (CHUD::Tick wrap). Built with ../state/hook_state.cpp (build.sh). */
#include <list>
#include <vector>
#define protected public
#define private public
#include "gamez/zCamera/zcam.h"
#include "gamez/zNode/znode.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zAnim/zanim.h"
#include "gamez/zReader/zrdr.h"
#include "gamez/zUtil/util_systemio.h"
#include "gamez/zSystem/zsys.h"
#include "Apps/FTS/hud/hud.h"
#include <stdio.h>
#include <string.h>

#ifndef SOCOM_CAMCMD_DELAY
#define SOCOM_CAMCMD_DELAY 300
#endif

extern "C" unsigned char __real__ZN9CBufferIO4OpenEPKcj(CBufferIO *self, const char *name, unsigned int mode);
extern "C" void __real__ZN4CHUD4TickEf(CHUD *hud, float dT);

namespace
{
/* one command per line: name, then its reader array (the value AnimParseCmd gets) */
const char g_text[] =
    "; camera command parsers self-test (test hook)\n"
    "camcmd (\n"
    "  DYNAMICS_RELEASE_CAMERA ( 1 )\n"
    "  DYNAMICS_ACQUIRE_CAMERA ( 1 )\n"
    "  CAMERA_INDOORS ( 1 )\n"
    "  SET_CAMERA_REGION_TEST ( ON )\n"
    "  SET_CAMERA_REGION_TEST ( OFF )\n"
    "  GET_CAMERA_REGION_TEST ( 1 )\n"
    "  CAMERA_PARAMS ( SAVE_PARAMS FOG_ON FOG_ALTITUDE_OFF\n"
    "    FOV ( 0 70 52.5 2 60 45 )\n"
    "    CLIP ( 0 4 600 )\n"
    "    CLIP_ALL ( 0 4 3000 3200 1.5 5 2500 2800 )\n"
    "    FOG_RANGE ( 0 200 2100 )\n"
    "    FOG_ALTITUDE ( 0 10 40 )\n"
    "    LOD_MULTIPLIER ( 0 1.5 3 2 ) )\n"
    "  CAMERA_PARAMS ( RESTORE_PARAMS FOG_OFF FOG_ALTITUDE_ON )\n"
    ")\n";

bool g_done;
bool g_cams_seen;
unsigned g_after;

void cam_state(const char *when)
{
    zdb::CCamera *c = zdb::CWorld::m_world != NULL ? zdb::CWorld::m_world->m_camera : NULL;

    if (c == NULL)
    {
        SOCOM_PORT_TRACE("HOOK CAMCMD: %s: no world camera", when);
        return;
    }

    SOCOM_PORT_TRACE("HOOK CAMCMD: %s: dyn %d region %d inside %d | hfov %.4f vfov %.4f (rad, half) near %.3f mid %.3f far %.3f"
                     " fog %d alt %d range %.1f..%.1f alt %.2f..%.2f lod %.4f",
                     when, (int)zdb::CCamera::m_dynamics_controlled, (int)zdb::CCamera::m_do_region_test, (int)c->m_IsInside,
                     c->m_hfov, c->m_vfov, c->m_near_plane, c->m_mid_plane, c->m_far_plane, (int)c->m_fog_enabled,
                     (int)c->m_fog_alt_enabled, c->m_fog_near, c->m_fog_far, c->m_fog_bottom, c->m_fog_top, c->m_RangeScale);
}

f32 rf(const u8 *b, unsigned off)
{
    f32 f;
    memcpy(&f, b + off, 4);
    return f;
}

u16 rh(const u8 *b, unsigned off)
{
    u16 h;
    memcpy(&h, b + off, 2);
    return h;
}

void dump(const char *name, _zanim_cmd_hdr *cmd)
{
    if (cmd == NULL)
    {
        SOCOM_PORT_TRACE("HOOK CAMCMD: parse %s -> NULL", name);
        return;
    }

    const u8 *b = reinterpret_cast<const u8 *>(cmd);
    SOCOM_PORT_TRACE("HOOK CAMCMD: parse %s -> type %04x size %u timeless %u quad %u, word +4 %08x", name, (unsigned)cmd->data_type,
                     (unsigned)cmd->data_size, (unsigned)cmd->timeless, (unsigned)cmd->quad_align,
                     cmd->data_size >= 8 ? (unsigned)(b[4] | b[5] << 8 | b[6] << 16 | b[7] << 24) : 0u);

    if (strcmp(name, "CAMERA_PARAMS") != 0)
        return;

    static const char *const tracks[6] = { "FOV", "CLIP", "CLIP_ALL", "FOG_RANGE", "FOG_ALTITUDE", "LOD_MULTIPLIER" };
    static const unsigned widths[6] = { 3, 3, 4, 3, 3, 2 };
    SOCOM_PORT_TRACE("HOOK CAMCMD:   flags save %u restore %u fog_set %u fog %u alt_set %u alt %u run_time %.3f", b[4] & 1,
                     (b[4] >> 1) & 1, (b[4] >> 2) & 1, (b[4] >> 3) & 1, (b[4] >> 4) & 1, (b[4] >> 5) & 1, rf(b, 8));

    for (int t = 0; t < 6; t++)
    {
        unsigned off = rh(b, 0xc + 4 * t);
        unsigned n = rh(b, 0xe + 4 * t);
        char line[256];
        int len = snprintf(line, sizeof(line), "HOOK CAMCMD:   %s offset %u count %u:", tracks[t], off, n);

        for (unsigned k = 0; off != 0 && k < n && len < (int)sizeof(line) - 40; k++)
        {
            len += snprintf(line + len, sizeof(line) - len, " {");

            for (unsigned w = 0; w < widths[t]; w++)
                len += snprintf(line + len, sizeof(line) - len, w ? " %g" : "%g", (double)rf(b, off + 4 * (k * widths[t] + w)));

            len += snprintf(line + len, sizeof(line) - len, "}");
        }

        SOCOM_PORT_TRACE("%s", line);
    }
}

typedef void (*BeginFn)(_zanim_cmd_hdr *);
typedef bool (*TickFn)(_zanim_cmd_hdr *, f32 *);

void run_cmd(const char *name, _zanim_cmd_hdr *cmd, f32 dT)
{
    zanim_cmd *entry = ZAnim.GetCmdEntry(name, false);

    if (entry == NULL || cmd == NULL)
        return;

    if (entry->begin != NULL)
        reinterpret_cast<BeginFn>(entry->begin)(cmd);

    f32 t = dT;
    bool done = entry->tick != NULL ? reinterpret_cast<TickFn>(entry->tick)(cmd, &t) : true;
    char when[96];
    snprintf(when, sizeof(when), "after %s%s tick(dT %.2f -> %.2f) = %d", name, entry->begin != NULL ? " begin +" : "", dT, t,
             (int)done);
    cam_state(when);
}

void selftest()
{
    SOCOM_PORT_TRACE("HOOK CAMCMD: self-test start");
    CRdrFile *rdr = zrdr_read("camcmd.rdr", "ztest", 1);

    if (rdr == NULL || !rdr->IsArray())
    {
        SOCOM_PORT_TRACE("HOOK CAMCMD: camcmd.rdr not parsed");
        return;
    }

    _zrdr *list = zrdr_findtag(rdr, "camcmd");

    if (list == NULL || !list->IsArray())
    {
        SOCOM_PORT_TRACE("HOOK CAMCMD: no camcmd list");
        return;
    }

    bool dyn = zdb::CCamera::m_dynamics_controlled;
    bool region = zdb::CCamera::m_do_region_test;
    _zsequence fake;
    memset(&fake, 0, sizeof(fake));
    _zsequence *seq = ZAnim.m_CurSeq;

    if (ZAnim.m_CurSeq == NULL)
        ZAnim.m_CurSeq = &fake; /* CmdTickParams reads the current sequence's cmd_timer (0 here) */

    cam_state("before");
    u32 n = list->array->integer;

    for (u32 i = 1; i + 1 < n; i++)
    {
        _zrdr *key = &list->array[i];

        if (key->type != ZRDR_STRING)
            continue;

        _zanim_cmd_hdr *cmd = ZAnim.AnimParseCmd(key->string, &list->array[i + 1]);
        dump(key->string, cmd);
        run_cmd(key->string, cmd, 1.0f);

        if (cmd != NULL)
            _free(cmd, "hook_camcmd.cpp", __LINE__);

        i++;
    }

    _zanim_cmd_hdr *null_cmd = ZAnim.AnimParseCmd("DYNAMICS_RELEASE_CAMERA", NULL);
    SOCOM_PORT_TRACE("HOOK CAMCMD: parse DYNAMICS_RELEASE_CAMERA with a NULL reader -> %p", (void *)null_cmd);

    ZAnim.m_CurSeq = seq;
    zdb::CCamera::m_dynamics_controlled = dyn;
    zdb::CCamera::m_do_region_test = region;
    cam_state("end (switches put back)");
    zrdr_free(rdr);
    SOCOM_PORT_TRACE("HOOK CAMCMD: self-test end");
}
} // namespace

extern "C" unsigned char __wrap__ZN9CBufferIO4OpenEPKcj(CBufferIO *self, const char *name, unsigned int mode)
{
    if (name != NULL && strcmp(name, "ztest/camcmd.rdr") == 0)
    {
        size_t size = sizeof(g_text) - 1;
        void *copy = _malloc(size, "hook_camcmd.cpp", __LINE__);
        memcpy(copy, g_text, size);
        return self->Open(copy, size);
    }

    return __real__ZN9CBufferIO4OpenEPKcj(self, name, mode);
}

extern "C" void __wrap__ZN4CHUD4TickEf(CHUD *hud, float dT)
{
    __real__ZN4CHUD4TickEf(hud, dT);

    if (g_done || zdb::CWorld::m_world == NULL || zdb::CWorld::m_world->m_camera == NULL)
        return;

    if (hud->m_missioncams.IsPlaying())
    {
        g_cams_seen = true;
        g_after = 0;
        return;
    }

    if (!g_cams_seen || ++g_after < SOCOM_CAMCMD_DELAY)
        return;

    g_done = true;
    selftest();
}
