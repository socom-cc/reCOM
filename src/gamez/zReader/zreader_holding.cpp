/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body buffer */
/* held from src/gamez/zReader/zrdr_file.cpp:7 */
char* buffer = NULL;

/* @socom-skeleton body zrdr_init */
/* held from src/gamez/zReader/zrdr_main.cpp:11 */
bool zrdr_init = false;

/* @socom-skeleton body warnonce */
/* held from src/gamez/zReader/zrdr_main.cpp:12 */
bool warnonce = false;

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
bool _zrdr::IsArray() const
{
	return type == ZRDR_ARRAY;
}

/* @socom-skeleton body IsString__5_zrdrCFv */
/* held from src/gamez/zReader/zrdr_main.cpp:44 */
bool _zrdr::IsString() const
{
	return type == ZRDR_STRING;
}

/* @socom-skeleton body GetInt__5_zrdrCFv */
/* held from src/gamez/zReader/zrdr_main.cpp:69 */
int _zrdr::GetInt() const
{
	if (type == ZRDR_INTEGER)
		return integer;
	else if (type == ZRDR_REAL)
		return static_cast<s32>(real);

	return 0;
}

/* @socom-skeleton body GetType__5_zrdrCFv */
/* held from src/gamez/zReader/zrdr_main.cpp:79 */
ZRDR_TYPE _zrdr::GetType() const
{
	return static_cast<ZRDR_TYPE>(type);
}

/* @socom-skeleton body Get__5_zrdrCFi */
/* held from src/gamez/zReader/zrdr_main.cpp:84 */
_zrdr* _zrdr::Get(s32 offset) const
{
	u32 len = 0;

	if (IsArray())
		len = array->integer - 1;

	if (offset < len)
		return &array[offset + 1];

	return NULL;
}

/* @socom-skeleton body zrdr_findtag__FP5_zrdrPCc */
/* held from src/gamez/zReader/zrdr_main.cpp:102 */
_zrdr* zrdr_findtag(_zrdr* reader, const char* name)
{
	return zrdr_findtag_startidx(reader, name, 1);
}

/* @socom-skeleton body zrdr_findtag_startidx__FP5_zrdrPCcUi */
/* held from src/gamez/zReader/zrdr_main.cpp:107 */
_zrdr* zrdr_findtag_startidx(_zrdr* reader, const char* name, u32 startidx)
{
	if (!reader)
		return NULL;

	if (!reader->IsArray())
		return NULL;
	
	for (u32 length = reader->array->integer; startidx < length; startidx++)
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
char* zrdr_findstring(_zrdr* reader, const char* name)
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
bool zrdr_findreal(_zrdr* reader, const char* name, f32* output, s32 startidx)
{
	_zrdr* tag = zrdr_findtag_startidx(reader, name, 1);

	if (!tag)
		return false;

	if (tag->type != ZRDR_ARRAY)
		return false;

	if (tag->array->integer < startidx + 1)
		return false;

	for (u32 i = 0; i < startidx; i++)
	{
		f32 real = 0.0f;
		_zrdr* node = &tag->array[startidx];

		if (node->type == ZRDR_REAL)
			real = node->real;

		if (node->type == ZRDR_INTEGER)
			real = static_cast<f32>(node->integer);

		*output = real;
	}

	return true;
}

/* @socom-skeleton body zrdr_findint__FP5_zrdrPCcPii */
/* held from src/gamez/zReader/zrdr_main.cpp:212 */
bool zrdr_findint(_zrdr* reader, const char* name, s32* output, s32 startidx)
{
	_zrdr* tag = zrdr_findtag_startidx(reader, name, 1);

	if (!tag)
		return false;

	if (tag->type != ZRDR_ARRAY)
		return false;

	if (tag->array->integer < startidx + 1)
		return false;

	for (u32 i = 0; i < startidx; i++)
	{
		s32 integer = 0;
		_zrdr* node = tag->array;

		if (node->type == ZRDR_REAL)
			integer = static_cast<s32>(node->real);

		if (node->type == ZRDR_INTEGER)
			integer = node->integer;

		*output = integer;
	}

	return true;
}

/* @socom-skeleton body zrdr_finduint__FP5_zrdrPCcPUii */
/* held from src/gamez/zReader/zrdr_main.cpp:242 */
bool zrdr_finduint(_zrdr* reader, const char* name, u32* output, s32 startidx)
{
	_zrdr* tag = zrdr_findtag_startidx(reader, name, startidx);
	return zrdr_toINT(tag, reinterpret_cast<s32*>(output), startidx);
}

/* @socom-skeleton body _zrdr_nexttag__FP5_zrdrPCcUiP5_zrdr */
/* held from src/gamez/zReader/zrdr_main.cpp:409 */
_zrdr* _zrdr_nexttag(_zrdr* reader, const char* name, size_t size, _zrdr* other)
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
s32 defcount = 0;

/* @socom-skeleton body init */
/* held from src/gamez/zReader/zrdr_parse.cpp:12 */
bool init = false;
