/* Port compatibility header: the Sony EE libpad.h. It declares the Sony scePadXxx calls
 * the game makes, which port/compat/libpad.c implements over ps2sdk's libpad (padXxx).
 * ps2sdk's own libpad.h of the same name is not chained: its PAD_START... button macros
 * collide with the game's PAD_BUTTON enumerators. Declarations are backed by the call
 * sites in zin_main.cpp (CPad 0x219aa0, 0x21b240, 0x21b3a0; CInput 0x21b5a0, 0x21b5f0). */
#ifndef SOCOM_COMPAT_LIBPAD_H
#define SOCOM_COMPAT_LIBPAD_H

#ifdef __cplusplus
extern "C" {
#endif

/* scePadGetState */
#define scePadStateDisconn  0
#define scePadStateFindPad  1
#define scePadStateFindCTP1 2
#define scePadStateExecCmd  5
#define scePadStateStable   6
#define scePadStateError    7

/* scePadGetReqState */
#define scePadReqStateComplete 0
#define scePadReqStateFaild    1
#define scePadReqStateBusy     2

/* scePadInfoMode terms */
#define InfoModeCurID    1
#define InfoModeCurExID  2
#define InfoModeCurExOffs 3
#define InfoModeIdTable  4

/* scePadInfoAct terms */
#define InfoActFunc  1
#define InfoActSub   2
#define InfoActSize  3
#define InfoActCurr  4

int scePadInit(int mode);
int scePadEnd(void);
int scePadPortOpen(int port, int slot, void *addr);
int scePadPortClose(int port, int slot);
int scePadRead(int port, int slot, unsigned char *rdata);
int scePadGetState(int port, int slot);
int scePadGetReqState(int port, int slot);
int scePadInfoMode(int port, int slot, int term, int offs);
int scePadSetMainMode(int port, int slot, int offs, int lock);
int scePadInfoAct(int port, int slot, int actno, int term);
int scePadSetActAlign(int port, int slot, const unsigned char *data);
int scePadSetActDirect(int port, int slot, const unsigned char *data);
int scePadInfoPressMode(int port, int slot);
int scePadEnterPressMode(int port, int slot);

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_LIBPAD_H */
