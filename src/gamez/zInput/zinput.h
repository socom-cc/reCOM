#ifndef ZINPUT_H
#define ZINPUT_H

/* port: forward declarations for names this header uses */
class CIOPManager;
class CPnt3D;
class CZSealBody;
#include "gamez/zSystem/zsys.h"
#include "gamez/zUtil/zutil.h" /* CIOPManager::RebootPhase/RebootMode */

#include <map>
/* @socom-skeleton decl forward */
/* STUN_TYPE: declared by gamez/zSeal/zseal.h, included below before CRemoteCtrl (its only use here) */
/* @socom-skeleton end forward */

class CInput;
class CPad;
class CKeyboard;
class CValve;
class CMouse;

/* pad_dt is file-local in zin_main.cpp (LOCAL symbol) */

enum KEY_STATE : unsigned char /* DWARF byte_size 1 (CPad::m_state, UpdateButton 0x219850 stores bytes) */
{
	KEY_UP,
	KEY_FALLING,
	KEY_DOWN,
	KEY_RISING
};

enum class PAD_BUTTON : unsigned char /* DWARF byte_size 1 */
{
	PAD_START,
	PAD_SELECT,
	PAD_RIGHT,
	PAD_LEFT,
	PAD_UP,
	PAD_DOWN,
	PAD_TRIANGLE,
	PAD_CIRCLE,
	PAD_SQUARE,
	PAD_CROSS,
	PAD_TRIGGER_R1,
	PAD_TRIGGER_R2,
	PAD_TRIGGER_L1,
	PAD_TRIGGER_L2,
	PAD_RIGHT_STICK,
	PAD_LEFT_STICK,
	PAD_MAX_BUTTONS
};

s32 InitKeyreadStuff();

class CStickType
{
	friend class CPad;
private:
	f32 m_minStickVelocity;
	f32 m_absoluteDeadZone;
	f32 m_velocityDeadZone;
	f32 m_valueForConstant;
	f32 m_valueForN;

	bool m_velocitySeparate;
	bool m_deadZoneSeparate;

	f32 m_minZeroVelocityTime;

	bool m_normalize;
	bool m_dilate;
	/* @socom-skeleton decl 10CStickType */
public:
	void ReadControlFile(int);
	/* @socom-skeleton end 10CStickType */
};

class CInput
{
public:
	// Disallow construction of a purely static class
	CInput() = delete;

	static void Init();
	static void Uninit();
	static void Tick(f32 dT);
	static CPad* CreatePad(u32 slot);
	static void DeletePad(u32 slot);
	static void Flush();
	static int OpenPadIO();
	static void ClosePadIO();
	static bool m_init;

	static CPad* m_pads[2];
	static CKeyboard* m_keyboard;
	/* @socom-skeleton decl 6CInput */
public:
	static bool IOPRebootHandler(CIOPManager::RebootPhase, CIOPManager::RebootMode, void *);
	/* @socom-skeleton end 6CInput */
};

class CPad
{
public:
	CPad() { }
	/* constructor: the binary has only __ct__4CPadFii, declared below */

	void SetButtonState(PAD_BUTTON button, KEY_STATE state);
	
	void Flush();
	
	void Tick(f32 delta);

	bool GetTwoButtons(PAD_BUTTON button1, PAD_BUTTON button2);
	/* IsOpen: the binary has only IsOpen__4CPadCFv (const), declared below */

	/* DWARF CPad (404 bytes) */
	s32 m_port;              /* +0x0 */
	s32 m_slot;              /* +0x4 */
	s32 m_open;              /* +0x8 scePadPortOpen result */

	u8 m_ActData[6];         /* +0xc scePadSetActDirect data */
	bool m_IsAnalog;         /* +0x12 */

	KEY_STATE m_state[16];   /* +0x13 */
	u8 m_singleClick[16];    /* +0x23 */
	u8 m_doubleClick[16];    /* +0x33 */
	f32 m_click[16];         /* +0x44 click timers: -1 single, -2 double, -3 consumed */

	long128* m_DmaBuf;       /* +0x84 256 bytes of m_DmaBufArray per port */

	u8 m_InData[32];
	u32 m_Data;
	u32 m_AnalogLeft[2];
	u32 m_AnalogRight[2];

	s32 m_Phase;
	s32 m_State;
	s32 m_Id;
	s32 m_ExId;
	s32 m_actuator;
	s32 m_NumActuators;

	f32 m_LeftStick[2];      /* +0xd4 */
	f32 m_RightStick[2];     /* +0xdc */
	bool m_swapSticks;       /* +0xe4 */

	f32 m_LeftStickDilated[2];  /* +0xe8 */
	f32 m_RightStickDilated[2]; /* +0xf0 */
	
	bool m_DataIsGood;       /* +0xf8 */

	u8 m_ActAlign[6];        /* +0xf9 */

	s32 m_RotationVibration;
	s32 m_RotationSpeed;
	s32 m_ControlNum;
	s32 m_Consuption;

	u8 m_lastStickRaw[4];
	f32 m_lastStickVal[4];
	f32 m_maxStick[4];
	f32 m_minStick[4];       /* +0x134 (DWARF m_minStick) */
	f32 m_deadTime[4];       /* +0x144 */

	CStickType m_stickType[2]; /* +0x154 */
	/* @socom-skeleton decl 4CPad */
public:
	CPad(int, int);
	bool IsOpen() const;
	~CPad();
	void SetSensitivity(int, float);
	float GetSensitivity(int);
	void SetAcceleration(int, float);
	float GetAcceleration(int);
	void SetDeadZone(int, float);
	float GetDeadZone(int);
	void SetPreset(int, int);
	void CheckStickVelocity(float &, float &, int);
	void Dilate(float &, float &, int);
	bool GetSingleClick(PAD_BUTTON); /* port: bool (0x219a50 returns 0/1) */
	bool GetDoubleClick(PAD_BUTTON); /* port: bool (0x219a00 returns 0/1) */
	void UpdateButton(PAD_BUTTON, unsigned int);
	/* @socom-skeleton end 4CPad */
};
/* @socom-skeleton decl 6CCheat */
class CCheat;
/* m_list__6CCheat (12 bytes, MSL vector<CCheat *>; __dt__10CCheatList 0x21b800) */
class CCheatList : public std::vector<CCheat *> {};
/* No DWARF and no constructor in the ELF (nothing makes a cheat); layout from Update 0x21b610.
 * Names invented. */
class CCheat
{
public:
	static void TickAll(float, CPad *);
	bool Update(float, CPad *); /* 0x21b610 returns 1 when the sequence completes */
	static const float cheatTimer;
	static CCheatList m_list;

	u32 m_unknown0;           /* +0x0: never read by Update */
	u32 m_length;             /* +0x4: buttons in the sequence */
	const u8 *m_sequence;     /* +0x8: PAD_BUTTON values */
	u32 m_unknownc;           /* +0xc */
	f32 m_timer;              /* +0x10: time left for the next button */
	const u8 *m_cursor;       /* +0x14: the next button expected */
	CValve *m_valve;          /* +0x18: pulsed on completion */
};
/* @socom-skeleton end 6CCheat */
/* @socom-skeleton decl 9CKeyboard */
class CKeyboard
{
public:
	CKeyboard();
	~CKeyboard();
	void Tick(float);
	u8 m_unknown0; /* +0x0: cleared by the ctor 0x21bf10, never read */
};
/* GetKeyReadThisFrame's result (zin_keyboard.cpp 0x21bc20; the soft keyboard's). No DWARF;
 * names from the statics it copies. */
struct KeyInput
{
	u8 m_key;           /* +0x0: the key code to type this frame (USB usage id), or 0 */
	int m_shift;        /* +0x4 */
	int m_ctrl;         /* +0x8 */
	int m_alt;          /* +0xc */
	int m_appleOrStart; /* +0x10 */
	int m_capsLock;     /* +0x14 */
	int m_numLock;      /* +0x18 */
	int m_anyDown;      /* +0x1c: any key held */
};
/* @socom-skeleton end 9CKeyboard */

/* CSealCtrl: base of CRemoteCtrl. Included after this header's own declarations because the
   zseal.h chain (zui.h -> ztwod.h) includes this header again. */
#include "gamez/zSeal/zseal.h"
/* @socom-skeleton decl 11CRemoteCtrl */
class CRemoteCtrl : public CSealCtrl
{
public:
	/* no ctor symbol: CreateRemoteSeal 0x289480 inlines it (CSealCtrl's ctor, the vtable, the
	 * fade values) */
	CRemoteCtrl() { m_fade_min = 0.001f; m_fade_time = 2.0f; }
	virtual ~CRemoteCtrl(); /* 0x2ce160 (remote_control.cpp) */
	virtual bool PreTick(float);
	virtual bool Tick(float);
	virtual void PostMortemPreTick(float);
	virtual void OnDeath() {} /* ELF 0x2ce1d0: jr ra */
	virtual CRemoteCtrl *GetRemoteControl() { return this; } /* ELF 0x2ce1c0: move v0,a0 */
	virtual bool AllowCommand(CZSealBody *, FT_COMMAND, void *); /* port: bool = CSealCtrl::AllowCommand (override) */
	virtual bool IsPlayer() const { return false; } /* ELF 0x2ce1f0: move v0,zero */
	virtual bool IsRemote() const { return true; } /* ELF 0x2ce200: li v0,1 */
	virtual void PostTick(float);
	virtual void OnStunDamage(STUN_TYPE, float, const CPnt3D *) {} /* ELF 0x2ce1e0: jr ra */
	virtual void SetAiNetState(unsigned int);
	virtual void OnCommand(CZSealBody *, FT_COMMAND, void *, bool);
	u8 GetRemoteAiState();
	CZSealBody *GetRemoteAiFollowMaster();
	/* after CSealCtrl's 0x240 bytes (PostMortemPreTick 0x2ce220); names invented */
	f32 m_fade_min;  /* +0x240: 0.001 */
	f32 m_fade_time; /* +0x244: 2 s */
};
/* @socom-skeleton end 11CRemoteCtrl */
#endif