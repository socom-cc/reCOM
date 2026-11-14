/* Functional port lane: Sony libvu0 declarations used by src/ (provider symbols; the
   implementations live in port/compat). Prototypes from the call sites in socom.elf. */
#ifndef SOCOM_COMPAT_LIBVU0_H
#define SOCOM_COMPAT_LIBVU0_H

typedef float sceVu0FVECTOR[4] __attribute__((aligned(16)));
typedef float sceVu0FMATRIX[4][4] __attribute__((aligned(16)));
typedef int sceVu0IVECTOR[4] __attribute__((aligned(16)));

#ifdef __cplusplus
extern "C" {
#endif

/* m0 = identity (CMatrix::CMatrix 0x222460) */
void sceVu0UnitMatrix(sceVu0FMATRIX m0);
/* m0 = m1 (CPipe::RenderWorld 0x2448dc, CPipe::RenderUiNode 0x241ce8) */
void sceVu0CopyMatrix(sceVu0FMATRIX m0, sceVu0FMATRIX m1);
/* row i of m0 = row i of m2 times m1 (0x152248; CStack::Multiply 0x221dfc, CMatrix::Multiply 0x218de8) */
void sceVu0MulMatrix(sceVu0FMATRIX m0, sceVu0FMATRIX m1, sceVu0FMATRIX m2);
/* v0 = v1 x v2 (CPnt3D::Cross 0x2016ac) */
void sceVu0OuterProduct(sceVu0FVECTOR v0, sceVu0FVECTOR v1, sceVu0FVECTOR v2);
/* v0 = normalized v1 (CPnt3D::Cross 0x2016bc) */
void sceVu0Normalize(sceVu0FVECTOR v0, sceVu0FVECTOR v1);
/* v0 = m0 * v1, rows of m0 weighted by v1.xyzw (0x152218; CCamera::Update 0x1e839c) */
void sceVu0ApplyMatrix(sceVu0FVECTOR v0, sceVu0FMATRIX m0, sceVu0FVECTOR v1);
/* inverse of a rigid transform: transposed 3x3, negated rotated translation (0x152360) */
void sceVu0InversMatrix(sceVu0FMATRIX m0, sceVu0FMATRIX m1);
/* m0 = m1 with tv added to the translation row (0x152498) */
void sceVu0TransMatrix(sceVu0FMATRIX m0, sceVu0FMATRIX m1, sceVu0FVECTOR tv);
/* world-to-view matrix from position p, view direction zd and up vector yd (0x152850;
   zdb::CalcWorldToUV 0x30cd8c) */
void sceVu0CameraMatrix(sceVu0FMATRIX m, sceVu0FVECTOR p, sceVu0FVECTOR zd, sceVu0FVECTOR yd);
/* v0 = v1 + v2 (0x152438) */
void sceVu0AddVector(sceVu0FVECTOR v0, sceVu0FVECTOR v1, sceVu0FVECTOR v2);
/* v0 = v1 * t (0x152480) */
void sceVu0ScaleVector(sceVu0FVECTOR v0, sceVu0FVECTOR v1, float t);
/* v0 = v1, one 128-bit copy (0x1524c8) */
void sceVu0CopyVector(sceVu0FVECTOR v0, sceVu0FVECTOR v1);
/* view-to-screen projection (0x152a28; CCamera::Update 0x1e8020) */
void sceVu0ViewScreenMatrix(sceVu0FMATRIX m, float scrz, float ax, float ay, float cx, float cy,
                            float zmin, float zmax, float nearz, float farz);
/* m0 = transpose of m1 (0x152318; m0 may alias m1) */
void sceVu0TransposeMatrix(sceVu0FMATRIX m0, sceVu0FMATRIX m1);
/* light direction matrix from three light vectors (0x152900; CWorld::Update 0x22f320) */
void sceVu0NormalLightMatrix(sceVu0FMATRIX m, sceVu0FVECTOR l0, sceVu0FVECTOR l1, sceVu0FVECTOR l2);
/* light colour matrix, rows c0, c1, c2, a (0x1529c0; CWorld::Update 0x22f34c) */
void sceVu0LightColorMatrix(sceVu0FMATRIX m, sceVu0FVECTOR c0, sceVu0FVECTOR c1, sceVu0FVECTOR c2, sceVu0FVECTOR a);
/* m0 = m1 turned about y by ry: each row r of m1 -> r.x*(c,0,-s,0) + r.y*(0,1,0,0) + r.z*(s,0,c,0) + r.w*(0,0,0,1)
 * (0x152730; GetDeadCamPoints 0x1e8fc0; m0 may alias m1) */
void sceVu0RotMatrixY(sceVu0FMATRIX m0, sceVu0FMATRIX m1, float ry);
/* the same about x (0x152688) and z (0x1525e0); load_si_script 0x1c6900 */
void sceVu0RotMatrixX(sceVu0FMATRIX m0, sceVu0FMATRIX m1, float rx);
void sceVu0RotMatrixZ(sceVu0FMATRIX m0, sceVu0FMATRIX m1, float rz);

/* v0 = ftoi4 of (m0 * v1 with x, y, z divided by its w; w kept), z and w as ftoi0 when mode
 * is nonzero (0x152d18; Particle::BufferElement::Draw 0x2348c4) */
void sceVu0RotTransPers(sceVu0IVECTOR v0, sceVu0FMATRIX m0, sceVu0FVECTOR v1, int mode);
/* v0 = v1 truncated to integers (vftoi0, 0x152510) */
void sceVu0FTOI0Vector(sceVu0IVECTOR v0, sceVu0FVECTOR v1);

#ifdef __cplusplus
}
#endif

#endif
