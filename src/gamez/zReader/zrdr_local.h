#ifndef ZREADER_LOCAL_H
#define ZREADER_LOCAL_H
#include <stack>
#include <vector>

#include "zrdr.h"

#include <ctype.h>

#define zrdr_alloc(count, size) (_zrdr*)zcalloc(count, size)

bool _NeedQuotes(_zrdr* reader);
bool _OutputASCII(FILE* out, _zrdr* reader, s32 offset);

class CRdrEditor : public CRdrFile
{
public:
	bool push(const char* tag);
	bool pop();

	bool addint(const char* tag, s32 value);
	bool addintnode(s32 value);
	bool addSTRING(const char* tag, const char* value);
	bool addPNT3D(const char* tag, const PNT3D& value);
	bool addrdrnode(_zrdr* node);
	bool addstringnode(const char* node);

	std::stack<std::vector<_zrdr*>> m_stack;
	/* @socom-skeleton decl 10CRdrEditor */
public:
	CRdrEditor();
	~CRdrEditor();
	/* @socom-skeleton end 10CRdrEditor */
};
#endif