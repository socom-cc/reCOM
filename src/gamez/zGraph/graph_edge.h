#ifndef GRAPH_EDGE_H
#define GRAPH_EDGE_H
#include "gamez/zSystem/zsys_primitive.h"

class CGNode;

class CGEdge /* no DWARF definition: layout from the ctor 0x20fa30 (28 bytes, CGraph::CreateEdge) */
{
public:
	CGEdge(CGNode* first, CGNode* second, f32 weight);

	/* port: the member Delete() was removed (never defined); the ELF has only the static Delete(CGEdge *) */
	/* @socom-skeleton decl 6CGEdge */
public:
	virtual ~CGEdge();
	static bool Delete(CGEdge *); /* 0x20f990 returns 0 */
	/* @socom-skeleton end 6CGEdge */

	f32 m_length; /* +0x4: CGraph::Read 0x20f2a0 stores the file's edge length, CAiMap::CreateGraph a path length */
	f32 m_weight; /* +0x8: the ctor argument (CreateEdge passes 1.0); port: name unproven */
	CGNode* m_first; /* +0xc */
	CGNode* m_second; /* +0x10 */
	const void* m_edgeEx; /* +0x14: the owner's record (CAiMap::CreateGraph stores the route); port: name unproven */
	u32 m_unk_18; /* +0x18: not set by the ctor; port: unproven */
};
#endif