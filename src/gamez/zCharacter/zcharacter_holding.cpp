/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body __ct__14CCharacterTypeFv */
/* held from src/gamez/zCharacter/char_type.cpp:23 */
CCharacterType::CCharacterType()
{
    m_name = NULL;
    m_ref_count = 0;
    m_model_file = NULL;
    m_model_file = NULL;
    m_parentID = 0;
    m_model = NULL;

    m_weapons.reserve(8);

    m_controller_id = 0;
}
