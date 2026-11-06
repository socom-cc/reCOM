/* Functional port lane: replacements for the Sony libvu0 functions the game calls.
 *
 * ps2sdk has no libvu0. These are plain C implementations of the behaviour read
 * from the copies linked into socom.elf (addresses below); they are not Sony's code.
 * The VU0 macro instructions round differently from the EE FPU, so results can
 * differ in the last bit; nothing here is evidence for the matching lane. */
#include <libvu0.h>
#include <math.h>

/* 0x152540: rows 0..3 = (1,0,0,0) (0,1,0,0) (0,0,1,0) (0,0,0,1). */
void sceVu0UnitMatrix(sceVu0FMATRIX m0)
{
    int i, j;
    for (i = 0; i < 4; i++)
        for (j = 0; j < 4; j++)
            m0[i][j] = (i == j) ? 1.0f : 0.0f;
}

/* 0x1524d8: four 128-bit row copies, m0 = m1. */
void sceVu0CopyMatrix(sceVu0FMATRIX m0, sceVu0FMATRIX m1)
{
    int i, j;
    for (i = 0; i < 4; i++)
        for (j = 0; j < 4; j++)
            m0[i][j] = m1[i][j];
}

/* 0x152248: m1 is loaded whole first; then for each row i, in order,
 * m0[i] = m1[0]*m2[i].x + m1[1]*m2[i].y + m1[2]*m2[i].z + m1[3]*m2[i].w.
 * Row i of m2 is read before row i of m0 is written, so m0 may alias m1 or m2. */
void sceVu0MulMatrix(sceVu0FMATRIX m0, sceVu0FMATRIX m1, sceVu0FMATRIX m2)
{
    float a[4][4];
    float row[4];
    int i, k;
    for (i = 0; i < 4; i++)
        for (k = 0; k < 4; k++)
            a[i][k] = m1[i][k];
    for (i = 0; i < 4; i++) {
        const float x = m2[i][0], y = m2[i][1], z = m2[i][2], w = m2[i][3];
        for (k = 0; k < 4; k++)
            row[k] = a[0][k] * x + a[1][k] * y + a[2][k] * z + a[3][k] * w;
        for (k = 0; k < 4; k++)
            m0[i][k] = row[k];
    }
}

/* 0x152290: v0.xyz = v1 x v2, v0.w = 0. */
void sceVu0OuterProduct(sceVu0FVECTOR v0, sceVu0FVECTOR v1, sceVu0FVECTOR v2)
{
    const float x = v1[1] * v2[2] - v2[1] * v1[2];
    const float y = v1[2] * v2[0] - v2[2] * v1[0];
    const float z = v1[0] * v2[1] - v2[0] * v1[1];
    v0[0] = x;
    v0[1] = y;
    v0[2] = z;
    v0[3] = 0.0f;
}

/* 0x1522d8: v0.xyz = v1.xyz / |v1.xyz|, v0.w = 0. VU0 division by zero yields the
 * largest float rather than infinity, so a zero vector normalizes to zero. */
void sceVu0Normalize(sceVu0FVECTOR v0, sceVu0FVECTOR v1)
{
    const float length = sqrtf(v1[0] * v1[0] + v1[1] * v1[1] + v1[2] * v1[2]);
    const float scale = (length > 0.0f) ? 1.0f / length : 0.0f;
    const float x = v1[0] * scale, y = v1[1] * scale, z = v1[2] * scale;
    v0[0] = x;
    v0[1] = y;
    v0[2] = z;
    v0[3] = 0.0f;
}
