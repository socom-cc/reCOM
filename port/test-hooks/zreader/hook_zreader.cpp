/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-zreader-fix, the text reader's file stack and preprocessor
 * (src/gamez/zReader/zrdr_parse.cpp). No reader on the disc uses #include / #ifdef / #else /
 * #endif, so the hook serves its own text files:
 *  - wraps CBufferIO::Open(const char *, unsigned): a name under "ztest/" is served from the
 *    in-memory files below (Open(void *, size) on an _malloc'd copy, as a loaded file); any other
 *    name is opened as usual. Every .rdr open is traced with the file stack's depth before the push.
 *  - wraps zrdr_read: every read is traced (name, path, flags, result, stack depth after); the
 *    first read of the run also runs the self-test once: zrdr_read("main.rdr", "ztest", 1), then
 *    the parsed elements are dumped with the symbol count (zrdr_symbols, never filled in the ELF).
 *    e3config.rdr (the raw reader CLoadState::Init reads) is dumped: entries, names, game_time.
 * Pair with a diag spec on pop__10CFileStackFb for the pops (see port/test-hooks/README.md).
 * Built with ../state/hook_state.cpp (build.sh), which drives the menus and m8. */
#include "gamez/zReader/zrdr.h"
#include "gamez/zUtil/util_stack.h"
#include "gamez/zUtil/util_systemio.h"
#include "gamez/zSystem/zsys.h"
#include <string.h>
#include <stdio.h>
#include <strings.h>

extern "C" unsigned char __real__ZN9CBufferIO4OpenEPKcj(CBufferIO *self, const char *name, unsigned int mode);
extern "C" CRdrFile *__real__Z9zrdr_readPKcS0_i(const char *name, const char *path, int flags);

namespace
{
struct TestFile
{
    const char *name;
    const char *text;
};

/* ztest/main.rdr includes inc.rdr, which includes inc2.rdr (stack depth 3); then an #ifdef of a
 * symbol nothing defines (the #else branch is read), an include written with quotes (the ELF keeps
 * the quotes in the name) and a #define (not a directive of this reader). */
const TestFile g_files[] = {
    { "ztest/main.rdr",
      "; zreader self-test (test hook)\n"
      "zt_a (1)\n"
      "#include inc.rdr\n"
      "zt_b (\"two\")\n"
      "#ifdef ZT_SYM\n"
      "zt_c (3)\n"
      "#else\n"
      "zt_d (4)\n"
      "#endif\n"
      "#include \"quoted.rdr\"\n"
      "#define ZT_DEF 5\n"
      "zt_e (6.5)\n" },
    { "ztest/inc.rdr",
      "zt_inc (7)\n"
      "#include inc2.rdr\n"
      "zt_inc_after (8)\n" },
    { "ztest/inc2.rdr",
      "zt_inc2 (9)\n" },
};

bool g_selftest_done;

void dump(const _zrdr *node, int depth, char *out, size_t cap)
{
    char tmp[64];

    switch (node->type)
    {
    case ZRDR_INTEGER: snprintf(tmp, sizeof(tmp), "%d", node->integer); break;
    case ZRDR_REAL: snprintf(tmp, sizeof(tmp), "%g", (double)node->real); break;
    case ZRDR_STRING: snprintf(tmp, sizeof(tmp), "'%s'", node->string); break;
    case ZRDR_ARRAY:
    {
        strncat(out, "(", cap - strlen(out) - 1);
        u32 n = (u32)node->array->integer;

        for (u32 i = 1; i < n; i++)
        {
            if (i > 1)
                strncat(out, " ", cap - strlen(out) - 1);
            dump(&node->array[i], depth + 1, out, cap);
        }

        strncat(out, ")", cap - strlen(out) - 1);
        return;
    }
    default: snprintf(tmp, sizeof(tmp), "null"); break;
    }

    strncat(out, tmp, cap - strlen(out) - 1);
}

void selftest()
{
    SOCOM_PORT_TRACE("HOOK: zrdr selftest: start, stack depth %d, symbols %d", (int)fstack.size(),
                     (int)zrdr_symbols.size());
    CRdrFile *rdr = zrdr_read("main.rdr", "ztest", 1);

    if (rdr == NULL)
    {
        SOCOM_PORT_TRACE("HOOK: zrdr selftest: main.rdr not parsed (NULL), stack depth %d",
                         (int)fstack.size());
        return;
    }

    static char line[1024];
    line[0] = '\0';
    dump(rdr, 0, line, sizeof(line));
    SOCOM_PORT_TRACE("HOOK: zrdr selftest: parsed %s", line);
    SOCOM_PORT_TRACE("HOOK: zrdr selftest: end, stack depth %d, symbols %d", (int)fstack.size(),
                     (int)zrdr_symbols.size());
    zrdr_free(rdr);
}

void dump_e3config(CRdrFile *rdr)
{
    u32 n = rdr->IsArray() ? (u32)rdr->array->integer - 1 : 0;
    SOCOM_PORT_TRACE("HOOK: zrdr e3config.rdr: %u entries", n);

    for (u32 i = 0; i < n; i++)
    {
        _zrdr *entry = rdr->Get(i);
        _zrdr *first = entry != NULL ? entry->Get(0) : NULL;
        s32 seconds = -1;
        s32 rounds = -1;

        if (entry != NULL)
        {
            zrdr_findint(entry, "game_time", &seconds, 1);
            zrdr_findint(entry, "round_count", &rounds, 1);
        }

        SOCOM_PORT_TRACE("HOOK: zrdr e3config.rdr: entry %u '%s' game_time %d round_count %d type %s", i,
                         first != NULL && first->type == ZRDR_STRING ? first->string : "?", seconds, rounds,
                         entry != NULL ? zrdr_findstring(entry, "mp_game_type") : "?");
    }
}
} // namespace

extern "C" unsigned char __wrap__ZN9CBufferIO4OpenEPKcj(CBufferIO *self, const char *name, unsigned int mode)
{
    if (name != NULL && strncmp(name, "ztest/", 6) == 0)
    {
        for (const TestFile &f : g_files)
        {
            if (strcmp(f.name, name) == 0)
            {
                size_t size = strlen(f.text);
                void *copy = _malloc(size, "hook_zreader.cpp", __LINE__);
                memcpy(copy, f.text, size);
                SOCOM_PORT_TRACE("HOOK: zrdr open '%s' (served, %u B), stack depth %d", name, (unsigned)size,
                                 (int)fstack.size());
                return self->Open(copy, size);
            }
        }

        SOCOM_PORT_TRACE("HOOK: zrdr open '%s' (no such test file: fails), stack depth %d", name,
                         (int)fstack.size());
        return 0;
    }

    unsigned char ok = __real__ZN9CBufferIO4OpenEPKcj(self, name, mode);
    size_t len = name != NULL ? strlen(name) : 0;

    if (len > 4 && strcasecmp(name + len - 4, ".rdr") == 0)
        SOCOM_PORT_TRACE("HOOK: zrdr open '%s' -> %d, stack depth %d", name, ok, (int)fstack.size());

    return ok;
}

extern "C" CRdrFile *__wrap__Z9zrdr_readPKcS0_i(const char *name, const char *path, int flags)
{
    CRdrFile *rdr = __real__Z9zrdr_readPKcS0_i(name, path, flags);
    SOCOM_PORT_TRACE("HOOK: zrdr_read '%s' path '%s' flags %d -> %p, stack depth %d", name,
                     path != NULL ? path : "(null)", flags, (void *)rdr, (int)fstack.size());

    if (rdr != NULL && name != NULL && strcmp(name, "e3config.rdr") == 0)
        dump_e3config(rdr);

    if (!g_selftest_done)
    {
        g_selftest_done = true;
        selftest();
    }

    return rdr;
}
