/* Port compatibility: the Sony EE libpad calls the game makes (scePadXxx, declared in
 * compat/include/libpad.h) as thin wrappers over ps2sdk's libpad (padXxx). Both talk to
 * the pad driver the boot glue loads from the disc (SIO2MAN.IRX, PADMAN.IRX); ps2sdk's
 * libpad binds the same RPC servers (0x80000100/0x80000101) the game's libpad does
 * (scePadInit 0x16fdf0). The read data layout (rdata[0] status, [1] mode, [2..3] buttons
 * active low, [4..7] sticks) is the driver's and passes through unchanged.
 *
 * Test hook (off by default, never in the default build): configure a scratch build with
 * -DSOCOM_PORT_FAKE_PAD=<read>:<BUTTON>[,<read>:<BUTTON>...] (port/CMakeLists.txt) and
 * port 0 is a synthesized, always-stable analog pad that holds BUTTON down for three
 * reads starting at the given read count (CPad::Tick reads every other frame). Buttons:
 * START SELECT UP DOWN LEFT RIGHT CROSS CIRCLE SQUARE TRIANGLE L1 L2 R1 R2. A stick term
 * <read>:<AXIS>=<value>[+<reads>] holds an axis (LX LY RX RY, raw 0..255 decimal, 128 is
 * centred; LY=0 is the left stick fully up) for <reads> reads (default 3) from <read>;
 * otherwise the sticks stay centred. Held buttons read full pressure (255) unless a term
 * <read>:<BUTTON>P=<value>[+<reads>] (R1P, CROSSP, ...) gives another value. */
#include <libpad.h> /* compat: the Sony declarations */
#include <string.h>

void socom_port_trace(const char *fmt, ...);

/* ps2sdk libpad (its libpad.h is shadowed by the compat one) */
struct padButtonStatus;
extern int padInit(int mode);
extern int padEnd(void);
extern int padPortOpen(int port, int slot, void *padArea);
extern int padPortClose(int port, int slot);
extern unsigned char padRead(int port, int slot, struct padButtonStatus *data);
extern int padGetState(int port, int slot);
extern unsigned char padGetReqState(int port, int slot);
extern int padInfoMode(int port, int slot, int infoMode, int index);
extern int padSetMainMode(int port, int slot, int mode, int lock);
extern int padInfoPressMode(int port, int slot);
extern int padEnterPressMode(int port, int slot);
extern unsigned char padInfoAct(int port, int slot, int actuator, int cmd);
extern int padSetActAlign(int port, int slot, const char actAlign[6]);
extern int padSetActDirect(int port, int slot, const char actAlign[6]);

#ifdef SOCOM_PORT_FAKE_PAD
#define SOCOM_FAKE_STR(...) #__VA_ARGS__
#define SOCOM_FAKE_XSTR(...) SOCOM_FAKE_STR(__VA_ARGS__)

static const char socom_fake_script[] = SOCOM_FAKE_XSTR(SOCOM_PORT_FAKE_PAD);
static unsigned int socom_fake_reads;

static const struct
{
    const char *name;
    unsigned short bit; /* the button's bit in the active-low rdata[2] << 8 | rdata[3] */
} socom_fake_buttons[] =
{
    { "SELECT", 0x0100 }, { "L3", 0x0200 }, { "R3", 0x0400 }, { "START", 0x0800 }, { "UP", 0x1000 }, { "RIGHT", 0x2000 },
    { "DOWN", 0x4000 }, { "LEFT", 0x8000 }, { "L2", 0x0001 }, { "R2", 0x0002 },
    { "L1", 0x0004 }, { "R1", 0x0008 }, { "TRIANGLE", 0x0010 }, { "CIRCLE", 0x0020 },
    { "CROSS", 0x0040 }, { "SQUARE", 0x0080 },
};

/* the stick axes by read data byte (rdata[4..7] = RX RY LX LY) */
static const struct
{
    const char *name;
    unsigned int byte;
} socom_fake_axes[] =
{
    { "RX", 4 }, { "RY", 5 }, { "LX", 6 }, { "LY", 7 },
    /* the pressure bytes (only while the button is held, see scePadRead) */
    { "RIGHTP", 8 }, { "LEFTP", 9 }, { "UPP", 10 }, { "DOWNP", 11 }, { "TRIANGLEP", 12 }, { "CIRCLEP", 13 },
    { "CROSSP", 14 }, { "SQUAREP", 15 }, { "L1P", 16 }, { "R1P", 17 }, { "L2P", 18 }, { "R2P", 19 },
};

static unsigned int socom_fake_number(const char **pp)
{
    unsigned int v = 0;

    while (**pp >= '0' && **pp <= '9')
        v = v * 10 + (unsigned int)(*(*pp)++ - '0');

    return v;
}

/* the raw value the script gives a stick byte at this read (0x80, centred, when none) */
static unsigned char socom_fake_axis(unsigned int read, unsigned int byte)
{
    unsigned char value = 0x80;
    const char *p = socom_fake_script;

    while (*p != '\0')
    {
        unsigned int at;
        char name[16];
        unsigned int n = 0;
        unsigned int i;
        unsigned int v;
        unsigned int reads = 3;

        while (*p == ' ' || *p == ',')
            p++;

        at = socom_fake_number(&p);

        if (*p == ':')
            p++;

        while (*p != '\0' && *p != ',' && *p != ' ' && *p != '=' && n < sizeof(name) - 1)
            name[n++] = *p++;

        name[n] = '\0';

        if (*p != '=')
        {
            while (*p != '\0' && *p != ',' && *p != ' ')
                p++;

            continue;
        }

        p++;
        v = socom_fake_number(&p);

        if (*p == '+')
        {
            p++;
            reads = socom_fake_number(&p);
        }

        for (i = 0; i < sizeof(socom_fake_axes) / sizeof(socom_fake_axes[0]); i++)
        {
            if (strcmp(name, socom_fake_axes[i].name) == 0 && socom_fake_axes[i].byte == byte
                && read >= at && read < at + reads)
                value = (unsigned char)(v > 255 ? 255 : v);
        }

        while (*p != '\0' && *p != ',' && *p != ' ')
            p++;
    }

    return value;
}

/* the buttons the script holds down at this read */
static unsigned short socom_fake_pressed(unsigned int read)
{
    unsigned short pressed = 0;
    const char *p = socom_fake_script;

    while (*p != '\0')
    {
        unsigned int at = 0;
        char name[16];
        unsigned int n = 0;
        unsigned int i;

        while (*p == ' ' || *p == ',')
            p++;

        while (*p >= '0' && *p <= '9')
            at = at * 10 + (unsigned int)(*p++ - '0');

        if (*p == ':')
            p++;

        while (*p != '\0' && *p != ',' && *p != ' ' && n < sizeof(name) - 1)
            name[n++] = *p++;

        name[n] = '\0';

        if (strchr(name, '=') != NULL)
            continue; /* a stick term (socom_fake_axis) */

        for (i = 0; i < sizeof(socom_fake_buttons) / sizeof(socom_fake_buttons[0]); i++)
        {
            if (strcmp(name, socom_fake_buttons[i].name) == 0 && read >= at && read < at + 3)
                pressed |= socom_fake_buttons[i].bit;
        }
    }

    return pressed;
}

#define SOCOM_FAKE_PORT(port) ((port) == 0)
#else
#define SOCOM_FAKE_PORT(port) 0
#endif

int scePadInit(int mode)
{
#ifdef SOCOM_PORT_FAKE_PAD
    socom_port_trace("PAD: test hook SOCOM_PORT_FAKE_PAD=%s (port 0 is synthesized)", socom_fake_script);
#endif
    return padInit(mode);
}

int scePadEnd(void)
{
    return padEnd();
}

int scePadPortOpen(int port, int slot, void *addr)
{
    int result = padPortOpen(port, slot, addr);

    socom_port_trace("PAD: scePadPortOpen(%d, %d) -> %d", port, slot, result);

    if (SOCOM_FAKE_PORT(port))
        return 1;

    return result;
}

int scePadPortClose(int port, int slot)
{
    return padPortClose(port, slot);
}

int scePadRead(int port, int slot, unsigned char *rdata)
{
#ifdef SOCOM_PORT_FAKE_PAD
    if (SOCOM_FAKE_PORT(port))
    {
        unsigned short pressed = socom_fake_pressed(socom_fake_reads);

        if (pressed != 0 && socom_fake_pressed(socom_fake_reads - 1) != pressed)
            socom_port_trace("PAD: test hook read %u presses %04x", socom_fake_reads, pressed);

        socom_fake_reads++;
        memset(rdata, 0, 32);
        rdata[1] = 0x73; /* analog, 3 words */
        rdata[2] = (unsigned char)~(pressed >> 8);
        rdata[3] = (unsigned char)~pressed;
        /* the sticks: centred unless the script moves them */
        rdata[4] = socom_fake_axis(socom_fake_reads - 1, 4);
        rdata[5] = socom_fake_axis(socom_fake_reads - 1, 5);
        rdata[6] = socom_fake_axis(socom_fake_reads - 1, 6);
        rdata[7] = socom_fake_axis(socom_fake_reads - 1, 7);

        /* the pressure bytes (rdata[8..19]: right, left, up, down, triangle, circle, cross,
         * square, L1, R1, L2, R2) are full for held buttons: the game reads them directly
         * (CCtrlrConfigs::GetFireButtonPressure: the throw power, d-pad peeks) */
        {
            static const unsigned short pressure_bits[12] =
            {
                0x2000, 0x8000, 0x1000, 0x4000, 0x0010, 0x0020, 0x0040, 0x0080, 0x0004, 0x0008, 0x0001, 0x0002,
            };
            unsigned int i;

            for (i = 0; i < 12; i++)
            {
                /* a held button's pressure can be lowered by a term <read>:<BUTTON>P=<value>[+<reads>]
                 * (e.g. 800:R1P=100+40; 128 reads as "no term") */
                unsigned char level = socom_fake_axis(socom_fake_reads - 1, 8 + i);
                rdata[8 + i] = (pressed & pressure_bits[i]) == 0 ? 0x00 : level != 0x80 ? level : 0xff;
            }
        }

        if (rdata[4] != 0x80 || rdata[5] != 0x80 || rdata[6] != 0x80 || rdata[7] != 0x80)
        {
            static unsigned int traced;

            if (traced++ % 60 == 0)
                socom_port_trace("PAD: test hook read %u sticks RX %u RY %u LX %u LY %u", socom_fake_reads - 1,
                    rdata[4], rdata[5], rdata[6], rdata[7]);
        }

        return 32;
    }
#endif
    return padRead(port, slot, (struct padButtonStatus *)rdata);
}

int scePadGetState(int port, int slot)
{
    static int traced[2] = { -1, -1 };
    int state = padGetState(port, slot);

    if (port >= 0 && port < 2 && state != traced[port])
    {
        traced[port] = state;
        socom_port_trace("PAD: port %d state %d", port, state);
    }

    if (SOCOM_FAKE_PORT(port))
        return scePadStateStable;

    return state;
}

int scePadGetReqState(int port, int slot)
{
    if (SOCOM_FAKE_PORT(port))
        return scePadReqStateComplete;

    return padGetReqState(port, slot);
}

int scePadInfoMode(int port, int slot, int term, int offs)
{
    if (SOCOM_FAKE_PORT(port))
        return term == InfoModeCurID ? 7 : 0; /* an analog pad, no extended id or table */

    return padInfoMode(port, slot, term, offs);
}

int scePadSetMainMode(int port, int slot, int offs, int lock)
{
    if (SOCOM_FAKE_PORT(port))
        return 1;

    return padSetMainMode(port, slot, offs, lock);
}

int scePadInfoAct(int port, int slot, int actno, int term)
{
    if (SOCOM_FAKE_PORT(port))
        return 0; /* no actuators */

    return padInfoAct(port, slot, actno, term);
}

int scePadSetActAlign(int port, int slot, const unsigned char *data)
{
    if (SOCOM_FAKE_PORT(port))
        return 1;

    return padSetActAlign(port, slot, (const char *)data);
}

int scePadSetActDirect(int port, int slot, const unsigned char *data)
{
    if (SOCOM_FAKE_PORT(port))
        return 1;

    return padSetActDirect(port, slot, (const char *)data);
}

int scePadInfoPressMode(int port, int slot)
{
    if (SOCOM_FAKE_PORT(port))
        return 0;

    return padInfoPressMode(port, slot);
}

int scePadEnterPressMode(int port, int slot)
{
    if (SOCOM_FAKE_PORT(port))
        return 1;

    return padEnterPressMode(port, slot);
}
