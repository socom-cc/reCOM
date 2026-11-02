#ifndef ZINPUT_H
#define ZINPUT_H
#include "gamez/zSystem/zsys.h"

#include <map>
/* @socom-skeleton decl forward */
class STUN_TYPE;
/* @socom-skeleton end forward */

class CInput;
class CPad;
class CKeyboard;
class CMouse;

extern float pad_dt;

enum KEY_STATE
{
	KEY_UP,
	KEY_FALLING,
	KEY_DOWN,
	KEY_RISING
};

enum class PAD_BUTTON
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
	CPad(u32 port, u32 slot);

	void SetButtonState(PAD_BUTTON button, KEY_STATE state);
	
	void Flush();
	
	void Tick(f32 delta);

	bool GetTwoButtons(PAD_BUTTON button1, PAD_BUTTON button2);
	bool IsOpen();

	s32 m_port;
	s32 m_slot;
	s32 m_open;

	u8 m_ActData;
	bool m_IsAnalog;

	KEY_STATE m_state[16];
	u8 m_singleClick[16];
	u8 m_doubleClick[16];
	f32 m_click[16];

	long128* m_DmaBuf;

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

	f32 m_LeftStick[2];
	f32 m_RightStick[2];
	bool m_swapSticks;

	f32 m_LeftStickDilated;
	f32 m_RightStickDilated;
	
	bool m_DataIsGood;

	u8 m_ActAlign[6];

	s32 m_RotationVibration;
	s32 m_RotationSpeed;
	s32 m_ControlNum;
	s32 m_Consuption;

	u8 m_lastStickRaw[4];
	f32 m_lastStickVal[4];
	f32 m_maxStick[4];
	f32 m_minstick[4];
	f32 m_deadTime[4];

	CStickType m_stickType[2];
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
	void GetSingleClick(PAD_BUTTON);
	void GetDoubleClick(PAD_BUTTON);
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
	virtual void AllowCommand(CZSealBody *, FT_COMMAND, void *);
	virtual void IsPlayer() const;
	virtual void IsRemote() const;
	virtual void PostTick(float);
	virtual void OnStunDamage(STUN_TYPE, float, const CPnt3D *);
	virtual void SetAiNetState(unsigned int);
	virtual void OnCommand(CZSealBody *, FT_COMMAND, void *, bool);
	void GetRemoteAiState();
	void GetRemoteAiFollowMaster();
};
/* @socom-skeleton end 11CRemoteCtrl */
#endif