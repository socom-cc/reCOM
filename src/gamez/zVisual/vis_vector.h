#ifndef VIS_VECTOR_H
#define VIS_VECTOR_H
#include <vector>

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

	// TODO: Implement and use RTArray<T> as base class
	// A vector will be used for now
	class CDecalPool : public std::vector<CDecal*>
	{
	public:
		void RecycleTick();
		/* @socom-skeleton decl Q23zdb10CDecalPool */
public:
		void Init(unsigned int, unsigned int);
		void Get(bool);
		/* @socom-skeleton end Q23zdb10CDecalPool */
	};

	class CMeshDecalPool : public std::vector<CMeshDecal*>
	{
	public:
		void RecycleTick();
		/* @socom-skeleton decl Q23zdb14CMeshDecalPool */
public:
		void Init(unsigned int, unsigned int);
		void Uninit();
		/* @socom-skeleton end Q23zdb14CMeshDecalPool */
	};
}
#endif