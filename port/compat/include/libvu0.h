/* Functional port lane: Sony libvu0 declarations used by src/ (provider symbols; the
   implementations live in port/compat). Prototypes from the call sites in socom.elf. */
#ifndef SOCOM_COMPAT_LIBVU0_H
#define SOCOM_COMPAT_LIBVU0_H

typedef float sceVu0FVECTOR[4] __attribute__((aligned(16)));
typedef float sceVu0FMATRIX[4][4] __attribute__((aligned(16)));

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
/* v0 = v1 + v2 (0x152438) */
void sceVu0AddVector(sceVu0FVECTOR v0, sceVu0FVECTOR v1, sceVu0FVECTOR v2);
/* v0 = v1 * t (0x152480) */
void sceVu0ScaleVector(sceVu0FVECTOR v0, sceVu0FVECTOR v1, float t);
/* v0 = v1, one 128-bit copy (0x1524c8) */
void sceVu0CopyVector(sceVu0FVECTOR v0, sceVu0FVECTOR v1);
/* view-to-screen projection (0x152a28; CCamera::Update 0x1e8020) */
void sceVu0ViewScreenMatrix(sceVu0FMATRIX m, float scrz, float ax, float ay, float cx, float cy,
                            float zmin, float zmax, float nearz, float farz);

#ifdef __cplusplus
}
#endif

#endif
