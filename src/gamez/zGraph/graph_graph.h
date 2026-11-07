#ifndef GRAPH_GRAPH_H
#define GRAPH_GRAPH_H

/* port: forward declarations for names this header uses */
class CGRoute;
#include "graph_node.h"
#include "graph_edge.h"
#include "graph_tree.h"

#include "gamez/zUtil/util_systemio.h"

class CGraph /* no DWARF definition: layout from the ctor 0x20ef20 (28 bytes, CGraph::Create) */
{
public:
	CGraph(const char* name);
	~CGraph();

	/* port: the 3-argument Create/Read, member Destroy(), DestroyNode and GetNodeByNodeEx(const
	 * CGNodeEx *) were removed (never defined); the ELF's forms are below */
	static CGraph* Create(const char* name); /* 0x20f1f0 */

	void PopulateTree(CGTree* tree);

	CGEdge* CreateEdge(CGNode* first, CGNode* second);
	CGEdge* FindEdge(CGNode* first, CGNode* second);

	CGNode* CreateNode(const char* name);
	CGNode* GetNodeByIndex(u32 index);
	/* @socom-skeleton decl 6CGraph */
public:
	static CGraph * Create(CFileIO &, void (*)(CGraph *, CGNode *, bool, unsigned int &, void *), void (*)(CGraph *, CGEdge *, bool, unsigned int &, void *), void *); /* 0x20f4b0: NULL when Read fails */
	bool Read(CFileIO &, void (*)(CGraph *, CGNode *, bool, unsigned int &, void *), void (*)(CGraph *, CGEdge *, bool, unsigned int &, void *), void *); /* 0x20f2a0 */
	static void Destroy(CGraph *);
	void DeleteNode(CGNode *);
	CGNode * GetNodeByNodeEx(const void *); /* 0x20e8b0 */
	void BuildTree(CGNode *, float);
	void BuildRoute(CGNode *, CGNode *, CGRoute *);
	static int m_leafTree;
	static int m_treeEdge;
	static int m_treeNode;
	static const int version;
	/* @socom-skeleton end 6CGraph */

	char* m_name;
	std::list<CGNode*> m_nodes; /* +0x4 */
	std::list<CGEdge*> m_edges; /* +0x10 */
};
#endif