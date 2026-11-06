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
class CCheat
{
public:
	static void TickAll(float, CPad *);
	void Update(float, CPad *);
	static const float cheatTimer;
	static int m_list[3];
};
/* @socom-skeleton end 6CCheat */
/* @socom-skeleton decl 9CKeyboard */
class CKeyboard
{
public:
	CKeyboard();
	~CKeyboard();
	void Tick(float);
};
/* @socom-skeleton end 9CKeyboard */

/* CSealCtrl: base of CRemoteCtrl. Included after this header's own declarations because the
   zseal.h chain (zui.h -> ztwod.h) includes this header again. */
#include "gamez/zSeal/zseal.h"
/* @socom-skeleton decl 11CRemoteCtrl */
class CRemoteCtrl : public CSealCtrl
{
public:
	virtual ~CRemoteCtrl();
	virtual void PreTick(float);
	virtual void Tick(float);
	virtual void PostMortemPreTick(float);
	virtual void OnDeath();
	virtual void GetRemoteControl();
	virtual bool AllowCommand(CZSealBody *, FT_COMMAND, void *); /* port: bool = CSealCtrl::AllowCommand (override) */
	virtual bool IsPlayer() const; /* port: bool = CSealCtrl::IsPlayer (override) */
	virtual bool IsRemote() const; /* port: bool = CSealCtrl::IsRemote (override) */
	virtual void PostTick(float);
	virtual void OnStunDamage(STUN_TYPE, float, const CPnt3D *);
	virtual void SetAiNetState(unsigned int);
	virtual void OnCommand(CZSealBody *, FT_COMMAND, void *, bool);
	void GetRemoteAiState();
	void GetRemoteAiFollowMaster();
};
/* @socom-skeleton end 11CRemoteCtrl */
#endif