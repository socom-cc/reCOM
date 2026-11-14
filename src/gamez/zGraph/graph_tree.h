#ifndef GRAPH_TREE_H
#define GRAPH_TREE_H
#include "graph_node.h"

/* no DWARF record: 20 bytes (operator new 0x14 in CGraph::BuildTree 0x210010); names: port's */
class CGTree
{
public:
	CGTree() : m_parent(NULL), m_node(NULL) {} /* inlined at each new (list, then +0xc / +0x10 zeroed) */
	CGTree* FindNode(CGNode* node); /* returns the tree entry (0x210720) */
	void RemoveChild(CGTree* tree);
	/* @socom-skeleton decl 6CGTree */
public:
	static void Destroy(CGTree *); /* static: a0 is the tree (_release_tree, BuildRoute) */
	~CGTree();
	/* @socom-skeleton end 6CGTree */

	std::list<CGTree*> m_children; /* +0x0 */
	CGTree* m_parent;              /* +0xc */
	CGNode* m_node;                /* +0x10 */
};
#endif