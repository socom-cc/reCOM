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
