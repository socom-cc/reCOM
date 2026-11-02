#ifndef GRAPH_TREE_H
#define GRAPH_TREE_H
#include "graph_node.h"

class CGTree
{
public:
	CGNode* FindNode(CGNode* node);
	void RemoveChild(CGTree* tree);
	/* @socom-skeleton decl 6CGTree */
public:
	void Destroy(CGTree *);
	~CGTree();
	/* @socom-skeleton end 6CGTree */
};
#endif