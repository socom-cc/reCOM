#ifndef ZWEAPON_PROJECTILELIST_H
#define ZWEAPON_PROJECTILELIST_H

/* port: forward declarations for names this header uses */
class CZAmmo;
class CZWeapon;
#include "vector"

#include "gamez/zIntersect/zintersect.h"
#include "gamez/zSystem/zsys_primitive.h"
/* @socom-skeleton decl forward */
class PlacedExplosive;
/* @socom-skeleton end forward */

class CZProjectile;

class CZProjectileList
{
public:
    bool GetNextDirectFireDI(zdb::DiIntersect** di, s32* free_handle);
    bool GetNextIndirectFireDI(zdb::DiIntersect** di, s32* handle);
	
    CZProjectile* m_projectiles;
    std::vector<CZProjectile*> m_explosives;
	
    u8* m_used;

    s32 m_firstfree;
    s32 m_lastused;
    s32 m_size;

    zdb::DiIntersect* m_directFireDI[60];
    u8 m_directFireDIUsed[60];
    s32 m_direct_firstfree;

    zdb::DiIntersect* m_indirectFireDI[30];
    u8 m_indirectFireDIUsed[60];
    s32 m_indirect_firstfree;
    /* @socom-skeleton decl 16CZProjectileList */
public:
    CZProjectileList(int);
    ~CZProjectileList();
    void Init();
    void Clear();
    void Clear(int);
    void UnInit();
    CZProjectile * GetNextFreeProjectile();
    void FreeIdx(int);
    void FindLastUsed();
    void PreTick(float);
    void PostTick(float);
    void NetRemoveProjectile(CZProjectile *);
    void RemoveProjectile(CZProjectile *);
    void RemoveExplosive(PlacedExplosive *);
    int GetNumRemoteExplosives(int);
    void ReleaseDirectFireDI(zdb::DiIntersect **, int *);
    void ReleaseIndirectFireDI(zdb::DiIntersect **, int *);
    CZProjectile * AcquireProjectile(CZWeapon &, CZAmmo &);
    /* @socom-skeleton end 16CZProjectileList */
};
#endif