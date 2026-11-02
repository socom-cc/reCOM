/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body m_modelToWorld__Q23zdb7CVisual */
/* held from src/gamez/zVisual/vis_main.cpp:16 */
CMatrix zdb::CVisual::m_modelToWorld;

/* @socom-skeleton body m_instance_count__Q23zdb8CVisBase */
/* held from src/gamez/zVisual/vis_main.cpp:215 */
namespace zdb {
u32 CVisBase::m_instance_count = 0;
}

/* @socom-skeleton body __ct__Q23zdb8CVisBaseFUi */
/* held from src/gamez/zVisual/vis_main.cpp:223 */
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

/* @socom-skeleton body Exists__Q23zdb13CVisualVectorFPCQ23zdb7CVisual */
/* held from src/gamez/zVisual/vis_main.cpp:478 */
namespace zdb {
bool CVisualVector::Exists(const CVisual* visual)
	{
		for (auto it = begin(); it != end(); it++)
		{
			if (*it == visual)
				return true;
		}

		return false;
	}
}

/* @socom-skeleton body __ct__Q23zdb8CSubMeshFv */
/* held from src/gamez/zVisual/vis_mesh.cpp:33 */
namespace zdb {
CSubMesh::CSubMesh()
    {

    }
}
