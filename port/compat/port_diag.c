/* Functional port lane: boot diagnostics. Traces go to the EE SIO port, which PCSX2
 * logs at once and which keeps working while the IOP reboots; the game's own printf
 * goes through stdout (IOP tty), made unbuffered here so lines are not lost when the
 * boot stops. Not game code and not evidence for the matching lane. */
#include <stdarg.h>
#include <stdio.h>
#include <kernel.h>
#include <sio.h>
#include <unistd.h>
#include <stdlib.h>
#include <malloc.h>

void socom_port_trace(const char *fmt, ...)
{
    char line[256];
    int n;
    va_list ap;
    n = snprintf(line, sizeof(line), "[socom-port] ");
    va_start(ap, fmt);
    n += vsnprintf(line + n, sizeof(line) - n, fmt, ap);
    va_end(ap);
    if (n < (int)sizeof(line) - 40) {
        void *probe = malloc(16);
        struct mallinfo mi = mallinfo(); /* in use: the heap the game holds (brk is only the high-water mark) */
        snprintf(line + n, sizeof(line) - n, " [brk %p use %u%s]", sbrk(0), (unsigned int)mi.uordblks, probe ? "" : " HEAP BROKEN");
        free(probe);
    }
    sio_puts(line);
}

/* Runs before every unprioritised global constructor (all of the game's). */
__attribute__((constructor(101))) static void socom_port_ctors_begin(void)
{
    extern char _end[];
    socom_port_trace("M1: global constructors start (end %p, brk %p, heap end %p)", (void *)_end, sbrk(0), EndOfHeap());
    setvbuf(stdout, NULL, _IONBF, 0);
}

/* src/ is compiled with -fsanitize=return: a non-void function that falls off its
 * end (in practice an empty skeleton stub) calls this instead of running into the
 * next function. It names the stub by file and line, then stops the thread. */
struct socom_ubsan_location {
    const char *file;
    unsigned int line;
    unsigned int column;
};

void __ubsan_handle_missing_return(struct socom_ubsan_location *loc)
{
    socom_port_trace("STOP: non-void stub returned no value: %s:%u", loc->file, loc->line);
    for (;;)
        SleepThread();
}

void socom_port_stop(const char *what)
{
    socom_port_trace("STOP: %s", what);
    for (;;)
        SleepThread();
}

/* CPU exceptions (address errors, TLB misses, bus errors, reserved instructions, traps)
 * are reported once on EE SIO with the registers a crash pc can be mapped from
 * (addr2line on the port ELF), plus the .text words found on the stack as a rough call
 * chain; then the thread stops. Installed before the global constructors. */
#include <ee_debug.h>

static void socom_port_hex(const char *tag, u32 v)
{
    char line[48];
    snprintf(line, sizeof(line), " %s=%08x", tag, (unsigned int)v);
    sio_putsn(line);
}

static int socom_port_exception(EE_RegFrame *f)
{
    extern char _ftext[], _etext[];
    u32 *sp = (u32 *)f->sp[0];
    int i, n = 0;
    sio_putsn("[socom-port] STOP: CPU exception");
    socom_port_hex("cause", (f->cause >> 2) & 0x1f);
    socom_port_hex("epc", f->epc);
    socom_port_hex("ra", f->ra[0]);
    socom_port_hex("sp", f->sp[0]);
    socom_port_hex("badvaddr", f->badvaddr);
    socom_port_hex("a0", f->a0[0]);
    socom_port_hex("v0", f->v0[0]);
    sio_puts("");
    sio_putsn("[socom-port] stack text words:");
    for (i = 0; i < 512 && n < 24; i++) {
        u32 w = sp[i];
        if (w >= (u32)_ftext && w < (u32)_etext && (w & 3) == 0) {
            socom_port_hex("", w);
            n++;
        }
    }
    sio_puts("");
    for (;;)
        ;
    return 0;
}

__attribute__((constructor(101))) static void socom_port_install_exceptions(void)
{
    static const int causes[] = {1, 2, 3, 4, 5, 6, 7, 10, 12, 13};
    unsigned int i;
    ee_dbg_install(1);
    for (i = 0; i < sizeof(causes) / sizeof(causes[0]); i++)
        ee_dbg_set_level1_handler(causes[i], socom_port_exception);
}
