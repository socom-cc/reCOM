/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include "zui.h"
#include "gamez/zReader/zrdr.h"
#include "gamez/zTwoD/ztwod.h"

/* @socom-skeleton body __ct__14CGameDlgDesignFv */
/* held from src/gamez/zUI/zui_spec.cpp:6 */
CGameDlgDesign::CGameDlgDesign()
{
    /* 0x380e10: empty vectors and strings */
    m_useMpeg = false;
    m_fontlib = true; /* port: unproven - the ctor leaves +0x50 unset; LoadFromRdr always writes it */
}
