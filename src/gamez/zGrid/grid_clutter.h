#ifndef GRID_CLUTTER_H
#define GRID_CLUTTER_H
#include "gamez/zNode/znode.h"

namespace zdb
{
	class CClutter
	{
	private:
		CNode* m_node;
		/* @socom-skeleton decl Q23zdb8CClutter */
public:
		CClutter(zdb::CNode *);
		void Read(zar::CZAR *);
		void GetTranslate();
		void GetMatrix();
		void Render(CPnt3D *);
		/* @socom-skeleton end Q23zdb8CClutter */
	};

	class CClutterList : public std::list<CClutter*>
	{

	/* @socom-skeleton decl Q23zdb12CClutterList */
public:
	void Add(zdb::CClutter *);
	void Render(zdb::CCell *);
	void Free();
	/* @socom-skeleton end Q23zdb12CClutterList */
	};
}

#endif