/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include <string.h>
#include "gamez/zReader/zrdr.h"

/* @socom-skeleton body buffer */
/* held from src/gamez/zReader/zrdr_file.cpp:7 */
/* port: deleted (was #if 0): not zReader's: the ELF's buffer is a size-0 LOCAL label; nothing uses it */

/* @socom-skeleton body zrdr_init */
/* held from src/gamez/zReader/zrdr_main.cpp:11 */
/* port: deleted (was #if 0): not in the ELF; nothing uses it */

/* @socom-skeleton body warnonce */
/* held from src/gamez/zReader/zrdr_main.cpp:12 */
/* port: deleted (was #if 0): duplicate: warnonce$734 is a local static of _zrdr::Clone (zrdr_main.cpp) */

/* @socom-skeleton body __ct__5_zrdrFv */
/* held from src/gamez/zReader/zrdr_main.cpp:17 */
_zrdr::_zrdr()
{
	/* 0x23e380: the ELF clears only isclone and packed. Port deviation, kept: type, unused,
	 * length and array are zeroed too, so a CRdrFile freed after a failed read (ai_mapio.cpp's
	 * ReadPacked failure -> zrdr_free; the port's file layer can fail where the disc does not)
	 * runs zrdr_freearray on a NULL reader instead of heap garbage (CRdrFile's ctor 0x23cf30
	 * leaves them unset as well) */
	type = ZRDR_NULL;
	isclone = false;
	packed = false;
	unused = 0;
	length = 0;

	array = NULL;
}

/* @socom-skeleton body IsArray__5_zrdrCFv */
/* held from src/gamez/zReader/zrdr_main.cpp:39 */
/* port: deleted (was #if 0): inline in zrdr.h */

/* @socom-skeleton body IsString__5_zrdrCFv */
/* held from src/gamez/zReader/zrdr_main.cpp:44 */
/* port: deleted (was #if 0): inline in zrdr.h */

/* @socom-skeleton body GetInt__5_zrdrCFv */
/* held from src/gamez/zReader/zrdr_main.cpp:69 */
/* port: deleted (was #if 0): inline in zrdr.h */

/* @socom-skeleton body GetType__5_zrdrCFv */
/* held from src/gamez/zReader/zrdr_main.cpp:79 */
/* port: deleted (was #if 0): inline in zrdr.h */

/* @socom-skeleton body Get__5_zrdrCFi */
/* held from src/gamez/zReader/zrdr_main.cpp:84 */
/* port: deleted (was #if 0): inline in zrdr.h (ELF Get__5_zrdrFUi) */

/* @socom-skeleton body defcount */
/* held from src/gamez/zReader/zrdr_parse.cpp:11 */
/* port: deleted (was #if 0): duplicate: defcount$840 is a local static in zrdr_parse.cpp */

/* @socom-skeleton body init */
/* held from src/gamez/zReader/zrdr_parse.cpp:12 */
/* port: deleted (was #if 0): duplicate: init$735/init$841 are local statics in zrdr_main.cpp/zrdr_parse.cpp */
