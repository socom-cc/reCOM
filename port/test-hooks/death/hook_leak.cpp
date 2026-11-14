/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): leak finder. While armed (socom_hleak_armed = 1,
 * set by a test edit) every heap block handed out by malloc/calloc/realloc/memalign is
 * remembered with its size and a tag (the _malloc/_calloc/_memalign/_strdup/_new/_new_vec
 * file:line when it came through those, else the caller's address); free forgets it.
 * socom_hleak_dump() traces the 48 biggest groups of blocks still alive. */
#include <stdint.h>
#include <stddef.h>

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

extern "C" int socom_hleak_armed;
int socom_hleak_armed;
#ifndef SOCOM_HLEAK_MIN
#define SOCOM_HLEAK_MIN 256 /* smallest block tracked (-DSOCOM_HLEAK_MIN=1: all) */
#endif

struct Entry { uintptr_t p; uint32_t size; uintptr_t tag; uint32_t line; };
#ifndef SOCOM_HLEAK_SLOTS
#define SOCOM_HLEAK_SLOTS 65536 /* table size (power of two) */
#endif
#define SLOTS SOCOM_HLEAK_SLOTS
static Entry g_tab[SLOTS];
static int g_full;
static const char *g_file;
static int g_line;
static int g_depth;
static void *g_newra;
extern "C" void *__real__Znwj(unsigned int n);
extern "C" void *__real__Znaj(unsigned int n);
extern "C" void *__wrap__Znwj(unsigned int n) { void *s = g_newra; g_newra = __builtin_return_address(0); void *r = __real__Znwj(n); g_newra = s; return r; }
extern "C" void *__wrap__Znaj(unsigned int n) { void *s = g_newra; g_newra = __builtin_return_address(0); void *r = __real__Znaj(n); g_newra = s; return r; }

static unsigned slot(uintptr_t p) { return (unsigned)((p >> 3) * 2654435761u) & (SLOTS - 1); }

static void add(void *q, size_t n, uintptr_t tag, uint32_t line)
{
	if (!socom_hleak_armed || q == NULL || n < SOCOM_HLEAK_MIN)
		return;

	uintptr_t p = (uintptr_t)q;

	for (unsigned i = slot(p), k = 0; k < 4096; i = (i + 1) & (SLOTS - 1), k++)
	{
		if (g_tab[i].p == 0 || g_tab[i].p == p)
		{
			g_tab[i].p = p;
			g_tab[i].size = (uint32_t)n;
			g_tab[i].tag = tag;
			g_tab[i].line = line;
			return;
		}
	}

	g_full++;
}

static void del(void *q)
{
	if (q == NULL)
		return;

	uintptr_t p = (uintptr_t)q;
	unsigned i = slot(p);

	for (unsigned k = 0; k < SLOTS && g_tab[i].p != 0; i = (i + 1) & (SLOTS - 1), k++)
	{
		if (g_tab[i].p == p)
			break;
	}

	if (g_tab[i].p != p)
		return;

	unsigned j = i;
	g_tab[j].p = 0;

	for (unsigned k = (j + 1) & (SLOTS - 1); g_tab[k].p != 0; k = (k + 1) & (SLOTS - 1))
	{
		unsigned h = slot(g_tab[k].p);
		bool move = (k > j) ? (h <= j || h > k) : (h <= j && h > k);

		if (move)
		{
			g_tab[j] = g_tab[k];
			g_tab[k].p = 0;
			j = k;
		}
	}
}

static void *track(void *q, size_t n, void *ra)
{
	if (g_depth == 0)
		add(q, n, (uintptr_t)ra, 0);
	else if (g_line == 0 && g_newra != NULL)
		add(q, n, (uintptr_t)g_newra, 0);
	else
		add(q, n, (uintptr_t)g_file, (uint32_t)g_line);

	return q;
}

extern "C" void *socom_hleak_watch; void *socom_hleak_watch;
extern "C" void __wrap_free(void *p) { if (p != NULL && p == socom_hleak_watch) SOCOM_PORT_TRACE("HLEAK: watched %p freed from %p", p, __builtin_return_address(0)); del(p); __real_free(p); }
extern "C" void *__wrap_malloc(size_t n) { return track(__real_malloc(n), n, __builtin_return_address(0)); }
extern "C" void *__wrap_calloc(size_t a, size_t b) { return track(__real_calloc(a, b), a * b, __builtin_return_address(0)); }
extern "C" void *__wrap_realloc(void *p, size_t n) { del(p); return track(__real_realloc(p, n), n, __builtin_return_address(0)); }
extern "C" void *__wrap_memalign(size_t a, size_t n) { return track(__real_memalign(a, n), n, __builtin_return_address(0)); }

#define TAGGED(ret, name, args, call) \
	extern "C" ret __wrap_##name args { const char *sf = g_file; int sl = g_line; g_file = f ? f : "?"; g_line = l; g_depth++; ret r = call; g_depth--; g_file = sf; g_line = sl; return r; }

TAGGED(void *, _Z7_mallocjPKci, (size_t n, const char *f, int l), __real__Z7_mallocjPKci(n, f, l))
TAGGED(void *, _Z7_callocjjPKci, (size_t a, size_t b, const char *f, int l), __real__Z7_callocjjPKci(a, b, f, l))
TAGGED(void *, _Z9_memalignjjPKci, (size_t a, size_t n, const char *f, int l), __real__Z9_memalignjjPKci(a, n, f, l))
TAGGED(char *, _Z7_strdupPKcS0_i, (const char *s, const char *f, int l), __real__Z7_strdupPKcS0_i(s, f, l))
TAGGED(void *, _Z4_newjPKci, (size_t n, const char *f, int l), __real__Z4_newjPKci(n, f, l))
TAGGED(void *, _Z8_new_vecjPKci, (size_t n, const char *f, int l), __real__Z8_new_vecjPKci(n, f, l))

struct Group { uintptr_t tag; uint32_t line; uint32_t bytes; uint32_t count; uintptr_t ex[3]; };

extern "C" void socom_hleak_dump(const char *when)
{
	static Group g[512];
	int ng = 0;
	uint32_t total = 0, blocks = 0, lost = 0;

	for (unsigned i = 0; i < SLOTS; i++)
	{
		if (g_tab[i].p == 0)
			continue;

		total += g_tab[i].size;
		blocks++;
		int k;

		for (k = 0; k < ng; k++)
		{
			if (g[k].tag == g_tab[i].tag && g[k].line == g_tab[i].line)
				break;
		}

		if (k == ng)
		{
			if (ng == 512)
			{
				lost += g_tab[i].size;
				continue;
			}

			g[ng].tag = g_tab[i].tag;
			g[ng].line = g_tab[i].line;
			g[ng].bytes = 0;
			g[ng].count = 0;
			ng++;
		}

		if (g[k].count < 3) g[k].ex[g[k].count] = g_tab[i].p;
		g[k].bytes += g_tab[i].size;
		g[k].count++;
	}

	SOCOM_PORT_TRACE("HLEAK: %s: %u bytes in %u blocks alive since arming (%d groups, %u bytes ungrouped, %d untracked)", when, total, blocks, ng, lost, g_full);

	/* where they are: blocks and bytes per MB of the heap */
	static uint32_t mb_blocks[32], mb_bytes[32];

	for (int m = 0; m < 32; m++) mb_blocks[m] = mb_bytes[m] = 0;

	for (unsigned i = 0; i < SLOTS; i++)
	{
		if (g_tab[i].p != 0 && (g_tab[i].p >> 20) < 32)
		{
			mb_blocks[g_tab[i].p >> 20]++;
			mb_bytes[g_tab[i].p >> 20] += g_tab[i].size;
		}
	}

	for (int m = 0; m < 32; m++)
	{
		if (mb_blocks[m] != 0)
			SOCOM_PORT_TRACE("HLEAK: MB 0x%02x: %u blocks %u bytes", m, mb_blocks[m], mb_bytes[m]);
	}

	for (int n = 0; n < 48 && n < ng; n++)
	{
		int best = n;

		for (int k = n + 1; k < ng; k++)
		{
			if (g[k].bytes > g[best].bytes)
				best = k;
		}

		Group t = g[n]; g[n] = g[best]; g[best] = t;

		if (g[n].line != 0)
			SOCOM_PORT_TRACE("HLEAK: %8u bytes %5u blocks %s:%u", g[n].bytes, g[n].count, (const char *)g[n].tag, g[n].line);
		else
			SOCOM_PORT_TRACE("HLEAK: %8u bytes %5u blocks from %p (e.g. %p %p %p)", g[n].bytes, g[n].count, (void *)g[n].tag, (void *)g[n].ex[0], (void *)g[n].ex[1], (void *)g[n].ex[2]);
	}
}

extern "C" int socom_hleak_has(void *q)
{
	uintptr_t p = (uintptr_t)q;

	for (unsigned i = slot(p), k = 0; k < SLOTS && g_tab[i].p != 0; i = (i + 1) & (SLOTS - 1), k++)
	{
		if (g_tab[i].p == p)
			return (int)g_tab[i].size;
	}

	return 0;
}
/* the tag of a tracked block (file:line, or the caller with line 0); 0 when it is not tracked */
extern "C" int socom_hleak_tag(void *q, uintptr_t *tag, uint32_t *line)
{
	uintptr_t p = (uintptr_t)q;

	for (unsigned i = slot(p), k = 0; k < SLOTS && g_tab[i].p != 0; i = (i + 1) & (SLOTS - 1), k++)
	{
		if (g_tab[i].p == p)
		{
			*tag = g_tab[i].tag;
			*line = g_tab[i].line;
			return (int)g_tab[i].size;
		}
	}

	return 0;
}