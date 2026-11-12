#ifndef VIS_VECTOR_H
#define VIS_VECTOR_H
#include <vector>

#include "rt/rtarray.h"
#include "gamez/zSystem/zsys_primitive.h"

namespace zdb
{
	class CVisual;
	class CDecal;
	class CMeshDecal;

	class CVisualVector : public std::vector<CVisual*>
	{
	public:
		bool Exists(const CVisual* visual);
	};

	/* The decal pools (20 bytes each: CDecal::m_tempPool 0x511ba0, m_permPool 0x511bc0,
	 * CMeshDecal::m_tempPool 0x511be0, m_permPool 0x511c00). No DWARF; members from Init
	 * 0x313460, Get 0x3133e0, RecycleTick 0x313360 and CDecal::PutTempDecal 0x313320. The
	 * RTArray holds m_base + m_overflow objects; a decal taken while more than m_base are out
	 * marks one for RecycleTick, which takes the oldest back before the world is drawn. */
	class CDecalPool
	{
	public:
		void RecycleTick();
		/* @socom-skeleton decl Q23zdb10CDecalPool */
public:
		void Init(unsigned int, unsigned int);
		CDecal * Get(bool); /* 0x3133e0 returns the decal (v0), NULL when the pool is empty */
		/* @socom-skeleton end Q23zdb10CDecalPool */

		u32 m_count;              /* +0: decals out of the pool */
		u32 m_base;               /* +4: TEMP_DECAL_POOL / PERM_DECAL_POOL BASE */
		u32 m_overflow;           /* +8: OVERFLOW */
		u32 m_recycle;            /* +12: decals RecycleTick has to take back */
		RTArray<CDecal>* m_array; /* +16 */
	};

	class CMeshDecalPool
	{
	public:
		void RecycleTick();
		/* @socom-skeleton decl Q23zdb14CMeshDecalPool */
public:
		void Init(unsigned int, unsigned int);
		void Uninit();
		/* @socom-skeleton end Q23zdb14CMeshDecalPool */

		u32 m_count;                  /* +0 */
		u32 m_base;                   /* +4 */
		u32 m_overflow;               /* +8 */
		u32 m_recycle;                /* +12 */
		RTArray<CMeshDecal>* m_array; /* +16 */
	};
}
#endif