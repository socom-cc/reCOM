/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): heap maps for the state round trips (build.sh HMAP=1 with -DSOCOM_HOOK_HEAPMAP,
 * instead of -DSOCOM_HOOK_MALLOC / HLEAK). Every block handed out by malloc / calloc / realloc / memalign is
 * remembered with its allocation site (the game's _malloc / _calloc / _memalign / _strdup / _new / _new_vec
 * file:line, else the caller of operator new / new[], else the caller of malloc) in a compact table
 * (832 KB of bss, no heap use); free forgets it. socom_hmap_dump() walks newlib's heap chunk by chunk and
 * prints, without allocating (sio_puts, integer formats only): every free chunk of SOCOM_HMAP_FREE (4 KB)
 * or more, between them each run of in-use chunks with its bytes and top sites (runs of up to 8 chunks:
 * every chunk), every in-use chunk of 64 KB or more, and a summary (largest hole, top chunk, room left
 * below the heap end, the largest block malloc could hand out). The hook itself never probes the heap
 * with test allocations, so the layout is the game's own.
 *  - every memalign / malloc of SOCOM_HMAP_BIG (2 MB) or more: a map before it (the first SOCOM_HMAP_MAPS)
 *    or a summary, and the address it got;
 *  - -DSOCOM_HMAP_XSIZE=<bytes> [-DSOCOM_HMAP_XCOUNT=<n>] [-DSOCOM_HMAP_XAT=0|1]: a test-only boot
 *    allocation of n blocks (kept for ever): 0 = before the game's global constructors, 1 (default) right
 *    after the CSaveModule("CMission") constructor in __sinit of fts_mission.cpp, where the ELF builds
 *    theValveSaveManager (its zstrdup and list node). */
#include <stdint.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <malloc.h>
#include <unistd.h>
#include <kernel.h>
#include <sio.h>

#ifndef SOCOM_HMAP_FREE
#define SOCOM_HMAP_FREE 4096
#endif
#ifndef SOCOM_HMAP_BIG
#define SOCOM_HMAP_BIG 0x200000
#endif
#ifndef SOCOM_HMAP_MAPS
#define SOCOM_HMAP_MAPS 4
#endif
#ifndef SOCOM_HMAP_XCOUNT
#define SOCOM_HMAP_XCOUNT 1
#endif
#ifndef SOCOM_HMAP_XAT
#define SOCOM_HMAP_XAT 1
#endif

extern "C" void __real_free(void *p);
extern "C" void *__real_malloc(size_t n);
extern "C" void *__real_calloc(size_t a, size_t b);
extern "C" void *__real_realloc(void *p, size_t n);
extern "C" void *__real_memalign(size_t a, size_t n);
extern "C" void *__real__Z7_mallocjPKci(size_t n, const char *f, int l);
extern "C" void *__real__Z7_callocjjPKci(size_t a, size_t b, const char *f, int l);
extern "C" void *__real__Z9_memalignjjPKci(size_t a, size_t n, const char *f, int l);
extern "C" char *__real__Z7_strdupPKcS0_i(const char *s, const char *f, int l);
extern "C" void *__real__Z4_newjPKci(size_t n, const char *f, int l);
extern "C" void *__real__Z8_new_vecjPKci(size_t n, const char *f, int l);
extern "C" void *__real__Znwj(unsigned int n);
extern "C" void *__real__Znaj(unsigned int n);
extern "C" char *__malloc_sbrk_base;
extern "C" char *__malloc_av_[];

/* ---- sites and the block table ---- */
#ifdef SOCOM_HMAP_NOTAG
/* -DSOCOM_HMAP_NOTAG: no block table (16 slots, nothing recorded): maps and sums without sites, and the
 * hook's bss stays small, so the heap ends where a default build's does */
#define SLOTS 16u
#define NSITES 16
#else
#define SLOTS (1u << 17)
#define NSITES 8192
#endif
struct Site { uintptr_t tag; uint32_t line; uint32_t kind; };
static Site g_site[NSITES];
static uint16_t g_sitehash[NSITES * 2];
static unsigned g_nsites;
static uint32_t g_tp[SLOTS];
static uint16_t g_ts[SLOTS];
static uint8_t g_tph[SLOTS]; /* the hook's phase (state changes seen) when the block was made */
static unsigned g_phase;
extern "C" void socom_hmap_phase(unsigned phase) { g_phase = phase; }
static unsigned g_full, g_sitefull, g_nalloc, g_nfree;
static const char *g_file;
static int g_line;
static int g_depth;
static void *g_newra;
static int g_quiet; /* the hook's own work: not tracked */

enum { K_FILE = 1, K_NEW = 2, K_CALLER = 3, K_LIBC = 4 };

static unsigned site_of(uintptr_t tag, uint32_t line, uint32_t kind)
{
    unsigned h = (unsigned)((tag * 2654435761u) ^ (line * 40503u)) & (NSITES * 2 - 1);

    for (unsigned k = 0; k < NSITES * 2; k++, h = (h + 1) & (NSITES * 2 - 1))
    {
        unsigned s = g_sitehash[h];

        if (s == 0)
        {
            if (g_nsites + 1 >= NSITES)
            {
                g_sitefull++;
                return 0;
            }

            s = ++g_nsites;
            g_site[s].tag = tag;
            g_site[s].line = line;
            g_site[s].kind = kind;
            g_sitehash[h] = (uint16_t)s;
            return s;
        }

        if (g_site[s].tag == tag && g_site[s].line == line && g_site[s].kind == kind)
            return s;
    }

    return 0;
}

static unsigned slot(uint32_t p) { return (unsigned)((p >> 3) * 2654435761u) & (SLOTS - 1); }

static void add(void *q, unsigned site)
{
    if (q == NULL)
        return;

    uint32_t p = (uint32_t)(uintptr_t)q;
    g_nalloc++;
#ifdef SOCOM_HMAP_NOTAG
    (void)site;
    return;
#endif

    for (unsigned i = slot(p), k = 0; k < 4096; i = (i + 1) & (SLOTS - 1), k++)
    {
        if (g_tp[i] == 0 || g_tp[i] == p)
        {
            g_tp[i] = p;
            g_ts[i] = (uint16_t)site;
            g_tph[i] = (uint8_t)(g_phase < 255 ? g_phase : 255);
            return;
        }
    }

    g_full++;
}

static int find(uint32_t p)
{
    for (unsigned i = slot(p), k = 0; k < SLOTS && g_tp[i] != 0; i = (i + 1) & (SLOTS - 1), k++)
        if (g_tp[i] == p)
            return (int)i;

    return -1;
}

static void del(void *q)
{
    if (q == NULL)
        return;

    int f = find((uint32_t)(uintptr_t)q);

    if (f < 0)
        return;

    g_nfree++;
    unsigned j = (unsigned)f;
    g_tp[j] = 0;

    for (unsigned k = (j + 1) & (SLOTS - 1); g_tp[k] != 0; k = (k + 1) & (SLOTS - 1))
    {
        unsigned h = slot(g_tp[k]);
        bool move = (k > j) ? (h <= j || h > k) : (h <= j && h > k);

        if (move)
        {
            g_tp[j] = g_tp[k];
            g_ts[j] = g_ts[k];
            g_tph[j] = g_tph[k];
            g_tp[k] = 0;
            j = k;
        }
    }
}

static void *track(void *q, void *ra, bool libc)
{
    if (g_quiet)
        return q;

    unsigned s;

    if (g_depth == 0)
        s = site_of((uintptr_t)(g_newra != NULL ? g_newra : ra), 0, g_newra != NULL ? K_NEW : libc ? K_LIBC : K_CALLER);
    else if (g_line == 0 && g_newra != NULL)
        s = site_of((uintptr_t)g_newra, 0, K_NEW);
    else
        s = site_of((uintptr_t)g_file, (uint32_t)g_line, K_FILE);

    add(q, s);
    return q;
}

/* ---- output without the heap ---- */
static char g_out[256];

static void out(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void out(const char *fmt, ...)
{
    int n = snprintf(g_out, sizeof(g_out), "[socom-port] HOOK: map ");
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(g_out + n, sizeof(g_out) - n, fmt, ap);
    va_end(ap);
    sio_puts(g_out);
}

static const char *site_text(unsigned s, char *buf, size_t n)
{
    if (s == 0 || s > g_nsites)
        snprintf(buf, n, "?");
    else if (g_site[s].kind == K_FILE)
    {
        const char *f = (const char *)g_site[s].tag;
        const char *b = strrchr(f, '/');
        snprintf(buf, n, "%s:%u", b != NULL ? b + 1 : f, (unsigned)g_site[s].line);
    }
    else
        snprintf(buf, n, "%s%08x", g_site[s].kind == K_NEW ? "new@" : g_site[s].kind == K_LIBC ? "lc@" : "c@", (unsigned)g_site[s].tag);

    return buf;
}

static unsigned site_at(char *chunk)
{
    int f = find((uint32_t)(uintptr_t)(chunk + 8));
    return f < 0 ? 0xffff : g_ts[f];
}

static unsigned phase_at(char *chunk)
{
    int f = find((uint32_t)(uintptr_t)(chunk + 8));
    return f < 0 ? 255 : g_tph[f];
}

/* ---- the walk ---- */
struct RunSite { unsigned site; uint32_t bytes; uint32_t count; };
static RunSite g_rs[256];
static int g_nrs;
static char *g_run;
static uint32_t g_run_bytes, g_run_count, g_run_dust;
static char *g_first_chunks[8];
static uint32_t g_first_sizes[8];

static void run_add(char *p, uint32_t size)
{
    if (g_run == NULL)
        g_run = p;

    if (g_run_count < 8)
    {
        g_first_chunks[g_run_count] = p;
        g_first_sizes[g_run_count] = size;
    }

    g_run_bytes += size;
    g_run_count++;
    unsigned s = site_at(p);
    int k;

    for (k = 0; k < g_nrs; k++)
        if (g_rs[k].site == s)
            break;

    if (k == g_nrs)
    {
        if (g_nrs == 256)
            return;

        g_rs[k].site = s;
        g_rs[k].bytes = 0;
        g_rs[k].count = 0;
        g_nrs++;
    }

    g_rs[k].bytes += size;
    g_rs[k].count++;
}

static void run_report(char *end)
{
    if (g_run != NULL)
    {
        char a[48], b[48], c[48];

        if (g_run_count <= 8)
        {
            for (unsigned i = 0; i < g_run_count; i++)
                out("u %08x %u %s p%u", (unsigned)(uintptr_t)g_first_chunks[i], (unsigned)g_first_sizes[i],
                    site_text(site_at(g_first_chunks[i]), a, sizeof(a)), phase_at(g_first_chunks[i]));
        }
        else
        {
            for (int n = 0; n < 3 && n < g_nrs; n++)
            {
                int best = n;

                for (int k = n + 1; k < g_nrs; k++)
                    if (g_rs[k].bytes > g_rs[best].bytes)
                        best = k;

                RunSite t = g_rs[n]; g_rs[n] = g_rs[best]; g_rs[best] = t;
            }

            out("U %08x..%08x %u in %u (dust %u) | %s %u/%u | %s %u/%u | %s %u/%u", (unsigned)(uintptr_t)g_run,
                (unsigned)(uintptr_t)end, (unsigned)g_run_bytes, (unsigned)g_run_count, (unsigned)g_run_dust,
                g_nrs > 0 ? site_text(g_rs[0].site, a, sizeof(a)) : "-", g_nrs > 0 ? (unsigned)g_rs[0].bytes : 0, g_nrs > 0 ? (unsigned)g_rs[0].count : 0,
                g_nrs > 1 ? site_text(g_rs[1].site, b, sizeof(b)) : "-", g_nrs > 1 ? (unsigned)g_rs[1].bytes : 0, g_nrs > 1 ? (unsigned)g_rs[1].count : 0,
                g_nrs > 2 ? site_text(g_rs[2].site, c, sizeof(c)) : "-", g_nrs > 2 ? (unsigned)g_rs[2].bytes : 0, g_nrs > 2 ? (unsigned)g_rs[2].count : 0);
        }
    }

    g_run = NULL;
    g_run_bytes = g_run_count = g_run_dust = 0;
    g_nrs = 0;
}

static char *first_chunk()
{
    for (uintptr_t align = 16; align >= 8; align /= 2)
    {
        char *c = __malloc_sbrk_base;

        while (((uintptr_t)c + 8) % align != 0)
            c++;

        size_t s = *(size_t *)(c + 4);

        if ((s & 1) != 0 && (s & ~(size_t)3) >= 16 && (s & ~(size_t)3) < (32u << 20))
            return c;
    }

    return NULL;
}

struct Summary { uint32_t inuse, freeb, holes_big, largest, largest_at, topsz, room, best; };

static Summary walk(bool print)
{
    Summary s;
    memset(&s, 0, sizeof(s));
    char *top = __malloc_av_[2];
    char *p = first_chunk();

    if (p == NULL || top == NULL)
        return s;

    unsigned chunks = 0;

    while (p < top && chunks < 400000)
    {
        size_t size = *(size_t *)(p + 4) & ~(size_t)3;

        if (size < 16 || p + size > top)
        {
            if (print)
                out("walk stops at %08x (size %u)", (unsigned)(uintptr_t)p, (unsigned)size);
            break;
        }

        char *next = p + size;
        bool inuse = (*(size_t *)(next + 4) & 1) != 0;
        chunks++;

        if (!inuse)
        {
            s.freeb += size;

            if (size > s.largest)
            {
                s.largest = size;
                s.largest_at = (uint32_t)(uintptr_t)p;
            }

            if (size >= 2598384 + 64)
                s.holes_big++;

            if (print && size >= SOCOM_HMAP_FREE)
            {
                run_report(p);
                out("F %08x %u", (unsigned)(uintptr_t)p, (unsigned)size);
            }
            else if (print)
                g_run_dust += size;
        }
        else
        {
            s.inuse += size;

            if (print)
            {
                run_add(p, size);

                if (size >= 0x10000)
                {
                    char a[48];
                    out("B %08x %u %s p%u", (unsigned)(uintptr_t)p, (unsigned)size, site_text(site_at(p), a, sizeof(a)), phase_at(p));
                }
            }
        }

        p = next;
    }

    if (print)
        run_report(top);

    s.topsz = *(size_t *)(top + 4) & ~(size_t)3;
    char *brk = (char *)sbrk(0);
    char *end = (char *)EndOfHeap();
    s.room = end > brk ? (uint32_t)(end - brk) : 0;
    s.best = s.largest > s.topsz + s.room ? s.largest : s.topsz + s.room;
    return s;
}

extern "C" void socom_hmap_summary(const char *label)
{
    g_quiet++;
    Summary s = walk(false);
    out("sum %s: in use %u free %u (largest hole %u at %08x, holes >= archive %u) top %u brk %08x room %u largest block %u | blocks %u allocs %u frees %u full %u sites %u",
        label, (unsigned)s.inuse, (unsigned)s.freeb, (unsigned)s.largest, (unsigned)s.largest_at, (unsigned)s.holes_big,
        (unsigned)s.topsz, (unsigned)(uintptr_t)sbrk(0), (unsigned)s.room, (unsigned)s.best, (unsigned)(g_nalloc - g_nfree),
        g_nalloc, g_nfree, g_full, g_nsites);
    g_quiet--;
}

extern "C" void socom_hmap_dump(const char *label)
{
    g_quiet++;
    extern char _end[];
    out("begin %s: image end %08x sbrk base %08x top %08x brk %08x heap end %08x", label, (unsigned)(uintptr_t)_end,
        (unsigned)(uintptr_t)__malloc_sbrk_base, (unsigned)(uintptr_t)__malloc_av_[2], (unsigned)(uintptr_t)sbrk(0),
        (unsigned)(uintptr_t)EndOfHeap());
    walk(true);
    g_quiet--;
    socom_hmap_summary(label);
}

/* ---- the wraps ----
 * malloc / calloc / realloc / memalign only note their caller (the tag of untagged blocks); the block table
 * and the event log are kept in newlib's reentrant entry points (_malloc_r, _free_r, _realloc_r, _memalign_r,
 * _calloc_r), so blocks newlib makes for itself (stdio buffers, ...) are seen too. Calls between those entry
 * points (memalign -> malloc, realloc -> malloc / free, calloc -> malloc) cross newlib's objects and are
 * wrapped as well: only the outermost one counts.
 * -DSOCOM_HMAP_LOG: every outermost request is logged as one short line ("@m <size> <ptr>", "@a <align>
 * <size> <ptr>", "@c <bytes> <ptr>", "@r <old> <size> <new>", "@f <ptr>", "@s <increment> <old brk>" for a
 * break move outside malloc), so the run can be replayed off-line through the same allocator. */
struct _reent;
extern "C" void *__real__malloc_r(struct _reent *r, size_t n);
extern "C" void __real__free_r(struct _reent *r, void *p);
extern "C" void *__real__realloc_r(struct _reent *r, void *p, size_t n);
extern "C" void *__real__memalign_r(struct _reent *r, size_t a, size_t n);
extern "C" void *__real__calloc_r(struct _reent *r, size_t a, size_t b);
extern "C" void *__real_sbrk(ptrdiff_t n);
static int g_rdepth;
static void *g_caller;
static unsigned g_big;

#ifdef SOCOM_HMAP_LOG
static char g_ev[64];
static void ev(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void ev(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(g_ev, sizeof(g_ev), fmt, ap);
    va_end(ap);
    sio_puts(g_ev);
}
#define EV(...) ev(__VA_ARGS__)
#else
#define EV(...) ((void)0)
#endif

static void big_before(const char *what, size_t n)
{
    char label[96];
    snprintf(label, sizeof(label), "before %s(%u) %s:%d #%u", what, (unsigned)n, g_file != NULL ? g_file : "?", g_line, g_big + 1);

    if (g_big < SOCOM_HMAP_MAPS)
        socom_hmap_dump(label);
    else
        socom_hmap_summary(label);
}

static void *big_after(void *p, size_t n)
{
    g_big++;
    out("big #%u: %u bytes -> %08x..%08x (brk %08x)", g_big, (unsigned)n, (unsigned)(uintptr_t)p, (unsigned)((uintptr_t)p + n),
        (unsigned)(uintptr_t)sbrk(0));
    return p;
}

/* every block of 256 KB or more made or freed, in order, with the phase: who holds the big buffers when */
static void big_event(char what, void *p, void *ra)
{
    if (p == NULL || g_quiet)
        return;

    unsigned size = *(uint32_t *)((char *)p - 4) & ~3u;

    if (size < 0x40000)
        return;

    char a[48];
    out("%c %08x %u phase %u %s", what, (unsigned)(uintptr_t)p, size, g_phase,
        what == '+' ? site_text(site_at((char *)p - 8), a, sizeof(a)) : (snprintf(a, sizeof(a), "from %08x", (unsigned)(uintptr_t)ra), a));
}

/* ra: the caller of newlib's entry point, the tag when no malloc / calloc / realloc / memalign call is under way
 * (newlib's own blocks: lc@) */
static void *tracked(void *p, void *ra)
{
    track(p, g_caller != NULL ? g_caller : ra, g_caller == NULL);
    big_event('+', p, NULL);
    return p;
}

extern "C" void *__wrap__malloc_r(struct _reent *r, size_t n)
{
    if (g_rdepth++ != 0 || g_quiet)
    {
        void *p = __real__malloc_r(r, n);
        g_rdepth--;
        return p;
    }

    bool b = false;

    if (n >= SOCOM_HMAP_BIG && g_depth > 0)
    {
        b = true;
        g_rdepth--;
        big_before("malloc", n);
        g_rdepth++;
    }

    void *p = __real__malloc_r(r, n);
    EV("@m %x %x", (unsigned)n, (unsigned)(uintptr_t)p);
    tracked(p, __builtin_return_address(0));
    g_rdepth--;
    return b ? big_after(p, n) : p;
}

extern "C" void *__wrap__memalign_r(struct _reent *r, size_t a, size_t n)
{
    if (g_rdepth++ != 0 || g_quiet)
    {
        void *p = __real__memalign_r(r, a, n);
        g_rdepth--;
        return p;
    }

    bool b = false;

    if (n >= SOCOM_HMAP_BIG && g_depth > 0)
    {
        b = true;
        g_rdepth--;
        big_before("memalign", n);
        g_rdepth++;
    }

    void *p = __real__memalign_r(r, a, n);
    EV("@a %x %x %x", (unsigned)a, (unsigned)n, (unsigned)(uintptr_t)p);
    tracked(p, __builtin_return_address(0));
    g_rdepth--;
    return b ? big_after(p, n) : p;
}

extern "C" void *__wrap__calloc_r(struct _reent *r, size_t a, size_t b)
{
    if (g_rdepth++ != 0 || g_quiet)
    {
        void *p = __real__calloc_r(r, a, b);
        g_rdepth--;
        return p;
    }

    void *p = __real__calloc_r(r, a, b);
    EV("@c %x %x", (unsigned)(a * b), (unsigned)(uintptr_t)p);
    tracked(p, __builtin_return_address(0));
    g_rdepth--;
    return p;
}

extern "C" void *__wrap__realloc_r(struct _reent *r, void *old, size_t n)
{
    if (g_rdepth++ != 0 || g_quiet)
    {
        void *p = __real__realloc_r(r, old, n);
        g_rdepth--;
        return p;
    }

    del(old);
    void *p = __real__realloc_r(r, old, n);
    EV("@r %x %x %x", (unsigned)(uintptr_t)old, (unsigned)n, (unsigned)(uintptr_t)p);
    tracked(p, __builtin_return_address(0));
    g_rdepth--;
    return p;
}

extern "C" void __wrap__free_r(struct _reent *r, void *p)
{
    if (g_rdepth++ != 0 || g_quiet || p == NULL)
    {
        __real__free_r(r, p);
        g_rdepth--;
        return;
    }

    del(p);
    big_event('-', p, g_caller != NULL ? g_caller : __builtin_return_address(0));
    __real__free_r(r, p);
    EV("@f %x", (unsigned)(uintptr_t)p);
    g_rdepth--;
}

extern "C" void *__wrap_sbrk(ptrdiff_t n)
{
    void *p = __real_sbrk(n);

    if (n != 0 && g_rdepth == 0)
        EV("@s %x %x", (unsigned)n, (unsigned)(uintptr_t)p);

    return p;
}

#define CALLER(call) void *sc = g_caller; if (sc == NULL) g_caller = __builtin_return_address(0); auto r = call; g_caller = sc; return r
extern "C" void *__wrap_malloc(size_t n) { CALLER(__real_malloc(n)); }
extern "C" void *__wrap_calloc(size_t a, size_t b) { CALLER(__real_calloc(a, b)); }
extern "C" void *__wrap_realloc(void *p, size_t n) { CALLER(__real_realloc(p, n)); }
extern "C" void *__wrap_memalign(size_t a, size_t n) { CALLER(__real_memalign(a, n)); }
extern "C" void __real_free(void *p);
extern "C" void __wrap_free(void *p) { void *sc = g_caller; if (sc == NULL) g_caller = __builtin_return_address(0); __real_free(p); g_caller = sc; }
extern "C" void *__wrap__Znwj(unsigned int n) { void *s = g_newra; g_newra = __builtin_return_address(0); void *r = __real__Znwj(n); g_newra = s; return r; }
extern "C" void *__wrap__Znaj(unsigned int n) { void *s = g_newra; g_newra = __builtin_return_address(0); void *r = __real__Znaj(n); g_newra = s; return r; }

/* who makes newlib's own long-lived blocks: the Bigint cache (_Balloc keeps every Bigint it makes on a
 * per-size free list for ever: the first float printed or parsed with many digits makes them) and the
 * pthread mutexes made on first lock (libstdc++ / newlib locks) */
static void *g_vsn_ra, *g_strtod_ra;
extern "C" void *__real__Balloc(struct _reent *r, int k);
extern "C" void *__wrap__Balloc(struct _reent *r, int k)
{
    unsigned n0 = g_nalloc;
    void *b = __real__Balloc(r, k);

    if (g_nalloc != n0 && !g_quiet)
        out("libc: _Balloc(%d) made a block (from %08x; in vsnprintf from %08x; strtod from %08x) phase %u", k,
            (unsigned)(uintptr_t)__builtin_return_address(0), (unsigned)(uintptr_t)g_vsn_ra, (unsigned)(uintptr_t)g_strtod_ra, g_phase);

    return b;
}
extern "C" int __real_vsnprintf(char *s, size_t n, const char *f, va_list ap);
extern "C" int __wrap_vsnprintf(char *s, size_t n, const char *f, va_list ap)
{
    void *o = g_vsn_ra;
    g_vsn_ra = __builtin_return_address(0);
    int r = __real_vsnprintf(s, n, f, ap);
    g_vsn_ra = o;
    return r;
}
extern "C" double __real__strtod_r(struct _reent *r, const char *s, char **e);
extern "C" double __wrap__strtod_r(struct _reent *r, const char *s, char **e)
{
    void *o = g_strtod_ra;
    g_strtod_ra = __builtin_return_address(0);
    double d = __real__strtod_r(r, s, e);
    g_strtod_ra = o;
    return d;
}
extern "C" int __real_pthread_mutex_lock(void *m);
extern "C" int __wrap_pthread_mutex_lock(void *m)
{
    unsigned n0 = g_nalloc;
    int r = __real_pthread_mutex_lock(m);

    if (g_nalloc != n0 && !g_quiet)
        out("libc: pthread_mutex_lock(%08x) made the mutex (from %08x) phase %u", (unsigned)(uintptr_t)m,
            (unsigned)(uintptr_t)__builtin_return_address(0), g_phase);

    return r;
}
extern "C" int __real_pthread_mutex_init(void *m, const void *a);
extern "C" int __wrap_pthread_mutex_init(void *m, const void *a)
{
    unsigned n0 = g_nalloc;
    int r = __real_pthread_mutex_init(m, a);

    if (g_nalloc != n0 && !g_quiet && g_phase > 0)
        out("libc: pthread_mutex_init(%08x) made a mutex (from %08x) phase %u", (unsigned)(uintptr_t)m,
            (unsigned)(uintptr_t)__builtin_return_address(0), g_phase);

    return r;
}

#define TAGGED(ret, name, args, call) \
    extern "C" ret __wrap_##name args { const char *sf = g_file; int sl = g_line; void *sn = g_newra; g_file = f ? f : "?"; g_line = l; \
        if (l != 0) g_newra = NULL; g_depth++; ret r = call; g_depth--; g_file = sf; g_line = sl; g_newra = sn; return r; }

TAGGED(void *, _Z7_mallocjPKci, (size_t n, const char *f, int l), __real__Z7_mallocjPKci(n, f, l))
TAGGED(void *, _Z7_callocjjPKci, (size_t a, size_t b, const char *f, int l), __real__Z7_callocjjPKci(a, b, f, l))
TAGGED(void *, _Z9_memalignjjPKci, (size_t a, size_t n, const char *f, int l), __real__Z9_memalignjjPKci(a, n, f, l))
TAGGED(char *, _Z7_strdupPKcS0_i, (const char *s, const char *f, int l), __real__Z7_strdupPKcS0_i(s, f, l))
TAGGED(void *, _Z4_newjPKci, (size_t n, const char *f, int l), __real__Z4_newjPKci(n, f, l))
TAGGED(void *, _Z8_new_vecjPKci, (size_t n, const char *f, int l), __real__Z8_new_vecjPKci(n, f, l))

/* ---- the test-only boot allocation ---- */
#ifdef SOCOM_HMAP_XSIZE
static void extra_alloc(const char *where)
{
    void *first = NULL, *last = NULL;

    for (int i = 0; i < SOCOM_HMAP_XCOUNT; i++)
    {
        last = malloc(SOCOM_HMAP_XSIZE); /* kept for ever, as a static object's would be */

        if (i == 0)
            first = last;
    }

    out("extra boot allocation (%s): %d x %u bytes, first %08x last %08x", where, SOCOM_HMAP_XCOUNT, (unsigned)SOCOM_HMAP_XSIZE,
        (unsigned)(uintptr_t)first, (unsigned)(uintptr_t)last);
}
#if SOCOM_HMAP_XAT == 0
__attribute__((constructor(102))) static void extra_early() { extra_alloc("before the global constructors"); }
#else
class CSaveManager;
extern "C" void __real__ZN11CSaveModuleC2EPKcP12CSaveManager(void *self, const char *name, CSaveManager *m);
extern "C" void __wrap__ZN11CSaveModuleC2EPKcP12CSaveManager(void *self, const char *name, CSaveManager *m)
{
    __real__ZN11CSaveModuleC2EPKcP12CSaveManager(self, name, m);
    static bool done;

    if (!done && name != NULL && strcmp(name, "CMission") == 0)
    {
        done = true;
        extra_alloc("after CSaveModule(\"CMission\")");
    }
}
#endif
#endif
