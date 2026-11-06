/* Functional port lane: the Metrowerks runtime entry points the game calls.
 * Not Metrowerks code; nothing here is evidence for the matching lane. */
#include <mwUtils.h>

void socom_port_trace(const char *fmt, ...);

/* The original mwInit (0x144890) runs __initialize_cpp_rts: the static initialisers
 * (.ctors-style table at 0x471260..0x4714b0) and the exception tables. The ps2sdk
 * crt0 has already run every global constructor through _init before main, and the
 * port builds with -fno-exceptions, so nothing is left to do. */
void mwInit(void)
{
    socom_port_trace("mwInit: C++ static initialisation already done by crt0");
}
