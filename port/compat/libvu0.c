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

/* 0x152218: v0 = m0[0]*v1.x + m0[1]*v1.y + m0[2]*v1.z + m0[3]*v1.w (v0 may alias v1). */
void sceVu0ApplyMatrix(sceVu0FVECTOR v0, sceVu0FMATRIX m0, sceVu0FVECTOR v1)
{
    const float x = v1[0], y = v1[1], z = v1[2], w = v1[3];
    int k;
    for (k = 0; k < 4; k++)
        v0[k] = m0[0][k] * x + m0[1][k] * y + m0[2][k] * z + m0[3][k] * w;
}

/* 0x152360: rows 0..2 of m0 = columns 0..2 of m1 with w = 0; row 3 = (-(m1[0].t),
 * -(m1[1].t), -(m1[2].t), m1[3].w) with t = m1[3].xyz (the translation through the
 * transposed rows: vmulax/vmadday/vmaddz scale whole rows of m0 by t.x, t.y, t.z). All of
 * m1 is read before m0 is written, so m0 may alias m1. */
void sceVu0InversMatrix(sceVu0FMATRIX m0, sceVu0FMATRIX m1)
{
    float r[3][3];
    const float tx = m1[3][0], ty = m1[3][1], tz = m1[3][2], tw = m1[3][3];
    int i, j;
    for (i = 0; i < 3; i++)
        for (j = 0; j < 3; j++)
            r[i][j] = m1[j][i];
    for (i = 0; i < 3; i++) {
        m0[i][0] = r[i][0];
        m0[i][1] = r[i][1];
        m0[i][2] = r[i][2];
        m0[i][3] = 0.0f;
    }
    /* vmulax/vmadday/vmaddz: ACC.xyz = r[0].xyz*tx + r[1].xyz*ty + r[2].xyz*tz, with r the
     * rows written above, so component j = r0j*tx + r1j*ty + r2j*tz (an earlier version
     * summed along the rows instead, which only agrees for a symmetric rotation such as a
     * level camera's) */
    m0[3][0] = 0.0f - (r[0][0] * tx + r[1][0] * ty + r[2][0] * tz);
    m0[3][1] = 0.0f - (r[0][1] * tx + r[1][1] * ty + r[2][1] * tz);
    m0[3][2] = 0.0f - (r[0][2] * tx + r[1][2] * ty + r[2][2] * tz);
    m0[3][3] = tw;
}

/* 0x152438 */
void sceVu0AddVector(sceVu0FVECTOR v0, sceVu0FVECTOR v1, sceVu0FVECTOR v2)
{
    int k;
    for (k = 0; k < 4; k++)
        v0[k] = v1[k] + v2[k];
}

/* 0x152480 */
void sceVu0ScaleVector(sceVu0FVECTOR v0, sceVu0FVECTOR v1, float t)
{
    int k;
    for (k = 0; k < 4; k++)
        v0[k] = v1[k] * t;
}

/* 0x1524c8 */
void sceVu0CopyVector(sceVu0FVECTOR v0, sceVu0FVECTOR v1)
{
    int k;
    for (k = 0; k < 4; k++)
        v0[k] = v1[k];
}

/* 0x152498: rows 0..2 of m0 = rows 0..2 of m1; row 3 = m1[3] with tv.xyz added (w kept).
 * tv and m1 are read before m0 is written. */
void sceVu0TransMatrix(sceVu0FMATRIX m0, sceVu0FMATRIX m1, sceVu0FVECTOR tv)
{
    const float x = m1[3][0] + tv[0], y = m1[3][1] + tv[1], z = m1[3][2] + tv[2], w = m1[3][3];
    int i, j;
    for (i = 0; i < 3; i++)
        for (j = 0; j < 4; j++)
            m0[i][j] = m1[i][j];
    m0[3][0] = x;
    m0[3][1] = y;
    m0[3][2] = z;
    m0[3][3] = w;
}

/* 0x152850: the world-to-view matrix of a camera at p looking along zd with yd up:
 * a unit matrix whose row 0 = normalize(yd x zd), row 2 = normalize(zd), row 1 = row 2 x
 * row 0, translated by p (sceVu0TransMatrix), then sceVu0InversMatrix. */
void sceVu0CameraMatrix(sceVu0FMATRIX m, sceVu0FVECTOR p, sceVu0FVECTOR zd, sceVu0FVECTOR yd)
{
    sceVu0FMATRIX m0;
    sceVu0FVECTOR xd;

    sceVu0UnitMatrix(m0);
    sceVu0OuterProduct(xd, yd, zd);
    sceVu0Normalize(m0[0], xd);
    sceVu0Normalize(m0[2], zd);
    sceVu0OuterProduct(m0[1], m0[2], m0[0]);
    sceVu0TransMatrix(m0, m0, p);
    sceVu0InversMatrix(m, m0);
}

/* 0x152a28: m = M2 * M1 (sceVu0MulMatrix(m, M2, M1)), where M1 is the unit matrix with
 * [0][0] = [1][1] = scrz, [2][2] = [3][3] = 0, [2][3] = [3][2] = 1, and M2 the unit matrix
 * with [0][0] = ax, [1][1] = ay, [2][2] = farz*nearz*(zmax-zmin)/(farz-nearz),
 * [3][0] = cx, [3][1] = cy, [3][2] = (zmin*farz - zmax*nearz)/(farz-nearz). */
void sceVu0ViewScreenMatrix(sceVu0FMATRIX m, float scrz, float ax, float ay, float cx, float cy,
                            float zmin, float zmax, float nearz, float farz)
{
    sceVu0FMATRIX s;
    const float depth = farz - nearz;
    const float az = (farz * nearz * (zmax - zmin)) / depth;
    const float bz = ((0.0f - zmax) * nearz + zmin * farz) / depth;

    sceVu0UnitMatrix(m);
    m[1][1] = scrz;
    m[0][0] = scrz;
    m[2][2] = 0.0f;
    m[3][3] = 0.0f;
    m[2][3] = 1.0f;
    m[3][2] = 1.0f;

    sceVu0UnitMatrix(s);
    s[0][0] = ax;
    s[1][1] = ay;
    s[2][2] = az;
    s[3][0] = cx;
    s[3][1] = cy;
    s[3][2] = bz;

    sceVu0MulMatrix(m, s, m);
}

/* 0x152318: m0 = transpose of m1 (the four rows are read before any is written, so m0 may
 * alias m1). */
void sceVu0TransposeMatrix(sceVu0FMATRIX m0, sceVu0FMATRIX m1)
{
    float t[4][4];
    int i, j;
    for (i = 0; i < 4; i++)
        for (j = 0; j < 4; j++)
            t[i][j] = m1[j][i];
    for (i = 0; i < 4; i++)
        for (j = 0; j < 4; j++)
            m0[i][j] = t[i][j];
}

/* 0x152900: rows 0..2 = sceVu0Normalize(-l0), (-l1), (-l2) (w = 0), row 3 = (0,0,0,1),
 * then the matrix is transposed in place. */
void sceVu0NormalLightMatrix(sceVu0FMATRIX m, sceVu0FVECTOR l0, sceVu0FVECTOR l1, sceVu0FVECTOR l2)
{
    sceVu0FVECTOR t;
    sceVu0ScaleVector(t, l0, -1.0f);
    sceVu0Normalize(m[0], t);
    sceVu0ScaleVector(t, l1, -1.0f);
    sceVu0Normalize(m[1], t);
    sceVu0ScaleVector(t, l2, -1.0f);
    sceVu0Normalize(m[2], t);
    m[3][0] = 0.0f;
    m[3][3] = 1.0f;
    m[3][2] = 0.0f;
    m[3][1] = 0.0f;
    sceVu0TransposeMatrix(m, m);
}

/* 0x1529c0: rows c0, c1, c2, a. */
void sceVu0LightColorMatrix(sceVu0FMATRIX m, sceVu0FVECTOR c0, sceVu0FVECTOR c1, sceVu0FVECTOR c2, sceVu0FVECTOR a)
{
    sceVu0CopyVector(m[0], c0);
    sceVu0CopyVector(m[1], c1);
    sceVu0CopyVector(m[2], c2);
    sceVu0CopyVector(m[3], a);
}

/* 0x152730: the rotation rows are (c,0,-s,0) (0,1,0,0) (s,0,c,0) (0,0,0,1) with
 * c = cos(ry), s = sin(ry) (_sceVu0ecossin 0x152568: a VU0 polynomial for sin(pi/2 -/+ ry)
 * and s = +/-sqrt(1 - c*c) by the sign of ry; port: cosf/sinf). Each row r of m1 becomes
 * r.x*row0 + r.y*row1 + r.z*row2 + r.w*row3 (vmulax/vmadday/vmaddaz/vmaddw), row by
 * row, so m0 may alias m1. */
void sceVu0RotMatrixY(sceVu0FMATRIX m0, sceVu0FMATRIX m1, float ry)
{
    const float c = cosf(ry), s = sinf(ry);
    int i;
    for (i = 0; i < 4; i++) {
        const float x = m1[i][0], y = m1[i][1], z = m1[i][2], w = m1[i][3];
        m0[i][0] = x * c + z * s;
        m0[i][1] = y;
        m0[i][2] = -x * s + z * c;
        m0[i][3] = w;
    }
}

/* 0x152d18: rows of m0 weighted by v1.xyzw (vmulax/vmadday/vmaddaz/vmaddw), x, y, z times
 * 1 / w (vdiv, vmulq.xyz), all four converted by vftoi4 (x16, truncated), then z and w by
 * vftoi0 when mode is nonzero. */
void sceVu0RotTransPers(sceVu0IVECTOR v0, sceVu0FMATRIX m0, sceVu0FVECTOR v1, int mode)
{
    float r[4];
    int i;
    for (i = 0; i < 4; i++)
        r[i] = m0[0][i] * v1[0] + m0[1][i] * v1[1] + m0[2][i] * v1[2] + m0[3][i] * v1[3];
    {
        const float q = 1.0f / r[3];
        r[0] *= q;
        r[1] *= q;
        r[2] *= q;
    }
    for (i = 0; i < 4; i++)
        v0[i] = (int)(r[i] * 16.0f);
    if (mode) {
        v0[2] = (int)r[2];
        v0[3] = (int)r[3];
    }
}

/* 0x152510: vftoi0.xyzw */
void sceVu0FTOI0Vector(sceVu0IVECTOR v0, sceVu0FVECTOR v1)
{
    int i;
    for (i = 0; i < 4; i++)
        v0[i] = (int)v1[i];
}
