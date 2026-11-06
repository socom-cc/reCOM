#ifndef ZSYSTEM_PRIMITIVE_H
#define ZSYSTEM_PRIMITIVE_H
/// -------------------------------------------
/// INCLUDES
/// -------------------------------------------
#include <cstdint>

/// -------------------------------------------
/// PRIMITIVE TYPES
/// -------------------------------------------

typedef uint8_t    u8;  // unsigned char
typedef uint16_t   u16; // unsigned short
typedef unsigned int u32; // unsigned int (uint32_t is `long unsigned int` on the ps2dev GCC target)
typedef uint64_t   u64; // unsigned long
typedef int8_t     s8;  // char
typedef int16_t    s16; // short
typedef int        s32; // int (int32_t is `long int` on the ps2dev GCC target)
typedef int64_t    s64; // long
typedef float      f32; // float
typedef double     f64;
#endif