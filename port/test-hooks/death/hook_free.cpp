/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): double-free finder. While armed
 * (socom_hfree_armed, set by a test edit) every pointer given to free / operator delete /
 * _free is remembered until an allocator hands it out again; a second release of a
 * remembered pointer is traced with its caller (the release still happens). */
#include <stdint.h>
#include <stddef.h>
#include <unistd.h>

extern "C" void __real_free(void *p);
extern "C" void *__real_malloc(size_t n);
extern "C" void *__real_calloc(size_t a, size_t b);
extern "C" void *__real_realloc(void *p, size_t n);
extern "C" void *__real_memalign(size_t a, size_t n);
extern "C" void __real__ZdlPv(void *p);
extern "C" void __real__ZdlPvj(void *p, unsigned int n);
extern "C" void __real__ZdaPv(void *p);
extern "C" void *__real__Znwj(unsigned int n);
extern "C" void *__real__Znaj(unsigned int n);
extern "C" void __real__Z5_freePvPKci(void *p, const char *file, int line);

extern "C" int socom_hfree_armed;
int socom_hfree_armed;
static int g_reports;
static int g_nested;
static void *g_del_ra; static const char *g_free_file; static int g_free_line; static void *g_free_ra;

static int freed_chunk(void *p)
{
	uintptr_t a = (uintptr_t)p;
	uint32_t size = ((uint32_t *)p)[-1] & ~3u;

	if (size < 8 || size > 0x2000000)
		return 2;

	uint32_t next = *(uint32_t *)(a - 8 + size + 4);
	return (next & 1) == 0 ? 3 : 0;
}

#define SLOTS 262144
static uintptr_t g_set[SLOTS];

static unsigned slot(uintptr_t p) { return (unsigned)((p >> 2) * 2654435761u) & (SLOTS - 1); }

static int find(uintptr_t p)
{
	for (unsigned i = slot(p), n = 0; n < SLOTS; i = (i + 1) & (SLOTS - 1), n++)
	{
		if (g_set[i] == p)
			return (int)i;

		if (g_set[i] == 0)
			return -1;
	}

	return -1;
}

static void forget(void *q)
{
	/* backward-shift delete keeps the probe chains intact */
	int i = find((uintptr_t)q);

	if (i < 0)
		return;

	unsigned j = (unsigned)i;
	g_set[j] = 0;

	for (unsigned k = (j + 1) & (SLOTS - 1); g_set[k] != 0; k = (k + 1) & (SLOTS - 1))
	{
		uintptr_t v = g_set[k];
		unsigned h = slot(v);
		bool move = (k > j) ? (h <= j || h > k) : (h <= j && h > k);

		if (move)
		{
			g_set[j] = v;
			g_set[k] = 0;
			j = k;
		}
	}
}

static int wild(void *p, void *ra, const char *what)
{
	uintptr_t a = (uintptr_t)p;

	if (p == NULL || (a >= 0x100000 && a < (uintptr_t)sbrk(0)))
		return 0;

	if (g_reports++ < 100)
		SOCOM_PORT_TRACE("HFREE: WILD %s %p from %p (skipped)", what, p, ra);

	return 1;
}

static void released(void *p, void *ra, const char *what)
{
	if (!socom_hfree_armed || p == NULL || g_nested)
		return;

	uintptr_t a = (uintptr_t)p;

	if (find(a) >= 0)
	{
		if (g_reports++ < 100)
			SOCOM_PORT_TRACE("HFREE: DOUBLE %s %p from %p", what, p, ra);

		return;
	}

	for (unsigned i = slot(a), n = 0; n < SLOTS; i = (i + 1) & (SLOTS - 1), n++)
	{
		if (g_set[i] == 0)
		{
			g_set[i] = a;
			return;
		}
	}
}

static void *got(void *p)
{
	if (socom_hfree_armed && p != NULL)
		forget(p);

	return p;
}

extern "C" void __wrap_free(void *p)
{
	if (wild(p, __builtin_return_address(0), "free"))
		return;

	if (socom_hfree_armed && p != NULL)
	{
		int k = freed_chunk(p);

		if (k != 0)
		{
			if (g_reports++ < 100)
				SOCOM_PORT_TRACE("HFREE: FREED-CHUNK %p kind %d free-ra %p last _free %s:%d ra %p last delete ra %p (skipped)", p, k, __builtin_return_address(0), g_free_file ? g_free_file : "-", g_free_line, g_free_ra, g_del_ra);

			g_free_file = NULL; g_del_ra = NULL;
			return;
		}
	}

	g_free_file = NULL; g_del_ra = NULL;
	released(p, __builtin_return_address(0), "free");
	__real_free(p);
}
extern "C" void *__wrap_malloc(size_t n) { return got(__real_malloc(n)); }
extern "C" void *__wrap_calloc(size_t a, size_t b) { return got(__real_calloc(a, b)); }
extern "C" void *__wrap_realloc(void *p, size_t n) { if (socom_hfree_armed && p) forget(p); return got(__real_realloc(p, n)); }
extern "C" void *__wrap_memalign(size_t a, size_t n) { return got(__real_memalign(a, n)); }
extern "C" void *__wrap__Znwj(unsigned int n) { g_nested++; void *p = __real__Znwj(n); g_nested--; return got(p); }
extern "C" void *__wrap__Znaj(unsigned int n) { g_nested++; void *p = __real__Znaj(n); g_nested--; return got(p); }
extern "C" void __wrap__ZdlPv(void *p) { g_del_ra = __builtin_return_address(0); if (wild(p, __builtin_return_address(0), "delete")) return; released(p, __builtin_return_address(0), "delete"); g_nested++; __real__ZdlPv(p); g_nested--; }
extern "C" void __wrap__ZdaPv(void *p) { if (wild(p, __builtin_return_address(0), "delete[]")) return; released(p, __builtin_return_address(0), "delete[]"); g_nested++; __real__ZdaPv(p); g_nested--; }
extern "C" void __wrap__ZdlPvj(void *p, unsigned int n) { g_del_ra = __builtin_return_address(0); if (wild(p, __builtin_return_address(0), "delete(n)")) return; released(p, __builtin_return_address(0), "delete(n)"); g_nested++; __real__ZdlPvj(p, n); g_nested--; }
extern "C" void __wrap__Z5_freePvPKci(void *p, const char *file, int line)
{
	if (wild(p, __builtin_return_address(0), file ? file : "_free"))
		return;

	if (socom_hfree_armed && p != NULL && !g_nested && find((uintptr_t)p) >= 0 && g_reports++ < 100)
		SOCOM_PORT_TRACE("HFREE: DOUBLE _free %p %s:%d from %p", p, file ? file : "?", line, __builtin_return_address(0));
	else
		released(p, __builtin_return_address(0), "_free");

	g_free_file = file; g_free_line = line; g_free_ra = __builtin_return_address(0);
	g_nested++;
	__real__Z5_freePvPKci(p, file, line);
	g_nested--;
}
