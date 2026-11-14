/* Functional port lane: stand-in for the Sony libdev debug font (sceDevFont, linked into
 * socom.elf at 0x151bc0 with its font image). ps2sdk has no equivalent. Not Sony code;
 * nothing here is evidence for the matching lane.
 *
 * The game draws only one thing with it: CTTY, the developer terminal, which holds text
 * only after a failed zVid_Assert. The stand-in draws nothing: it writes a DMA end tag
 * (qwc 0) so the GIF send of the packet transfers nothing, and sends the text to the port
 * log instead (once per distinct line, so a terminal redrawn every frame is not repeated). */
#include <string.h>

void socom_port_trace(const char *fmt, ...);

void *sceDevFont(void *packet, int x, int y, int z, char *str, int ctxt)
{
    static char last[80];
    unsigned int *tag = (unsigned int *)packet;

    (void)z;
    (void)ctxt;
    tag[0] = 0x70000000; /* DMAtag end, qwc 0 */
    tag[1] = 0;
    tag[2] = 0;
    tag[3] = 0;
    if (strncmp(last, str, sizeof(last) - 1) != 0) {
        strncpy(last, str, sizeof(last) - 1);
        last[sizeof(last) - 1] = 0;
        socom_port_trace("TTY (%d,%d): %s", x >> 4, y >> 4, str);
    }
    return tag + 4;
}
