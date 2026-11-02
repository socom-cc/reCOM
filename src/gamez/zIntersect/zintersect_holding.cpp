/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body Exists__Q23zdb9CDIVectorFPQ23zdb3CDI */
/* held from src/gamez/zIntersect/int_main.cpp:103 */
namespace zdb {
bool CDIVector::Exists(CDI* di)
    {
        const auto it = begin();

        while (it != end())
        {
            if (*it == di)
            {
                return true;
            }
        }

        return false;
    }
}
