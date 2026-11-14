#ifndef GRID_CLUTTER_H
#define GRID_CLUTTER_H
#include "gamez/zNode/znode.h"

namespace zdb
{
	class CCell;
	class CClutterAnim;

	/* One piece of clutter (grass, bushes, debris): a model drawn at its own matrix in a cell.
	 * Not in DWARF; the 112-byte layout (new 112 in ReadClutter) is from the code that uses it.
	 * Bytes 0x00-0x5f are the archive's "params" record (Read 0x218ec0), 0x60 "scale_inverse".
	 * Member names are invented. */
	class CClutter
	{
	public:
		/* +0x00: a static clutter's model matrix (GetMatrix returns it). An animated one
		 * (m_animated) keeps the same 64 bytes as a rotation quaternion (+0x00), the
		 * animation's bend quaternion (+0x10, identity at rest), the position (+0x20), a
		 * uniform scale (+0x2c) and the bend force at the centre of an effector (+0x30,
		 * TickForce); Rotation() and the others below name those words. */
		CMatrix m_matrix;
		f32 m_farFadeStart;   /* +0x40 range (squared, camera range scale) where fading starts */
		f32 m_farFadeEnd;     /* +0x44 not drawn from here on; CClutterList keeps the largest */
		f32 m_farFadeScale;   /* +0x48 opacity per unit before m_farFadeEnd */
		u32 m_farFade : 1;    /* +0x4c bit 0: far fade; kept after the others in the list */
		u32 m_animated : 1;   /* bit 1: quaternion form, bent by effectors (ClutterTick) */
		u32 m_nearFade : 1;   /* bit 2: near fade */
		u32 m_flag3 : 1;      /* bit 3: cleared by the ctor, not read */
		u32 m_flag4 : 2;      /* bits 4-5: cleared by the ctor, not read */
		u32 m_useRegion : 1;  /* bit 6: drawn only when the camera can see m_region */
		u32 m_region : 5;     /* bits 7-11: region shift (CCamera::CanSeeRegion(1 << m_region)) */
		u32 m_flag12 : 20;    /* bits 12-31: cleared by the ctor, not read */
		f32 m_nearFadeStart;  /* +0x50 not drawn up to here */
		f32 m_nearFadeEnd;    /* +0x54 fading in up to here */
		f32 m_nearFadeScale;  /* +0x58 */
		u32 m_color;          /* +0x5c added colour 0x00RRGGBB (ColConvTo3D -> CVisual::m_addColor) */
		f32 m_lightScale;     /* +0x60 "scale_inverse": CVisual::m_GlobalLightScale while drawn */
		CNode* m_node;        /* +0x64 the model (shared by every clutter of the model) */
		CClutterAnim* m_anim; /* +0x68 the running bend animation, or NULL */
		u32 m_unk6c;          /* +0x6c not accessed */

		CQuat* Rotation() { return reinterpret_cast<CQuat*>(&m_matrix.m_matrix[0][0]); }
		CQuat* AnimRotation() { return reinterpret_cast<CQuat*>(&m_matrix.m_matrix[1][0]); }
		f32 Scale() const { return m_matrix.m_matrix[2][3]; }
		f32 MaxForce() const { return m_matrix.m_matrix[3][0]; }

		/* @socom-skeleton decl Q23zdb8CClutter */
public:
		CClutter(zdb::CNode *);
		bool Read(zar::CZAR *); /* 0x218ec0 returns the "scale_inverse" fetch result */
		CPnt3D * GetTranslate();
		CMatrix * GetMatrix();
		void Render(CPnt3D *);
		/* @socom-skeleton end Q23zdb8CClutter */
	};

	/* DWARF zdb::CClutterList (20 bytes): a vector of clutter, non-fading ones first */
	class CClutterList : public std::vector<CClutter*>
	{
	public:
		bool m_ContainsRepelClutter; /* +0xc an animated clutter is in the list */
		f32 m_max_farFadeSq;         /* +0x10 the largest m_farFadeEnd of the fading ones */

	/* @socom-skeleton decl Q23zdb12CClutterList */
public:
	void Add(zdb::CClutter *);
	void Render(zdb::CCell *);
	void Free();
	/* @socom-skeleton end Q23zdb12CClutterList */
	};
}

#endif
