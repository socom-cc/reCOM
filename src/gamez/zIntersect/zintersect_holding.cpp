/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include "gamez/zIntersect/zintersect.h"

/* @socom-skeleton body Exists__Q23zdb9CDIVectorFPQ23zdb3CDI */
/* held from src/gamez/zIntersect/int_main.cpp:103 */
namespace zdb {
/* port: retargeted to the ELF's Exists__Q23zdb9CDIVectorFPCQ23zdb3CDI; the held loop never
   advanced its iterator - 0x224420 scans [begin, end) and returns found != end */
bool CDIVector::Exists(const CDI* di)
    {
        for (auto it = begin(); it != end(); ++it)
        {
            if (*it == di)
            {
                return true;
            }
        }

        return false;
    }
}
