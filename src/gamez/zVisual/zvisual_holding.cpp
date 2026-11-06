/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include "gamez/zVisual/zvis.h"
#include "gamez/zVisual/vis_vector.h"

/* @socom-skeleton body m_modelToWorld__Q23zdb7CVisual */
/* held from src/gamez/zVisual/vis_main.cpp:16 */
/* port: not in the ELF; NodeSetup stores the pointer m_ModelToWorld (0x30c6ec), defined in vis_main.cpp */
#if 0
CMatrix zdb::CVisual::m_modelToWorld;
#endif

/* @socom-skeleton body m_instance_count__Q23zdb8CVisBase */
/* held from src/gamez/zVisual/vis_main.cpp:215 */
/* port: duplicate of gamez/zVisual/vis_main.cpp (m_instance_count__8CVisBase) */
#if 0
namespace zdb {
u32 CVisBase::m_instance_count = 0;
}
#endif

/* @socom-skeleton body __ct__Q23zdb8CVisBaseFUi */
/* held from src/gamez/zVisual/vis_main.cpp:223 */
/* port: superseded by gamez/zVisual/vis_main.cpp (ELF __ct__8CVisBaseFUib, owner annotation 0x30d470) */
#if 0
namespace zdb {
CVisBase::CVisBase(size_t size)
	{
		m_data_buffer = NULL;
		m_buffer_count = 0;
		m_data_size = size;
		m_instance_count++;
		m_active = true;
	}
}
#endif

/* @socom-skeleton body __ct__Q23zdb8CSubMeshFv */
/* held from src/gamez/zVisual/vis_mesh.cpp:33 */
/* port: not in the ELF; CVisual::Create calls CSubMesh(CMesh*) with NULL (0x30e1e4) */
#if 0
namespace zdb {
CSubMesh::CSubMesh()
    {

    }
}
#endif
