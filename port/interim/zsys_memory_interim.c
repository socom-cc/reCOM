/* Functional port lane, INTERIM: stand-ins for the game allocator while its src/
 * bodies are not written.
 *
 * The allocator lives in src/gamez/zSystem/zsys_memory.cpp, which is held for the
 * stage-4 amendment wave (no edits until it lands), and _delete__FPvPCci has no
 * owning unit yet. Every global constructor and most of start-up allocate through
 * these functions, so without them the port cannot pass its global constructors.
 *
 * port/CMakeLists.txt links each function below with `-Wl,--wrap=<symbol>` only
 * while its src/ definition is still an empty skeleton stub (or, for _delete, absent),
 * so a written body automatically replaces its stand-in. Delete this file and that
 * CMake block once zsys_memory.cpp and _delete have bodies.
 *
 * Behaviour is read from socom.elf (addresses below): each wraps the C library call
 * in DIntr/EIntr and asserts through zVid_Assert(size == 0 || p != NULL, 0x800000ff,
 * ...). The stand-ins stop with a trace instead of the assert. Not game code and not
 * evidence for the matching lane. */
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
#include <kernel.h>
#include <unistd.h>

void socom_port_stop(const char *what);
void socom_port_trace(const char *fmt, ...);

static void *checked_at(void *p, unsigned int size, const char *file, int line, void *caller)
{
    if (size >= 0x100000)
        socom_port_trace("interim allocator: large block %u bytes -> %p (%s:%d, called from %p)", size, p, file ? file : "?", line, caller);
    if (size != 0 && p == NULL) {
        struct mallinfo mi = mallinfo();
        socom_port_trace("interim allocator: %u bytes failed (%s:%d, called from %p); heap arena %d in use %d free %d, brk %p, heap end %p",
                         size, file ? file : "?", line, caller, mi.arena, mi.uordblks, mi.fordblks, sbrk(0), EndOfHeap());
        socom_port_stop("interim allocator: out of memory");
    }
    return p;
}
#define checked(p, size) checked_at((p), (size), file, line, __builtin_return_address(0))

/* _new__FUiPCci 0x2f4830 */
void *__wrap__Z4_newjPKci(unsigned int size, const char *file, int line)
{
    void *p;
    DIntr();
    p = malloc(size);
    EIntr();
    return checked(p, size);
}

/* _new_vec__FUiPCci 0x2f4780 */
void *__wrap__Z8_new_vecjPKci(unsigned int size, const char *file, int line)
{
    void *p;
    DIntr();
    p = malloc(size);
    EIntr();
    return checked(p, size);
}

/* _malloc__FUiPCci 0x2f4710 */
void *__wrap__Z7_mallocjPKci(unsigned int size, const char *file, int line)
{
    void *p;
    DIntr();
    p = malloc(size);
    EIntr();
    return checked(p, size);
}

/* _calloc__FUiUiPCci 0x2f45b0: malloc(count * size), then memset outside DIntr. */
void *__wrap__Z7_callocjjPKci(unsigned int count, unsigned int size, const char *file, int line)
{
    unsigned int total = count * size;
    void *p;
    DIntr();
    p = malloc(total);
    EIntr();
    memset(p, 0, total);
    return checked(p, total);
}

/* _realloc__FPvUiPCci 0x2f4630 */
void *__wrap__Z8_reallocPvjPKci(void *ptr, unsigned int size, const char *file, int line)
{
    void *p;
    DIntr();
    p = realloc(ptr, size);
    EIntr();
    return checked(p, size);
}

/* _memalign__FUiUiPCci 0x2f46a0 */
void *__wrap__Z9_memalignjjPKci(unsigned int alignment, unsigned int size, const char *file, int line)
{
    void *p;
    DIntr();
    p = memalign(alignment, size);
    EIntr();
    return checked(p, size);
}

/* _strdup__FPCcPCci 0x2f4520: strlen, then malloc + strcpy inside DIntr. */
char *__wrap__Z7_strdupPKcS0_i(const char *str, const char *file, int line)
{
    unsigned int size = strlen(str) + 1;
    char *p;
    DIntr();
    p = malloc(size);
    strcpy(p, str);
    EIntr();
    return checked(p, size);
}

/* _delete_vec__FPvPCci 0x2f47f0 */
void __wrap__Z11_delete_vecPvPKci(void *ptr, const char *file, int line)
{
    if (ptr != NULL) {
        DIntr();
        free(ptr);
        EIntr();
    }
}

/* _delete__FPvPCci 0x2f48a0 (no owning unit yet) */
void __wrap__Z7_deletePvPKci(void *ptr, const char *file, int line)
{
    DIntr();
    free(ptr);
    EIntr();
}
