/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only).
 * 1. Wraps CMission::Open (database.cpp calls it across units) and passes SOCOM_HOOK_AI as its
 *    `ai` argument: 0 = the mission's own "player only" load (CMission::LoadVehicle m_load_ai 0).
 *    The full 41-character load runs out of heap since the AI maps are read (see NOTES.md).
 * 2. A live-heap profiler: malloc/free/realloc/calloc/memalign are wrapped and every block gets
 *    a 16-byte header {magic, size, site, original pointer}. The site is the outermost tracked
 *    allocator's caller: _malloc/_new/... file:line, or the return address of operator new /
 *    new[] / plain malloc. The live bytes per site are dumped after CAiMaps::ReadMapSet. */
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <kernel.h>

extern "C" void socom_port_trace(const char *fmt, ...);

#ifdef SOCOM_HOOK_PROF
/* ---- sites ---- */
struct Site { const char *file; uint32_t line; uint32_t bytes; uint32_t count; uint32_t peak; };
static Site g_sites[4096];
static const char *g_tag_file;
static uint32_t g_tag_line;
static int g_depth;
static uint32_t g_total;

static uint32_t site_index(const char *file, uint32_t line)
{
    uint32_t h = ((uint32_t)(uintptr_t)file * 2654435761u) ^ (line * 40503u);
    for (uint32_t i = 0; i < 4096; i++)
    {
        uint32_t k = (h + i) & 4095;
        if (g_sites[k].file == file && g_sites[k].line == line)
            return k;
        if (g_sites[k].file == NULL && g_sites[k].line == 0)
        {
            g_sites[k].file = file;
            g_sites[k].line = line;
            return k;
        }
    }
    return 0;
}

struct Hdr { uint32_t magic; uint32_t size; uint32_t site; void *orig; };
static const uint32_t MAGIC = 0x50524f46u;

extern "C" void *__real_malloc(size_t);
extern "C" void __real_free(void *);
extern "C" void *__real_realloc(void *, size_t);
extern "C" void *__real_memalign(size_t, size_t);

static void *track(void *raw, void *user, size_t size, void *pc)
{
    if (raw == NULL)
        return NULL;
    Hdr *h = (Hdr *)user - 1;
    const char *file = g_depth > 0 ? g_tag_file : NULL;
    uint32_t line = g_depth > 0 ? g_tag_line : (uint32_t)(uintptr_t)pc;
    uint32_t k = site_index(file, line);
    h->magic = MAGIC;
    h->size = (uint32_t)size;
    h->site = k;
    h->orig = raw;
    g_sites[k].bytes += size;
    g_sites[k].count++;
    if (g_sites[k].bytes > g_sites[k].peak)
        g_sites[k].peak = g_sites[k].bytes;
    g_total += size;
    return user;
}

static void *alloc_at(size_t size, size_t align, void *pc)
{
    if (align < 16)
        align = 16;
    char *raw = (char *)(align == 16 ? __real_malloc(size + 16) : __real_memalign(align, size + align));
    if (raw == NULL)
        return NULL;
    char *user = align == 16 ? raw + 16 : raw + align;
    return track(raw, user, size, pc);
}

static bool untrack(void *p, Hdr **out)
{
    if (p == NULL || ((uintptr_t)p & 15) != 0)
        return false;
    Hdr *h = (Hdr *)p - 1;
    if (h->magic != MAGIC || h->site >= 4096)
        return false;
    g_sites[h->site].bytes -= h->size;
    g_sites[h->site].count--;
    g_total -= h->size;
    h->magic = 0;
    *out = h;
    return true;
}

extern "C" void *__wrap_malloc(size_t size) { return alloc_at(size, 16, __builtin_return_address(0)); }
extern "C" void *__wrap_memalign(size_t align, size_t size) { return alloc_at(size, align, __builtin_return_address(0)); }
extern "C" void *__wrap_calloc(size_t n, size_t size)
{
    void *p = alloc_at(n * size, 16, __builtin_return_address(0));
    if (p != NULL)
        memset(p, 0, n * size);
    return p;
}
extern "C" void __wrap_free(void *p)
{
    Hdr *h;
    if (untrack(p, &h))
        __real_free(h->orig);
    else
        __real_free(p);
}
extern "C" void *__wrap_realloc(void *p, size_t size)
{
    Hdr *h;
    if (p == NULL)
        return alloc_at(size, 16, __builtin_return_address(0));
    if (((uintptr_t)p & 15) == 0 && ((Hdr *)p - 1)->magic == MAGIC)
    {
        uint32_t old = ((Hdr *)p - 1)->size;
        void *n = alloc_at(size, 16, __builtin_return_address(0));
        if (n == NULL)
            return NULL;
        memcpy(n, p, old < size ? old : size);
        untrack(p, &h);
        __real_free(h->orig);
        return n;
    }
    return __real_realloc(p, size);
}

/* outer allocators: tag with file:line or the caller */
#define OUTER(file, line, call) \
    do { int d = g_depth++; if (d == 0) { g_tag_file = (file); g_tag_line = (line); } void *r = (call); g_depth--; return r; } while (0)

extern "C" void *__real__Z7_mallocjPKci(unsigned int, const char *, int);
extern "C" void *__wrap__Z7_mallocjPKci(unsigned int s, const char *f, int l) { OUTER(f, l, __real__Z7_mallocjPKci(s, f, l)); }
extern "C" void *__real__Z4_newjPKci(unsigned int, const char *, int);
extern "C" void *__wrap__Z4_newjPKci(unsigned int s, const char *f, int l) { OUTER(f, l, __real__Z4_newjPKci(s, f, l)); }
extern "C" void *__real__Z8_new_vecjPKci(unsigned int, const char *, int);
extern "C" void *__wrap__Z8_new_vecjPKci(unsigned int s, const char *f, int l) { OUTER(f, l, __real__Z8_new_vecjPKci(s, f, l)); }
extern "C" void *__real__Z9_memalignjjPKci(unsigned int, unsigned int, const char *, int);
extern "C" void *__wrap__Z9_memalignjjPKci(unsigned int a, unsigned int s, const char *f, int l) { OUTER(f, l, __real__Z9_memalignjjPKci(a, s, f, l)); }
extern "C" void *__real__Z7_callocjjPKci(unsigned int, unsigned int, const char *, int);
extern "C" void *__wrap__Z7_callocjjPKci(unsigned int n, unsigned int s, const char *f, int l) { OUTER(f, l, __real__Z7_callocjjPKci(n, s, f, l)); }
extern "C" char *__real__Z7_strdupPKcS0_i(const char *, const char *, int);
extern "C" char *__wrap__Z7_strdupPKcS0_i(const char *str, const char *f, int l) { int d = g_depth++; if (d == 0) { g_tag_file = f; g_tag_line = l; } char *r = __real__Z7_strdupPKcS0_i(str, f, l); g_depth--; return r; }
extern "C" void *__real__Znwj(unsigned int);
extern "C" void *__wrap__Znwj(unsigned int s) { OUTER("new@", (uint32_t)(uintptr_t)__builtin_return_address(0), __real__Znwj(s)); }
extern "C" void *__real__Znaj(unsigned int);
extern "C" void *__wrap__Znaj(unsigned int s) { OUTER("new[]@", (uint32_t)(uintptr_t)__builtin_return_address(0), __real__Znaj(s)); }

static void dump(const char *why)
{
    static uint32_t order[4096];
    uint32_t n = 0;
    for (uint32_t i = 0; i < 4096; i++)
        if (g_sites[i].bytes >= 16384)
            order[n++] = i;
    for (uint32_t i = 0; i < n; i++)
        for (uint32_t j = i + 1; j < n; j++)
            if (g_sites[order[j]].bytes > g_sites[order[i]].bytes) { uint32_t t = order[i]; order[i] = order[j]; order[j] = t; }
    socom_port_trace("PROF: %s: %u bytes tracked live, %u sites >= 16 KB", why, g_total, n);
    for (uint32_t i = 0; i < n && i < 60; i++)
    {
        Site &s = g_sites[order[i]];
        if (s.file != NULL && s.file[0] != 'n')
            socom_port_trace("PROF: %8u B %6u blocks (peak %8u) %s:%u", s.bytes, s.count, s.peak, s.file, s.line);
        else
            socom_port_trace("PROF: %8u B %6u blocks (peak %8u) %s%08x", s.bytes, s.count, s.peak, s.file != NULL ? s.file : "pc ", s.line);
    }
}

#else
static void dump(const char *) { }
#endif

class CMission;
extern "C" void __real__ZN8CMission4OpenEPKci(CMission *, const char *, int);
extern "C" void __wrap__ZN8CMission4OpenEPKci(CMission *m, const char *db, int ai)
{
    socom_port_trace("HOOK: CMission::Open(%s, ai %d) -> ai %d", db, ai, SOCOM_HOOK_AI);
    dump("before CMission::Open");
    __real__ZN8CMission4OpenEPKci(m, db, SOCOM_HOOK_AI);
    dump("after CMission::Open");
}
