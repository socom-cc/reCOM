#ifndef ZVISUAL_LOCAL_H
#define ZVISUAL_LOCAL_H
/* @socom-skeleton decl 8CVisBase */
class CVisBase
{
public:
	static int m_instance_count;
};
/* @socom-skeleton end 8CVisBase */
/* @socom-skeleton decl Q23zdb11CLOD_Object */
namespace zdb {
class CLOD_Object : public std::vector
{
public:
	CLOD_Object();
	~CLOD_Object();
	void Read(zdb::CSaveLoad *);
};
}
/* @socom-skeleton end Q23zdb11CLOD_Object */
/* @socom-skeleton decl Q23zdb15CLightMapVector */
namespace zdb {
class CLightMapVector : public std::vector
{
public:
};
}
/* @socom-skeleton end Q23zdb15CLightMapVector */
/* @socom-skeleton decl Q23zdb16CMaterial_Object */
namespace zdb {
class CMaterial_Object : public std::vector
{
public:
	CMaterial_Object();
	~CMaterial_Object();
	void Read(zdb::CSaveLoad *);
};
}
/* @socom-skeleton end Q23zdb16CMaterial_Object */
/* @socom-skeleton decl Q23zdb16CPreLight_Object */
namespace zdb {
class CPreLight_Object : public std::vector
{
public:
	CPreLight_Object();
	~CPreLight_Object();
};
}
/* @socom-skeleton end Q23zdb16CPreLight_Object */
/* @socom-skeleton decl Q23zdb24CScrollingTexture_Object */
namespace zdb {
class CScrollingTexture_Object : public std::vector
{
public:
	CScrollingTexture_Object();
	~CScrollingTexture_Object();
	void Read(zdb::CSaveLoad *);
};
}
/* @socom-skeleton end Q23zdb24CScrollingTexture_Object */
/* @socom-skeleton decl Q23zdb15CSubSurf_Object */
namespace zdb {
class CSubSurf_Object : public std::vector
{
public:
	CSubSurf_Object();
	~CSubSurf_Object();
};
}
/* @socom-skeleton end Q23zdb15CSubSurf_Object */
#endif