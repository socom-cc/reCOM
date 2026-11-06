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

/* @socom-skeleton body LoadDlgObjects__FRQ23std60vector<P13CDesignDlgObj,Q23std27allocator<P13CDesignDlgObj>>P5_zrdrPcPFP5_zrdrPc_P11CButtonSpec */
/* held from src/gamez/zUI/zui_spec.cpp:120 */
void LoadDlgObjects(std::vector<CDesignDlgObj*>& objects, _zrdr* reader, char* name, CButtonSpec*(*SpecGetter)(_zrdr*, char*))
{
    auto dlg_object = zrdr_findtag(reader, name);

    for (u32 i = 1; i < dlg_object->array->integer - 1; i++)
    {
        auto tag = &dlg_object->array[i];
        
        char* obj_name = zrdr_findstring(tag, "NAME");
        char* obj_type = zrdr_findstring(tag, "TYPE");
        s32 obj_xpos = 0;
        s32 obj_ypos = 0;

        zrdr_findint (tag, "XPOS", &obj_xpos);
        zrdr_findint (tag, "YPOS", &obj_ypos);

        auto spec_tag = zrdr_findtag(tag, "SPEC");

        if (spec_tag)
        {
            CDlgObjSpec* spec = SpecGetter(spec_tag, obj_name);

            if (spec)
            {
                objects.resize(objects.size() + 1);
            }
        }
    }
}
