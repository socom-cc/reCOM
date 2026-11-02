#ifndef ZINTERSECT_H
#define ZINTERSECT_H
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
        CPnt3D m_norm;
        CNode* m_node;
        /* @socom-skeleton decl Q23zdb15IntersectStruct */
public:
        unsigned int GetMaterial();
        unsigned int GetRegion();
        unsigned char IsInside();
        void GetIntersectedEdgePointsY(CPnt3D *);
        void GetIntersectedEdgePoints(CPnt3D *, CPnt3D *);
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
    private:
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
        bool Exists(CDI* di);
    };

    class CDIPoly : public CDI
    {
        
	/* @socom-skeleton decl Q23zdb7CDIPoly */
public:
	virtual ~CDIPoly();
	virtual void GetIntersect(zdb::DiIntersect *);
	virtual void GetAltitude(zdb::DiIntersect *);
	CDIPoly();
	/* @socom-skeleton end Q23zdb7CDIPoly */
    };
}
/* @socom-skeleton decl 11CMaterialEx */
class CMaterialEx
{
public:
	CMaterialEx();
};
/* @socom-skeleton end 11CMaterialEx */
/* @socom-skeleton decl 16CMaterialExArray */
class CMaterialExArray
{
public:
	static int ResolveMaterialIndex(const char *);
	static int ResolveDecalMaterialIndex(const char *, int);
	void UnInit();
	static void CreateDefaultMaterials();
	void GetWeaponAnimMaterialEx(unsigned int);
	static void ReadMaterials(CRdrFile *);
	static void SetDefaultMaterial(int);
	static int m_materialex_list[3];
	static unsigned char m_materialex_map[16];
};
/* @socom-skeleton end 16CMaterialExArray */
/* @socom-skeleton decl Q23zdb7CDIBBox */
namespace zdb {
class CDIBBox : public zdb::CDI
{
public:
	virtual ~CDIBBox();
	virtual void GetIntersect(zdb::DiIntersect *);
	virtual void GetAltitude(zdb::DiIntersect *);
	CDIBBox();
	static void SetCDIBBox();
};
}
/* @socom-skeleton end Q23zdb7CDIBBox */
#endif