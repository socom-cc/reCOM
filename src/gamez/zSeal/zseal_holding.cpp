/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body seal_init */
/* held from src/gamez/zSeal/seal.cpp:6 */
bool seal_init = false;

/* @socom-skeleton body m_crawl1stperson_amplitude__9CSealCtrl */
/* held from src/gamez/zSeal/seal_control.cpp:5 */
f32 CSealCtrl::m_crawl1stperson_amplitude = 0.0f;

/* @socom-skeleton body m_crawl1stperson_rate__9CSealCtrl */
/* held from src/gamez/zSeal/seal_control.cpp:6 */
f32 CSealCtrl::m_crawl1stperson_rate = 0.0f;

/* @socom-skeleton body StopRumbler__9CSealCtrlFv */
/* held from src/gamez/zSeal/seal_control.cpp:8 */
void CSealCtrl::StopRumbler()
{
    CPad* pad;
    
    if (m_padid < 2)
    {
        pad = CInput::m_pads[m_padid];
    }
    else
    {
        pad = NULL;
    }

    if (pad)
    {
        pad->m_ActData = 0;
        pad->m_IsAnalog = false;
    }

    m_highrumbletime = 0.0f;
    m_rumbletime = 0.0f;
    m_rumblestr = 0.0f;

    CInput::Flush();
    CZSealBody::StopAllHeartbeatSounds();
}

/* @socom-skeleton body Begin__8CTSelectFP14_zanim_cmd_hdr */
/* held from src/gamez/zSeal/seal_tasks.cpp:320 */
void CTSelect::Begin(_zanim_cmd_hdr* header)
{

}

/* @socom-skeleton body End__8CTSelectFP14_zanim_cmd_hdr */
/* held from src/gamez/zSeal/seal_tasks.cpp:325 */
void CTSelect::End(_zanim_cmd_hdr* header)
{

}
