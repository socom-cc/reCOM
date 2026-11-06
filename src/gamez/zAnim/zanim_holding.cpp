/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include "gamez/zAnim/zanim.h"

/* @socom-skeleton body m_LoadFromZAR__10CZAnimMain */
/* held from src/gamez/zAnim/anim_main.cpp:6 */
bool CZAnimMain::m_LoadFromZAR = false;

/* @socom-skeleton body _local_wildcard_ptr */
/* held from src/gamez/zAnim/anim_main.cpp:11 */
/* port: not in the ELF (the binary has _local_wildcard_str in anim_main.cpp); nothing uses it */
#if 0
char* _local_wildcard_ptr = NULL;
#endif

/* @socom-skeleton body zAnimQuadAlignTick__FP14_zanim_cmd_hdrPf */
/* held from src/gamez/zAnim/zanim_cmd_tick.cpp:3 */
bool zAnimQuadAlignTick(_zanim_cmd_hdr* header, f32* dT)
{
    return true;
}

/* @socom-skeleton body zAnimIfTick__FP14_zanim_cmd_hdrPf */
/* held from src/gamez/zAnim/zanim_cmd_tick.cpp:8 */
bool zAnimIfTick(_zanim_cmd_hdr* header, f32* dT)
{
    ZAnim.m_CurSeq->m_IF_NestLevel++;

    while (!CZAnimExpression::ProcExpr(dT))
    {
        _zanim_cmd_hdr* header = NULL;
        bool evaluated = false;

        while (!evaluated)
        {
            if (!ZAnim.CmdValid())
            {
                evaluated = true;
                break;
            }

            if (ZAnim.m_CurSeq)
                header = reinterpret_cast<_zanim_cmd_hdr*>(ZAnim.m_CurSeq->cmd_pc);

            if (header->data_type != ZAnim.m_cmd_else.data_type)
                if (header->data_type != ZAnim.m_cmd_elseif.data_type)
                    if (header->data_type != ZAnim.m_cmd_endif.data_type)
                        continue;

            if (header->data_size == ZAnim.m_CurSeq->m_IF_NestLevel)
            {
                evaluated = true;
                if (header->data_type == ZAnim.m_cmd_endif.data_type)
                    ZAnim.m_CurSeq->m_IF_NestLevel--;
            }
        }

        if (!ZAnim.m_CurSeq)
            header = NULL;
        else
            header = reinterpret_cast<_zanim_cmd_hdr*>(ZAnim.m_CurSeq->cmd_pc);

        if (header->data_type != ZAnim.m_cmd_elseif.data_type)
            evaluated = true;
    }

    return true;
}

/* @socom-skeleton body zAnimWhileTick__FP14_zanim_cmd_hdrPf */
/* held from src/gamez/zAnim/zanim_cmd_tick.cpp:53 */
bool zAnimWhileTick(_zanim_cmd_hdr* header, f32* dT)
{
    // what does this even mean
    if (header[1].data_type == 0)
    {
        ZAnim.CmdNext(8);
        if (CZAnimExpression::ProcExpr(dT))
            ZAnim.CmdSet(header[1].data_size);
    }

    return true;
}

/* @socom-skeleton body zAnimEndIfTick__FP14_zanim_cmd_hdrPf */
/* held from src/gamez/zAnim/zanim_cmd_tick.cpp:66 */
bool zAnimEndIfTick(_zanim_cmd_hdr* header, f32* dT)
{
    ZAnim.m_CurSeq->m_IF_NestLevel--;
    return true;
}

/* @socom-skeleton body zAnimGoToEndIf__FP14_zanim_cmd_hdrPf */
/* held from src/gamez/zAnim/zanim_cmd_tick.cpp:72 */
bool zAnimGoToEndIf(_zanim_cmd_hdr* header, f32* dT)
{
    return true;
}
