#ifndef ZCAMERA_H
#define ZCAMERA_H
#include "gamez/zAnim/zanim.h"
#include "gamez/zMath/zmath.h"
#include "gamez/zNode/znode.h"
#include "gamez/zSystem/zsys.h"

enum class SEAL_PEEK;

class CHUD;

class CEntity;
class CAppCamera;
class CZSealBody;
class CZBodyPart;

extern CAppCamera* appCamera;

/* fogCheck (zcam_main.cpp) and camera_tether_intersects_something, save_short_tether_length,
   DeltaRot, DeltaAim (camera.cpp) are file-local (LOCAL symbols; DWARF local_variable) */

void GetFirstPersonCameraPos(CAppCamera* appCamera);
void FirstToThirdPersonTransition(CAppCamera* appCamera);
void ThirdToFirstPersonTransition(CAppCamera* appCamera);

enum class CAMVIEW
{
	cam_view_third,
	cam_view_side,
	cam_view_first,
	cam_view_peek_left,
	cam_view_peek_right,
	cam_view_last
};

enum class PLAYER_CAM_STATE
{
	cam_mode_unk,
	cam_mode_tether,
	cam_mode_FP,
	cam_mode_apLook,
	cam_mode_net
};

enum class CAM_DEATH_STATE
{
	none,
	init_dying,
	tether_initial_dying,
	view_killer,
	tether_killer,
	tether_body,
	auto_rotate_body,
	user_rotate_body
};

class CCameraParams
{
public:
	CPnt3D m_cam_offset;
	CPnt3D m_cam_aimpoint;
};

namespace zdb
{
	struct tag_CAMERA_PARAMS
	{
		CQuat m_quat;

		CPnt4D m_fog_color;

		f32 m_hfov;
		f32 m_vfov;

		f32 m_near_plane;
		f32 m_mid_plane;
		f32 m_far_plane;

		CPnt3D m_px_fog_color;
		CPnt3D m_nx_fog_color;
		CPnt3D m_pz_fog_color;
		CPnt3D m_nz_fog_color;
		f32 m_fog_near;
		f32 m_fog_far;
		f32 m_fog_mid;
		f32 m_fogA;
		f32 m_fogB;
		f32 m_fog_density;
		f32 m_fog_top;
		f32 m_fog_bottom;
		f32 m_landmark_fog_top;
		f32 m_landmark_fog_bottom;

		u32 m_flags_unused : 29;
		u32 m_fog_enabled : 1;
		u32 m_directional_fog_enabled : 1;
		u32 m_fog_alt_enabled : 1;
	};

	struct tag_RECT
	{
		s32 left;
		s32 top;
		s32 right;
		s32 bottom;
	};

	struct tag_FrameSetup;

	struct tag_ZCAM_MTX_SET
	{
		f32 mtxWorldToView[4][4];
		f32 mtxWorldToClip[4][4];
		f32 mtxViewToClip[4][4];
		f32 mtxViewToScreen[4][4];
		tag_FrameSetup* m_vu; /* DWARF member at +0x100: the VU1 frame-setup packet (scratchpad 0x70003e60) */
	};

	struct tag_FrameSetup
	{
		_word128 dmaTag;
		_word128 vifTag;
		f32 mtxWorldToScreen[4][4];
		f32 mtxWorldToClip[4][4];
		f32 mtxClipToScreen[4][4];
		f32 mtxLightNormal[4][4];
		f32 mtxLightColor[4][4];
		f32 fogA[4];
		f32 fogB[4];
		_word128 shadowGifTag;
	};

	enum tag_ZCAM_TYPE
	{
		ZCAM_NORMAL,
		ZCAM_LANDMARK,
		ZCAM_NUM_TYPES
	};

	struct _tag_SAVE_CAMERA_PARAMS
	{
		tag_CAMERA_PARAMS m_CameraParams;
		float m_RangeScale;
	};

	struct ZCAM_CLIP_DATA
	{
		CPnt4D ViewPlanePoint;
		CPnt4D NearPlanePoint;
		CPnt4D NearPlaneNormal;
		CPnt4D LeftPlaneNormal;
		CPnt4D RightPlaneNormal;
		CPnt4D TopPlaneNormal;
		CPnt4D BottomPlaneNormal;
	};

	class CCamera : public CNode, public tag_CAMERA_PARAMS
	{
	public:
		CCamera();
		
		static void RegisterAnimCommands();

		static _zanim_cmd_hdr* CmdParseRelease(_zrdr* reader);
		static _zanim_cmd_hdr* CmdParseAcquire(_zrdr* reader);
		static _zanim_cmd_hdr* CmdParseIndoorsTest(_zrdr* reader);
		static _zanim_cmd_hdr* CmdParseSetRegions(_zrdr* reader);
		static _zanim_cmd_hdr* CmdParseGetRegions(_zrdr* reader);
		static _zanim_cmd_hdr* CmdParseParams(_zrdr* reader);

		static void CmdBeginParams(_zanim_cmd_hdr* header);

		static bool CmdTickControlSwitch(_zanim_cmd_hdr* header, f32* delta);
		static bool CmdTickIndoorsTest(_zanim_cmd_hdr* header, f32* delta);
		static bool CmdTickSetRegions(_zanim_cmd_hdr* header, f32* delta);
		static bool CmdTickGetRegions(_zanim_cmd_hdr* header, f32* delta);
		static bool CmdTickParams(_zanim_cmd_hdr* header, f32* delta);
		
		void Update(tag_ZCAM_TYPE type);

		f32 GetScaledRangeSquared(const CPnt3D& point) { return 0.0f; }

		bool CanSeeRegion(u32 mask);

		void SetHalfHorizontalFOVRadians(f32 radians);
		void SetFarClip(f32 farclip);
		
		static bool m_dynamics_controlled;
		static bool m_do_region_test;
		
		f32 m_Zmin;
		f32 m_Zmax;
		f32 m_RangeScale;
	
		CPnt3D m_frustum[3];
		CPnt3D m_fullfrustum[6];
		s32 m_fullfrustum_points; /* DWARF spelling */

		PNT2D m_sin;
		PNT2D m_cos;
		PNT2D m_tan;
		PNT2D m_cot;

		std::vector<void*> m_LensFlareList;

		_tag_SAVE_CAMERA_PARAMS m_saveParams;

		f32 m_scrZ;

		std::vector<void*> m_lensflare_vec;

		u32 m_PlayerCanSeeRegions; /* DWARF uint */
		u32 m_CameraCanSeeRegions;
		u32 m_SeeRegions;
		bool m_IsInside;
		
		s32 m_AboveMaterial;

		f32 m_landmark_far_plane;

		tag_ZCAM_MTX_SET m_mtxSet;
		ZCAM_CLIP_DATA m_ClipSet;
		
		PNT2D m_screenAspect;
		PNT2D m_screenCenter;
		PNT2D m_screenOffset;
		tag_RECT m_screen;
		PNT2D m_screenConstant;

		f32 m_guardBand_min[4];
		f32 m_guardBand_max[4];

		f32 m_vecClipVolume[4];
		f32 m_farCorner[2][4];
		CPnt4D m_fog_alt[2];
		CPnt4D m_landmark_fog_alt[2];

		tag_ZCAM_TYPE m_type;

		u32 m_fovMask;

		f32 m_yaw;
		f32 m_pitch;
		/* @socom-skeleton decl Q23zdb7CCamera */
public:
		virtual ~CCamera();
		void SetHalfVerticalFOVRadians(float);
		void SetMidClip(float);
		void SetNearClip(float);
		void UpdateFrustum();
		int find_convex_hull_xz(CPnt3D *, int);
		void theta_x_z(CPnt3D *, CPnt3D *, float *, float *);
		zdb::tag_ZVIS_FOV TestFOV(PNT4D *, unsigned int *, bool);
		void SetCameraCanSeeRegions(unsigned int);
		void SetPlayerCanSeeRegions(unsigned int);
		unsigned char PlayerCanSeeRegion(unsigned int);
		unsigned int GetPlayerCanSeeRegion();
		float GetScaledRangeSquared(CPnt3D *);
		unsigned char InsideMidPlane(zdb::CCell *);
		unsigned char InsideMidPlane(zdb::CNode *);
		float GetZ(CPnt3D *);
		float GetScaledZSquared(CPnt3D *);
		void GetLandmarkFarPlane(zdb::CWorld *);
		unsigned char TestFOG(const CPnt3D *, float);
		unsigned char TestLandmarkFOG(const CPnt3D *, float);
		unsigned __int128 * GetVuMtxSet();
		float GetFogVisibility(const CPnt3D *, const CPnt3D *) const;
		void UpdateDirectionalFog();
		/* @socom-skeleton end Q23zdb7CCamera */
	};
}

class CAppCamera
{
public:
	CAppCamera(zdb::CWorld* world, zdb::CCamera* camera);
	~CAppCamera();

	static void GetThirdPersonCameraPos(CPnt3D* out, f32* partPosition);
	static _zanim_cmd_hdr* CmdParse3rdPersonTest(_zrdr* reader);
	static bool CmdTick3rdPersonTest(_zanim_cmd_hdr* header, f32* delta);
	static void RegisterAnimCommands();
public:
	// bool AttachTo(CZSealBody* seal);

	void APLookAt(f32 dT, CEntity* entity, CMatrix& matrix);
	void APFirstPersonCam(CMatrix& matrix);
	void APTeatherCam(CMatrix& transform, float offset);
	

	void FTSTick(f32 delta);
	void Tick(f32 dT);

	void UpdateDeathCamState();
	void ResetDeathCam();
	void TickCameraWiggle(f32 dT, zdb::CCamera* camera);

	void SetZoom(f32 zoom);

	void WiggleScalar(f32 wiggle);
	void WiggleEcho(bool echo);
public:
	PLAYER_CAM_STATE m_camera_mode;
	PLAYER_CAM_STATE m_camera_last_mode;

	CPnt3D m_cameraAim;
	CPnt3D m_cameraTie;
	CPnt3D m_camGoalPos;

	f32 m_goal_t_len;
	f32 m_short_tether_timer;
	u32 m_padid;

	zdb::CCamera* m_camera;
	zdb::CNode* m_camera_effects;

	CZSealBody* m_entity;
	CZBodyPart* m_skel_root;

	CPnt3D m_rPos;
	CPnt3D m_wPos;

	CAMVIEW m_ctrl_view;

	f32 m_view_delay;
	f32 m_z_nominal;

	f32 m_switch_time;
	f32 m_wiggle_amp;
	f32 m_wiggle_duration;
	f32 m_wiggle_inv_duration;
	f32 m_wiggle_rate;
	f32 m_wiggle_inv_rate;
	f32 m_wiggle_cur_time;
	f32 m_wiggle_scalar;
	bool m_wiggle_echo;

	CEntity* m_track;

	SEAL_PEEK m_save_peek;
	CAMVIEW m_save_view;

	bool m_auto_death_cam;
	bool m_allow_player_death_cam_control;
	CAM_DEATH_STATE m_cam_death_state;
	f32 m_death_state_timer;
	CZSealBody* m_killed;
	CZSealBody* m_killer;

	s32 m_flashcounter;

	f32 m_death_fade_out_time;
	f32 m_death_faded_time;
	f32 m_death_fade_in_time;

	f32 m_next_rumble_time;
	f32 m_next_rumble_time_scaler;
	s32 m_rumble_counter;
	f32 m_rumble_timer;
	f32 m_rumble_time;
	f32 m_rumble_time_scaler;
	f32 m_rumble_power;
	f32 m_rumble_power_scaler;
	/* @socom-skeleton decl 10CAppCamera */
public:
	virtual unsigned char AttachTo(CZSealBody *);
	void ClipCameraChord(float, CPnt3D *, CPnt3D *, CPnt3D *);
	void LookAt(const CPnt3D *, const CPnt3D *, CMatrix &);
	void GetThirdPersonCamPos(CPnt3D *, float *);
	void UpdateDeathCamState(float);
	unsigned char GetDeadCamPoints(CPnt3D *, CPnt3D *, CMatrix *, float);
	unsigned char GetTetherCamPoints(CPnt3D *, CPnt3D *, CPnt3D *, float);
	/* @socom-skeleton end 10CAppCamera */
};

class CameraZoom
{
public:
	static void AttachHud(CHUD* hud);
	static void AttachSeal(CZSealBody* seal);
public:
	static CHUD* m_hud;
	static CZSealBody* m_seal;
	/* @socom-skeleton decl 10CameraZoom */
public:
	static void SetGoal(float);
	static void HandleZoomIn(float, float);
	static void HandleNewZoom();
	static void OnGoal();
	static unsigned char Tick(float);
	static float m_current;
	static float m_goal;
	static float m_increment;
	static unsigned char m_isGoalHit;
	static unsigned char m_iszoom;
	static CAMVIEW m_oldview;
	/* @socom-skeleton end 10CameraZoom */
};
/* VU0 helpers of TestFOV (GLOBAL functions in fov.cpp) */
unsigned int sceVu0ClipBBox(float (*)[4], PNT4D *);
int _OutsideGuardBand(float *, float *, float (*)[4], float (*)[4], int);
#endif