#ifndef ZSYSTEM_ALLOC_H
#define ZSYSTEM_ALLOC_H
/// -------------------------------------------
/// ALLOCATION MACROS
/// -------------------------------------------
#define zmalloc(size) _malloc(size, __FILE__, __LINE__)
#define zcalloc(num, size) _calloc(num, size, __FILE__, __LINE__)
#define zrealloc(ptr, new_size) _realloc(ptr, new_size, __FILE__, __LINE__)
#define zmemalign(alignment, size) _memalign(alignment, size, __FILE__, __LINE__)
#define zstrdup(str) _strdup(str, __FILE__, __LINE__)
#define zfree(block) _free(block, __FILE__, __LINE__)
#endif