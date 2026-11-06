#ifndef ASSETLIB_VECTOR_H
#define ASSETLIB_VECTOR_H
#include <list>

namespace zdb
{
	class CAssetLib;
	class CNode;
}

/* CModel::m_list: the model's instances (CNode::CreateInstance 0x229360 appends them;
 * SetParentHasVisuals 0x227c80 walks them) */
class CRefList : public std::list<zdb::CNode*> {};
#endif