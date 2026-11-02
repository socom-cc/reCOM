/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body MakeYXZ__5CQuatFfffR5CQuat */
/* held from src/gamez/zMath/zmath_main.cpp:96 */
void CQuat::MakeYXZ(f32 x, f32 y, f32 z, CQuat& out)
{
	f32 halfX = x * 0.5f;
	f32 sinHalfX = sinf(halfX);
	halfX = cosf(halfX);

	f32 halfY = x * 0.5f;
	f32 sinHalfY = sinf(halfY);
	halfY = cosf(halfY);

	f32 zMul = sinHalfX * sinHalfY;
	sinHalfX *= halfY;

	f32 zSin = sinf(z * 0.5f);
	f32 zCos = cosf(z * 0.5f);

	out.w = zMul * zSin + halfX * halfY * zCos;
	out.vec.x = sinHalfX * zSin + halfX * sinHalfY * zCos;
	out.vec.y = sinHalfX * zCos - halfX * sinHalfY * zSin;
	out.vec.z = halfX * halfY * zSin - zMul * zCos;
}

/* @socom-skeleton body __ct__7CMatrixFv */
/* held from src/gamez/zMath/zmath_matrix.cpp:3 */
CMatrix::CMatrix()
{
	*this = CMatrix::identity;
}

/* @socom-skeleton body __vc__7CMatrixFi */
/* held from src/gamez/zMath/zmath_matrix.cpp:31 */
const float* CMatrix::operator[](const int row)
{
	return m_matrix[row];
}

/* @socom-skeleton body GetTranslate__7CMatrixCFv */
/* held from src/gamez/zMath/zmath_matrix.cpp:36 */
const float* CMatrix::GetTranslate() const
{
	return m_matrix[3];
}

/* @socom-skeleton body Transform__7CMatrixFP6CPnt3Di */
/* held from src/gamez/zMath/zmath_matrix.cpp:42 */
void CMatrix::Transform(CPnt3D* point, s32 count)
{
	m_matrix[3][0] = point->x;
	m_matrix[3][1] = point->y;
	m_matrix[3][2] = point->z;
	m_matrix[3][3] = 1.0f;
}

/* @socom-skeleton body Multiply__7CMatrixFPC7CMatrixPC7CMatrix */
/* held from src/gamez/zMath/zmath_matrix.cpp:50 */
void CMatrix::Multiply(const CMatrix* first, const CMatrix* second)
{
	// First row
	m_matrix[0][0] = 
		(first->m_matrix[0][0] * second->m_matrix[0][0]) + 
		(first->m_matrix[0][1] * second->m_matrix[1][0]) + 
		(first->m_matrix[0][2] * second->m_matrix[2][0]) + 
		(first->m_matrix[0][3] * second->m_matrix[3][0]);

	m_matrix[0][1] =
		(first->m_matrix[0][0] * second->m_matrix[0][1]) +
		(first->m_matrix[0][1] * second->m_matrix[1][1]) +
		(first->m_matrix[0][2] * second->m_matrix[2][1]) +
		(first->m_matrix[0][3] * second->m_matrix[3][1]);

	m_matrix[0][2] =
		(first->m_matrix[0][0] * second->m_matrix[0][2]) +
		(first->m_matrix[0][1] * second->m_matrix[1][2]) +
		(first->m_matrix[0][2] * second->m_matrix[2][2]) +
		(first->m_matrix[0][3] * second->m_matrix[3][2]);

	m_matrix[0][3] =
		(first->m_matrix[0][0] * second->m_matrix[0][3]) +
		(first->m_matrix[0][1] * second->m_matrix[1][3]) +
		(first->m_matrix[0][2] * second->m_matrix[2][3]) +
		(first->m_matrix[0][3] * second->m_matrix[3][3]);

	// Second row
	m_matrix[1][0] =
		(first->m_matrix[1][0] * second->m_matrix[0][0]) +
		(first->m_matrix[1][1] * second->m_matrix[1][0]) +
		(first->m_matrix[1][2] * second->m_matrix[2][0]) +
		(first->m_matrix[1][3] * second->m_matrix[3][0]);

	m_matrix[1][1] =
		(first->m_matrix[1][0] * second->m_matrix[0][1]) +
		(first->m_matrix[1][1] * second->m_matrix[1][1]) +
		(first->m_matrix[1][2] * second->m_matrix[2][1]) +
		(first->m_matrix[1][3] * second->m_matrix[3][1]);

	m_matrix[1][2] =
		(first->m_matrix[1][0] * second->m_matrix[0][2]) +
		(first->m_matrix[1][1] * second->m_matrix[1][2]) +
		(first->m_matrix[1][2] * second->m_matrix[2][2]) +
		(first->m_matrix[1][3] * second->m_matrix[3][2]);

	m_matrix[1][3] =
		(first->m_matrix[1][0] * second->m_matrix[0][3]) +
		(first->m_matrix[1][1] * second->m_matrix[1][3]) +
		(first->m_matrix[1][2] * second->m_matrix[2][3]) +
		(first->m_matrix[1][3] * second->m_matrix[3][3]);

	// Third row
	m_matrix[2][0] =
		(first->m_matrix[2][0] * second->m_matrix[0][0]) +
		(first->m_matrix[2][1] * second->m_matrix[1][0]) +
		(first->m_matrix[2][2] * second->m_matrix[2][0]) +
		(first->m_matrix[2][3] * second->m_matrix[3][0]);

	m_matrix[2][1] =
		(first->m_matrix[2][0] * second->m_matrix[0][1]) +
		(first->m_matrix[2][1] * second->m_matrix[1][1]) +
		(first->m_matrix[2][2] * second->m_matrix[2][1]) +
		(first->m_matrix[2][3] * second->m_matrix[3][1]);

	m_matrix[2][2] =
		(first->m_matrix[2][0] * second->m_matrix[0][2]) +
		(first->m_matrix[2][1] * second->m_matrix[1][2]) +
		(first->m_matrix[2][2] * second->m_matrix[2][2]) +
		(first->m_matrix[2][3] * second->m_matrix[3][2]);

	m_matrix[2][3] =
		(first->m_matrix[2][0] * second->m_matrix[0][3]) +
		(first->m_matrix[2][1] * second->m_matrix[1][3]) +
		(first->m_matrix[2][2] * second->m_matrix[2][3]) +
		(first->m_matrix[2][3] * second->m_matrix[3][3]);

	// Fourth row
	m_matrix[3][0] =
		(first->m_matrix[3][0] * second->m_matrix[0][0]) +
		(first->m_matrix[3][1] * second->m_matrix[1][0]) +
		(first->m_matrix[3][2] * second->m_matrix[2][0]) +
		(first->m_matrix[3][3] * second->m_matrix[3][0]);

	m_matrix[3][1] =
		(first->m_matrix[3][0] * second->m_matrix[0][1]) +
		(first->m_matrix[3][1] * second->m_matrix[1][1]) +
		(first->m_matrix[3][2] * second->m_matrix[2][1]) +
		(first->m_matrix[3][3] * second->m_matrix[3][1]);

	m_matrix[3][2] =
		(first->m_matrix[3][0] * second->m_matrix[0][2]) +
		(first->m_matrix[3][1] * second->m_matrix[1][2]) +
		(first->m_matrix[3][2] * second->m_matrix[2][2]) +
		(first->m_matrix[3][3] * second->m_matrix[3][2]);

	m_matrix[3][3] =
		(first->m_matrix[3][0] * second->m_matrix[0][3]) +
		(first->m_matrix[3][1] * second->m_matrix[1][3]) +
		(first->m_matrix[3][2] * second->m_matrix[2][3]) +
		(first->m_matrix[3][3] * second->m_matrix[3][3]);
}

/* @socom-skeleton body Cross__6CPnt3DFPC6CPnt3DP6CPnt3Db */
/* held from src/gamez/zMath/zmath_pnt3d.cpp:52 */
void CPnt3D::Cross(const CPnt3D* a, CPnt3D* b, bool normalize)
{

}

/* @socom-skeleton body zMathCopyVector__FR5PNT3DR5PNT3D */
/* held from src/gamez/zMath/zmath_vu.cpp:49 */
void zMathCopyVector(PNT3D& out, PNT3D& in)
{
#ifdef PS2 && PS2DEV
#else
	out.x = in.x;
	out.y = in.y;
	out.z = in.z;
#endif
}

/* @socom-skeleton body zMathAddVector__FR5PNT3DR5PNT3DR5PNT3D */
/* held from src/gamez/zMath/zmath_vu.cpp:59 */
void zMathAddVector(PNT3D& sum, PNT3D& addend, PNT3D& summand)
{
	PNT3D work;
	work.x = addend.x + summand.x;
	work.y = addend.y + summand.y;
	work.z = addend.z + summand.z;
	zMathCopyVector(sum, work);
}

/* @socom-skeleton body zMathSubVector__FR5PNT3DR5PNT3DR5PNT3D */
/* held from src/gamez/zMath/zmath_vu.cpp:68 */
void zMathSubVector(PNT3D& diff, PNT3D& subend, PNT3D& diffand)
{
	PNT3D work;
	work.x = subend.x - diffand.x;
	work.y = subend.y - diffand.y;
	work.z = subend.z - diffand.z;
	zMathCopyVector(diff, work);
}

/* @socom-skeleton body zMathUnitMatrix__FR7CMatrix */
/* held from src/gamez/zMath/zmath_vu.cpp:77 */
void zMathUnitMatrix(CMatrix& mat)
{
	memset(&mat, 0, sizeof(CMatrix));
	mat.m_matrix[0][0] = 1.0f;
	mat.m_matrix[1][1] = 1.0f;
	mat.m_matrix[2][2] = 1.0f;
	mat.m_matrix[3][3] = 1.0f;
}

/* @socom-skeleton body zMathCopyMatrix__FP7CMatrixPC7CMatrix */
/* held from src/gamez/zMath/zmath_vu.cpp:86 */
void zMathCopyMatrix(CMatrix* dest, const CMatrix* src)
{
	s32 i, j, k;
	f32* pA = (f32*)dest;
	f32* pB = (f32*)src;

	for (i = 0; i < 16; i++)
		pA[i] = pB[i];
}

/* @socom-skeleton body zMathMulMatrix__FP7CMatrixP7CMatrixP7CMatrix */
/* held from src/gamez/zMath/zmath_vu.cpp:96 */
void zMathMulMatrix(CMatrix* m0, CMatrix* m1, CMatrix* out)
{
	s32 i, j, k;
	f32* pA = (f32*)m1;
	f32* pB = (f32*)m0;
	f32* pQ = (f32*)out;
	f32 pM[16];

	for (s32 i = 0; i < 16; i++)
		pM[i] = 0;

	for (i = 0; i < 4; i++)
		for (j = 0; j < 4; j++)
			for (k = 0; k < 4; k++)
				pM[4 * i + j] += pA[4 * k + j] * pB[4 * i + k];

	for (i = 0; i < 16; i++)
		pQ[i] = pM[i];
;}
