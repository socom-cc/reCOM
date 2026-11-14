#ifndef GRAPH_ROUTE_H
#define GRAPH_ROUTE_H
#include "graph_node.h"

/* no DWARF record: 12 bytes, a list of the route's nodes from start to goal (the ctor 0x20f910
   builds only the list; CGraph::BuildRoute fills it) */
class CGRoute
{
public:
	CGRoute();
	~CGRoute();

	void Append(CGNode* node);
	void PostProcess();
	void Clear();

	std::list<CGNode*> m_nodes; /* +0x0; name: port's */
};
#endif