#ifndef GRAPH_EDGE_H
#define GRAPH_EDGE_H
#include "gamez/zSystem/zsys_primitive.h"

class CGNode;

class CGEdge
{
public:
	CGEdge(CGNode* first, CGNode* second, f32 padding);

	bool Delete();
	/* @socom-skeleton decl 6CGEdge */
public:
	virtual ~CGEdge();
	void Delete(CGEdge *);
	/* @socom-skeleton end 6CGEdge */
};
#endif