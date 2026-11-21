/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include <string.h>
#include "gamez/zReader/zrdr.h"

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
