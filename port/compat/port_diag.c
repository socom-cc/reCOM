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

void socom_port_trace(const char *fmt, ...)
{
    char line[256];
    int n;
    va_list ap;
    n = snprintf(line, sizeof(line), "[socom-port] ");
    va_start(ap, fmt);
    n += vsnprintf(line + n, sizeof(line) - n, fmt, ap);
    va_end(ap);
    if (n < (int)sizeof(line) - 32) {
        void *probe = malloc(16);
        snprintf(line + n, sizeof(line) - n, " [brk %p%s]", sbrk(0), probe ? "" : " HEAP BROKEN");
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
