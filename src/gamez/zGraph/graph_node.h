#ifndef GRAPH_NODE_H
#define GRAPH_NODE_H

/* port: forward declarations for names this header uses */
class CGEdge;
#include <list>
#include "gamez/zSystem/zsys_primitive.h"

class CGNode /* no DWARF definition: layout from the ctor 0x20f780 (36 bytes, CGraph::CreateNode) */
{
public:
	CGNode(const char* name);
	virtual ~CGNode(); /* __vt__6CGNode 0x471de0 slot 0 */

	CGEdge* FindEdge(CGNode* node);

	void SetName(const char* name);

	char* m_name; /* +0x4 (SetName 0x20f650) */
	u32 m_unk_08; /* +0x8: zeroed by the ctor; port: unproven (tree/route use not mapped) */
	const void* m_nodeEx; /* +0xc: the owner's record (CGraph::GetNodeByNodeEx 0x20e8b0; a CAiMap::link or region) */
	std::list<CGEdge*> m_edges; /* +0x10 (FindEdge 0x20f550, CreateEdge 0x20ea10) */
	u32 m_unk_1c; /* +0x1c: zeroed by the ctor; port: unproven */
	u32 m_unk_20; /* +0x20: zeroed by the ctor; port: unproven */
};

class CGNodeEx : CGNode {};
#endif