#ifndef ZINTERSECT_H
#define ZINTERSECT_H

/* port: forward declarations for names this header uses */
class CRdrFile;
class CSnd;
#include <map>
#include <string>
#include <vector>

#include "gamez/zMath/zmath.h"
#include "gamez/zSystem/zsys.h"

namespace zdb
{
    class CNode;
    class CSaveLoad;
}

namespace zdb
{
    class CDI;

    struct DI_PARAMS
    {
        CPnt4D m_nrm;
        u32 m_region;
        u32 m_refcount;
        u32 m_ditype : 2;
        u32 m_ptcount : 8;
        u32 m_material : 8;
        u32 m_cameratype : 2;
        u32 m_appflags : 3;
        u32 m_inside : 1;
        u32 m_shadow : 2;
        u32 m_reserved : 6;
    };

    struct IntersectStruct
    {
        CPnt3D m_pos;
        CDI* m_poly; /* DWARF +0xc */
        CPnt3D m_norm;
        CNode* m_node;
        /* @socom-skeleton decl Q23zdb15IntersectStruct */
public:
        unsigned int GetMaterial();
        unsigned int GetRegion();
        unsigned char IsInside();
        bool GetIntersectedEdgePointsY(CPnt3D *); /* 0x21c130 returns 0/1 */
        bool GetIntersectedEdgePoints(CPnt3D *, CPnt3D *); /* 0x21bf20 returns 0/1 */
        /* @socom-skeleton end Q23zdb15IntersectStruct */
    };

    struct DiIntersect
    {
        DiIntersect() {}
        DiIntersect(s32 count);
        
        u32 m_Type : 16;
        u32 m_IntersectCharacters : 1;
        u32 m_AltitudeCharacters : 1;
        u32 m_ProximityCharacters : 1;
        u32 m_Unused : 13;

        CPnt3D m_Tail;
        CPnt3D m_Tip;
        CPnt3D m_MTail;
        CPnt3D m_MTip;

        s32 m_Cnt;
        s32 m_BufCnt;

        CNode* m_Node;
        CNode* m_TreeDoneNode;
        IntersectStruct* m_Intersects;
        /* @socom-skeleton decl Q23zdb11DiIntersect */
public:
        void SortNearToFar(int *, float *);
        zdb::IntersectStruct * GetNearestIntersect();
        zdb::IntersectStruct * GetHighestAltitude(const CPnt3D *, float);
        void LoadTipAndTail();
        ~DiIntersect();
        /* @socom-skeleton end Q23zdb11DiIntersect */
    };

    class CHit : public IntersectStruct
    {
    public:
        CPnt3D m_hit0;
        CPnt3D m_hit1;
    };
    
    class CDI : public DI_PARAMS
    {
    public:
        enum class CDIType
        {
            type_00,
            type_01,
            type_02,
            type_03,
            type_04
        };
        
        CDI();

        static CDI* Create(CSaveLoad& sload);

        void Allocate(size_t size);
        void Free();
        bool Read(CSaveLoad& sload);

        s32 GetEdgeIntersects(CPnt3D* firstPoint, CPnt3D* secondPoint, CPnt3D* edge) const;
        s32 GetEdgeIntersectsY(CPnt3D* firstPoint, CPnt3D* secondPoint) const;

        /* pure in __vt__Q23zdb3CDI (slots +0x14/+0x18 are 0); CDIPoly/CDIBBox/CDIDummy
           define them. Both return whether the DI was hit. */
        virtual bool GetIntersect(DiIntersect* di) = 0;
        virtual bool GetAltitude(DiIntersect* di) = 0;

        static u32 m_backface_mask; /* 0x474e68 (.sdata, 32); CGrid::GetAltitude sets 32 */
    protected: /* CDIPoly::GetAltitude 0x21e23c reads the points */
        CPnt4D* m_pts;
        /* @socom-skeleton decl Q23zdb3CDI */
public:
        virtual ~CDI();
        virtual void Allocate(int);
        int GetEdgeIntersects(CPnt3D *, CPnt3D *, CPnt3D *);
        int GetEdgeIntersectsY(CPnt3D *, CPnt3D *);
        void SetEdgeVecsAndNorm();
        unsigned int Release();
        /* @socom-skeleton end Q23zdb3CDI */
    };

    class CDIVector : public std::vector<CDI*>
    {
    public:
        /* port: Exists(CDI*) is not declared: the ELF has only Exists__Q23zdb9CDIVectorFPCQ23zdb3CDI (the region below) */
        /* inline in CNode's ctor (0x22862c): stop at the first hit, no back faces */
        CDIVector() : m_bStopAtFirstIntersection(1), m_bReturnBackFaceIntersections(0), m_padding(0) {}
        u8 m_bStopAtFirstIntersection : 1; /* DWARF +0xc bit 0: CGrid::NodeGetIntersect(Batch) end a node's DI loop at its first hit */
        u8 m_bReturnBackFaceIntersections : 1; /* DWARF +0xc bit 1: CDI::m_backface_mask 0x30 instead of 0x20 (the seal ctor 0x2584cc sets it on its skeleton) */
        u8 m_padding : 6;
        /* @socom-skeleton decl Q23zdb9CDIVector */
public:
        bool Exists(const zdb::CDI *);
        /* @socom-skeleton end Q23zdb9CDIVector */
    };

    class CDIPoly : public CDI
    {
        
	/* @socom-skeleton decl Q23zdb7CDIPoly */
public:
	virtual ~CDIPoly();
	virtual bool GetIntersect(zdb::DiIntersect *);
	virtual bool GetAltitude(zdb::DiIntersect *);
	CDIPoly();
	/* @socom-skeleton end Q23zdb7CDIPoly */
    };
}
/* @socom-skeleton decl 11CMaterialEx */
/* A soil/material record from the mission's materials reader (SOILS). No DWARF record:
 * the 60-byte layout is from the constructor 0x21f350, ReadMaterials 0x21e730 and
 * SetDefaultMaterial 0x21e4d0; member names follow the reader tags (port: names guessed). */
class CMaterialEx
{
public:
	CMaterialEx();

	char* m_name; /* +0x00 NAME (zstrdup) */
	char* m_decal; /* +0x04 DECAL (zstrdup) */
	CSnd* m_step_sound; /* +0x08 STEPSOUND */
	CSnd* m_stealth_step_sound; /* +0x0c STEALTH_STEPSOUND */
	CSnd* m_crawl_sound; /* +0x10 CRAWLSOUND */
	CSnd* m_land_sound; /* +0x14 LANDSOUND */
	int m_weapon_anim; /* +0x18 WEAPONANIM: index of another material */
	float m_opacity; /* +0x1c OPACITY, 1.0 */
	float m_penetration; /* +0x20 PENETRATION */
	float m_ricochet; /* +0x24 RICOCHET */
	float m_elasticity_coeff; /* +0x28 ELASTICITY_COEFF */
	float m_impact_radius_mod; /* +0x2c IMPACT_RADIUS_MOD, 1.0 */
	float m_stealth_factor; /* +0x30 STEALTH_FACTOR, 0.5 */
	float m_foot_step_offset; /* +0x34 FOOT_STEP_OFFSET */
	unsigned int m_volumetric : 1; /* +0x38 bit 0 VOLUMETRIC */
	unsigned int m_liquid : 1; /* bit 1 LIQUID */
	unsigned int m_underwater : 1; /* bit 2 UNDERWATER */
	unsigned int m_particle_system : 1; /* bit 3: set only on the PARTICLE_SYSTEM default */
	unsigned int m_pickup : 1; /* bit 4 PICKUP */
	unsigned int m_reserved : 27; /* bits 5-31: copied by SetDefaultMaterial, never read here */
};
/* @socom-skeleton end 11CMaterialEx */
/* @socom-skeleton decl 16CMaterialExArray */
class CMaterialExArray
{
public:
	static int ResolveMaterialIndex(const char *);
	static int ResolveDecalMaterialIndex(const char *, int);
	static bool UnInit(); /* static bool: 0x21f070 reads no this and returns 0/1 */
	static void CreateDefaultMaterials();
	static CMaterialEx* GetWeaponAnimMaterialEx(unsigned int); /* static: a0 is the index (0x21ed50) */
	static bool ReadMaterials(CRdrFile *); /* bool: 0x21e730 returns 0/1 */
	static void SetDefaultMaterial(int);
	static std::vector<CMaterialEx*> m_materialex_list; /* vector<P11CMaterialEx> (dtor 0x21f1a0) */
	static std::map<std::string, int> m_materialex_map; /* map<string, i> (find 0x21f720, find_or_insert 0x21f410) */
};
/* @socom-skeleton end 16CMaterialExArray */
/* @socom-skeleton decl Q23zdb7CDIBBox */
namespace zdb {
class CDIBBox : public zdb::CDI
{
public:
	CBBox* m_box; /* +0x24 (CDIBBox is 40 bytes, SetDIBBox 0x22c420): the owner node's bbox (no DWARF record; port: name guessed) */
	virtual ~CDIBBox();
	virtual bool GetIntersect(zdb::DiIntersect *);
	virtual bool GetAltitude(zdb::DiIntersect *);
	CDIBBox();
	static void SetCDIBBox();
};
}
/* @socom-skeleton end Q23zdb7CDIBBox */
#endif