/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include <string.h>
#include "gamez/zReader/zrdr.h"

/* @socom-skeleton body buffer */
/* held from src/gamez/zReader/zrdr_file.cpp:7 */
/* port: not zReader's: the ELF's buffer is a size-0 LOCAL label; nothing uses it */
#if 0
char* buffer = NULL;
#endif

/* @socom-skeleton body zrdr_init */
/* held from src/gamez/zReader/zrdr_main.cpp:11 */
/* port: not in the ELF; nothing uses it */
#if 0
bool zrdr_init = false;
#endif

/* @socom-skeleton body warnonce */
/* held from src/gamez/zReader/zrdr_main.cpp:12 */
/* port: duplicate: warnonce$734 is a local static of _zrdr::Clone (zrdr_main.cpp) */
#if 0
bool warnonce = false;
#endif

/* @socom-skeleton body __ct__5_zrdrFv */
/* held from src/gamez/zReader/zrdr_main.cpp:17 */
_zrdr::_zrdr()
{
	type = ZRDR_NULL;
	isclone = false;
	packed = false;
	unused = 0;
	length = 0;

	array = NULL;
}

/* @socom-skeleton body __ct__5_zrdrFP5_zrdrP7CSTable */
/* held from src/gamez/zReader/zrdr_main.cpp:28 */
_zrdr::_zrdr(_zrdr* other, CSTable* stable)
{
	type = ZRDR_NULL;
	isclone = false;
	packed = false;
	unused = 0;
	length = 0;

	Clone(other, stable);
}

/* @socom-skeleton body IsArray__5_zrdrCFv */
/* held from src/gamez/zReader/zrdr_main.cpp:39 */
/* port: inline in zrdr.h */
#if 0
bool _zrdr::IsArray() const
{
	return type == ZRDR_ARRAY;
}
#endif

/* @socom-skeleton body IsString__5_zrdrCFv */
/* held from src/gamez/zReader/zrdr_main.cpp:44 */
/* port: inline in zrdr.h */
#if 0
bool _zrdr::IsString() const
{
	return type == ZRDR_STRING;
}
#endif

/* @socom-skeleton body GetInt__5_zrdrCFv */
/* held from src/gamez/zReader/zrdr_main.cpp:69 */
/* port: inline in zrdr.h */
#if 0
int _zrdr::GetInt() const
{
	if (type == ZRDR_INTEGER)
		return integer;
	else if (type == ZRDR_REAL)
		return static_cast<s32>(real);

	return 0;
}
#endif

/* @socom-skeleton body GetType__5_zrdrCFv */
/* held from src/gamez/zReader/zrdr_main.cpp:79 */
/* port: inline in zrdr.h */
#if 0
ZRDR_TYPE _zrdr::GetType() const
{
	return static_cast<ZRDR_TYPE>(type);
}
#endif

/* @socom-skeleton body Get__5_zrdrCFi */
/* held from src/gamez/zReader/zrdr_main.cpp:84 */
/* port: inline in zrdr.h (ELF Get__5_zrdrFUi) */
#if 0
_zrdr* _zrdr::Get(s32 offset) const
{
	u32 len = 0;

	if (IsArray())
		len = array->integer - 1;

	if (offset < len)
		return &array[offset + 1];

	return NULL;
}
#endif

/* @socom-skeleton body zrdr_findtag__FP5_zrdrPCc */
/* held from src/gamez/zReader/zrdr_main.cpp:102 */
_zrdr* zrdr_findtag(const _zrdr* reader, const char* name) /* port: zrdr_findtag__FPC5_zrdrPCc */
{
	return zrdr_findtag_startidx(reader, name, 1);
}

/* @socom-skeleton body zrdr_findtag_startidx__FP5_zrdrPCcUi */
/* held from src/gamez/zReader/zrdr_main.cpp:107 */
_zrdr* zrdr_findtag_startidx(const _zrdr* reader, const char* name, s32 startidx) /* port: zrdr_findtag_startidx__FPC5_zrdrPCci */
{
	if (!reader)
		return NULL;

	if (!reader->IsArray())
		return NULL;
	
	for (s32 length = reader->array->integer; startidx < length; startidx++)
	{
		_zrdr* node = &reader->array[startidx];

		if (node->IsArray())
		{
			node = zrdr_findtag_startidx(node, name, 1);

			if (node)
				return node;
		}
		else if (node->IsString() && strcmp(node->string, name) == 0)
			return &node[1];
	}

	return NULL;
}

/* @socom-skeleton body zrdr_findstring__FP5_zrdrPCc */
/* held from src/gamez/zReader/zrdr_main.cpp:133 */
char* zrdr_findstring(const _zrdr* reader, const char* name) /* port: zrdr_findstring__FPC5_zrdrPCc */
{
	auto tag = zrdr_findtag_startidx(reader, name, 1);

	if (!tag)
		return NULL;

	if (tag->type == ZRDR_STRING)
		return tag->string;

	if (tag->type == ZRDR_ARRAY && tag->array[1].type == ZRDR_STRING)
		return tag->array[1].string;

	return NULL;
}

/* @socom-skeleton body zrdr_findreal__FP5_zrdrPCcPfi */
/* held from src/gamez/zReader/zrdr_main.cpp:182 */
bool zrdr_findreal(const _zrdr* reader, const char* name, f32* output, s32 count) /* port: zrdr_findreal__FPC5_zrdrPCcPfi */
{
	/* port: body from 0x23d9d0 - element i + 1 of the tag array goes to output[i]; other types leave it */
	_zrdr* tag = zrdr_findtag_startidx(reader, name, 1);

	if (!tag || tag->type != ZRDR_ARRAY)
		return false;

	if (tag->array->integer < count + 1)
		return false;

	for (s32 i = 0; i < count; i++)
	{
		_zrdr* node = &tag->array[i + 1];

		if (node->type == ZRDR_REAL)
			output[i] = node->real;
		else if (node->type == ZRDR_INTEGER)
			output[i] = static_cast<f32>(node->integer);
	}

	return true;
}

/* @socom-skeleton body zrdr_findint__FP5_zrdrPCcPii */
/* held from src/gamez/zReader/zrdr_main.cpp:212 */
bool zrdr_findint(const _zrdr* reader, const char* name, s32* output, s32 count) /* port: zrdr_findint__FPC5_zrdrPCcPii */
{
	/* port: body from 0x23d8c0 - element i + 1 of the tag array goes to output[i]; other types leave it */
	_zrdr* tag = zrdr_findtag_startidx(reader, name, 1);

	if (!tag || tag->type != ZRDR_ARRAY)
		return false;

	if (tag->array->integer < count + 1)
		return false;

	for (s32 i = 0; i < count; i++)
	{
		_zrdr* node = &tag->array[i + 1];

		if (node->type == ZRDR_REAL)
			output[i] = static_cast<s32>(node->real);
		else if (node->type == ZRDR_INTEGER)
			output[i] = node->integer;
	}

	return true;
}

/* @socom-skeleton body zrdr_finduint__FP5_zrdrPCcPUii */
/* held from src/gamez/zReader/zrdr_main.cpp:242 */
bool zrdr_finduint(const _zrdr* reader, const char* name, u32* output, s32 startidx) /* port: zrdr_finduint__FPC5_zrdrPCcPUii */
{
	_zrdr* tag = zrdr_findtag_startidx(reader, name, 1); /* port: 0x23d6b8 passes 1 */
	return zrdr_toINT(tag, reinterpret_cast<s32*>(output), startidx);
}

/* @socom-skeleton body _zrdr_nexttag__FP5_zrdrPCcUiP5_zrdr */
/* held from src/gamez/zReader/zrdr_main.cpp:409 */
_zrdr* _zrdr_nexttag(const _zrdr* reader, const char* name, s32 size, _zrdr* other) /* port: _zrdr_nexttag__FPC5_zrdrPCciP5_zrdr */
{
	_zrdr* node = reader->array;

	if (node->integer <= 1)
		return NULL;

	if (node == other)
		other = NULL;

	if (node->type == ZRDR_ARRAY)
		return _zrdr_nexttag(node, name, size, other);

	if (node->type == ZRDR_STRING && !other)
	{
		if (strncmp(node->string, name, size) == 0)
			return &node[1];
	}

	return NULL;
}

/* @socom-skeleton body defcount */
/* held from src/gamez/zReader/zrdr_parse.cpp:11 */
/* port: duplicate: defcount$840 is a local static in zrdr_parse.cpp */
#if 0
s32 defcount = 0;
#endif

/* @socom-skeleton body init */
/* held from src/gamez/zReader/zrdr_parse.cpp:12 */
/* port: duplicate: init$735/init$841 are local statics in zrdr_main.cpp/zrdr_parse.cpp */
#if 0
bool init = false;
#endif
