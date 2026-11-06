#ifndef ZMATH_VU_H
#define ZMATH_VU_H
#include "zmath.h"
#include "gamez/zSystem/zsys.h"

/// -----------------------------
/// PURPOSE:
/// This file provides functions for wrapping PS2 vector unit calls so that they're "platform agnostic".
/// For example, if we were compiling this project for the PS2, then PS2-related operations will be selected.
/// Likewise, if compiling for an x86 target, vector code compatible with the PC will be selected.
/// 
/// NOTICE:
/// This file does not contain anything from Sony's PS2 development kit.
/// Code is sourced from the unofficial PS2SDK repository:
/// https://github.com/ps2dev/ps2sdk
/// -----------------------------

extern void Vu0MatrixInverseWithUniformScale(CMatrix* m0, CMatrix* m1);

extern void zMathScaleVector();
extern void zMathFTOI0Vector();
extern void zMathFTOI4Vector();
extern void zMathInnerVector();

extern void zMathInnerProduct();
extern void zMathOuterProduct();
extern void zMathNormalize();

extern void zMathRotTransPers();

extern void zMathClipBBox();

/* zMathCopyMatrix/zMathUnitMatrix/zMathMulMatrix are not in the ELF: the call sites call libvu0
   directly (CPipe::RenderWorld 0x2448dc sceVu0CopyMatrix; CStack::Multiply 0x221dfc sceVu0MulMatrix) */
inline void zMathCopyMatrix(CMatrix* dest, const CMatrix* src)
{
	sceVu0CopyMatrix(dest->m_matrix, const_cast<float(*)[4]>(src->m_matrix));
}
extern void zMathApplyMatrix();
inline void zMathUnitMatrix(CMatrix& mat) { sceVu0UnitMatrix(mat.m_matrix); } /* port: unproven (caller st_core.cpp not checked) */
inline void zMathMulMatrix(CMatrix* m0, CMatrix* m1, CMatrix* m2) { sceVu0MulMatrix(m0->m_matrix, m1->m_matrix, m2->m_matrix); }
extern void zMathCameraMatrix();
extern void zMathViewScreenMatrix();
extern void zMathTransMatrix();
extern void zMathTransposeMatrix();
extern void zMathInverseMatrix();
extern void zMathRotMatrixX();
extern void zMathRotMatrixY();
extern void zMathRotMatrixZ();
extern void zMathLightColorMatrix();
extern void zMathNormalLightMatrix();
#endif