#ifndef ZVISUAL_LOCAL_H
#define ZVISUAL_LOCAL_H
#include <vector>

#include "gamez/zRender/zrender.h" /* band element types (zdb::CLOD_band ...) */

namespace zdb
{
	class CSaveLoad;
}
/* @socom-skeleton decl 8CVisBase */
class CVisBase
{
public:
	static int m_instance_count;

	/* layout: __ct__8CVisBaseFUib (0x30d470) and its inlined copy in hookupVisuals
	   (0x30a110: new(0x14)); the earlier zdb::CVisBase in zvis.h had these members
	   in the wrong namespace */
	CVisBase(unsigned int size, bool external);
	~CVisBase();

	_word128* m_data_buffer; /* +0x00: allocated by the constructor unless `external` */
	s32 m_buffer_count;      /* +0x04 */
	u32 m_data_size;         /* +0x08 */
	u32 m_node_ofs;          /* +0x0c; port: unproven (not set by the constructor) */
	bool m_active;           /* +0x10: the constructor flag; the destructor frees m_data_buffer only when false */
};
/* @socom-skeleton end 8CVisBase */
/* @socom-skeleton decl Q23zdb11CLOD_Object */
namespace zdb {
class CLOD_Object : public std::vector<CLOD_band>
{
public:
	CLOD_Object();
	~CLOD_Object();
	void Read(zdb::CSaveLoad *);
	s32 m_bandMax; /* DWARF zdb::CLOD_Object +12 */
};
}
/* @socom-skeleton end Q23zdb11CLOD_Object */
/* @socom-skeleton decl Q23zdb15CLightMapVector */
namespace zdb {
class CLightMapVector : public std::vector<unsigned int> /* port: element type from MSL pointer storage in DWARF; real element unproven */
{
public:
};
}
/* @socom-skeleton end Q23zdb15CLightMapVector */
/* @socom-skeleton decl Q23zdb16CMaterial_Object */
namespace zdb {
class CMaterial_Object : public std::vector<CMaterial_band>
{
public:
	CMaterial_Object();
	~CMaterial_Object();
	void Read(zdb::CSaveLoad *);
	s32 m_bandMax; /* DWARF zdb::CMaterial_Object +12 */
};
}
/* @socom-skeleton end Q23zdb16CMaterial_Object */
/* @socom-skeleton decl Q23zdb16CPreLight_Object */
namespace zdb {
class CPreLight_Object : public std::vector<CPreLight_band>
{
public:
	CPreLight_Object();
	~CPreLight_Object();
	s32 m_bandMax; /* DWARF zdb::CPreLight_Object +12 */
};
}
/* @socom-skeleton end Q23zdb16CPreLight_Object */
/* @socom-skeleton decl Q23zdb24CScrollingTexture_Object */
namespace zdb {
class CScrollingTexture_Object : public std::vector<CScrollingTexture_band>
{
public:
	CScrollingTexture_Object();
	~CScrollingTexture_Object();
	void Read(zdb::CSaveLoad *);
	s32 m_bandMax; /* DWARF zdb::CScrollingTexture_Object +12 */
};
}
/* @socom-skeleton end Q23zdb24CScrollingTexture_Object */
/* @socom-skeleton decl Q23zdb15CSubSurf_Object */
namespace zdb {
class CSubSurf_Object : public std::vector<CSubSurf_band>
{
public:
	CSubSurf_Object();
	~CSubSurf_Object();
	s32 m_bandMax; /* DWARF zdb::CSubSurf_Object +12 */
};
}
/* @socom-skeleton end Q23zdb15CSubSurf_Object */

namespace zdb {
/* DWARF zdb::CProjectedMap_Object: 16 bytes, base std::vector (MSL __vector_pod<unsigned int>) */
class CProjectedMap_Object : public std::vector<unsigned int> /* port: element type from MSL pointer storage in DWARF; real element unproven */
{
public:
	s32 m_bandMax;
};
}
#endif