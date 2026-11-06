# Functional port lane: build src/ with the pinned ps2dev toolchain.
#
# Configure inside the Linux side (WSL) with the toolchain file:
#   cmake -S port -B <build> -DCMAKE_TOOLCHAIN_FILE=$PS2DEV/share/ps2dev.cmake
#   cmake --build <build> -- -k        # keep going to collect every failure
#
# Targets:
#   socom_game  - every src/ unit, including the *_holding.cpp files
#   socom_port  - the ELF: socom_game + port/compat + ps2sdk
# Nothing built here is evidence for the matching lane.
cmake_minimum_required(VERSION 3.13)
project(socom_port C CXX)

set(SOCOM_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")
get_filename_component(SOCOM_ROOT "${SOCOM_ROOT}" ABSOLUTE)

file(GLOB_RECURSE SOCOM_GAME_SOURCES CONFIGURE_DEPENDS
  "${SOCOM_ROOT}/src/*.cpp" "${SOCOM_ROOT}/src/*.c")
# *_holding.cpp files are built too: they hold the only provisional code for functions
# stage 4 left without an owning unit (the matching lane never builds them).

set(SOCOM_PORT_FLAGS
  -std=gnu++17
  -fno-exceptions
  # Metrowerks accepted members that reuse a type's name (e.g. `f32 f32[4]` in _word128).
  -Wno-changes-meaning
  # Boot diagnostics: a non-void stub that falls off its end calls
  # __ubsan_handle_missing_return (port/compat/port_diag.c) instead of running into the
  # next function. Compile-only; libubsan is not linked.
  -fsanitize=return
  # Metrowerks never removes a malloc/free pair; GCC does when it treats them as
  # builtins. zsys_FullAllocAndFree (0x2f4920) probes the heap size with exactly such a
  # pair, so with the builtins it never sees a failure, reports 32 MB and zSysInit
  # (0x2f4df0) sets zSys.isT10K. Calling them as plain functions keeps the probe.
  -fno-builtin-malloc
  -fno-builtin-free
  -include "${CMAKE_CURRENT_SOURCE_DIR}/include/socom_port_prefix.h")

add_library(socom_game STATIC ${SOCOM_GAME_SOURCES})
target_compile_definitions(socom_game PRIVATE SOCOM_PORT _EE SOCOM_PORT_TRACE_ON)
target_include_directories(socom_game PRIVATE
  "${SOCOM_ROOT}/src"
  "${CMAKE_CURRENT_SOURCE_DIR}/compat/include")
target_compile_options(socom_game PRIVATE
  $<$<COMPILE_LANGUAGE:CXX>:${SOCOM_PORT_FLAGS}>)

file(GLOB_RECURSE SOCOM_COMPAT_SOURCES CONFIGURE_DEPENDS
  "${CMAKE_CURRENT_SOURCE_DIR}/compat/*.cpp" "${CMAKE_CURRENT_SOURCE_DIR}/compat/*.c")

add_executable(socom_port ${SOCOM_COMPAT_SOURCES})
set_target_properties(socom_port PROPERTIES OUTPUT_NAME "socom_port.elf" LINKER_LANGUAGE CXX)
target_include_directories(socom_port PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/compat/include")
target_compile_definitions(socom_port PRIVATE SOCOM_PORT _EE SOCOM_PORT_TRACE_ON)
target_link_libraries(socom_port PRIVATE
  -Wl,--whole-archive socom_game -Wl,--no-whole-archive
  -liopreboot -lpatches -lcdvd -ldebug -leedebug -lkernel)

# INTERIM allocator (port/interim/zsys_memory_interim.c). The game allocator in
# src/gamez/zSystem/zsys_memory.cpp is held for the stage-4 amendment wave and still
# has empty stub bodies; _delete__FPvPCci has no owning unit. Each function is wrapped
# (-Wl,--wrap) only while its src/ definition is still the empty skeleton stub (for
# _delete: while no src/ fence names it), so written bodies take over by themselves.
# Remove this block and port/interim/ once all of them have bodies.
set(SOCOM_INTERIM_ALLOC
  "_new__FUiPCci=_Z4_newjPKci"
  "_new_vec__FUiPCci=_Z8_new_vecjPKci"
  "_malloc__FUiPCci=_Z7_mallocjPKci"
  "_calloc__FUiUiPCci=_Z7_callocjjPKci"
  "_realloc__FPvUiPCci=_Z8_reallocPvjPKci"
  "_memalign__FUiUiPCci=_Z9_memalignjjPKci"
  "_strdup__FPCcPCci=_Z7_strdupPKcS0_i"
  "_delete_vec__FPvPCci=_Z11_delete_vecPvPKci")
set(_zsys_memory_cpp "${SOCOM_ROOT}/src/gamez/zSystem/zsys_memory.cpp")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_zsys_memory_cpp}")
file(READ "${_zsys_memory_cpp}" _zsys_memory)
set(SOCOM_INTERIM_WRAP "")
foreach(_pair ${SOCOM_INTERIM_ALLOC})
  string(REPLACE "=" ";" _pair "${_pair}")
  list(GET _pair 0 _mw)
  list(GET _pair 1 _sym)
  string(REGEX MATCH "@socom-skeleton stub ${_mw} \\*/\n[^\n]*\n{\n}" _stub "${_zsys_memory}")
  if(_stub)
    list(APPEND SOCOM_INTERIM_WRAP "-Wl,--wrap=${_sym}")
  endif()
endforeach()
set(_delete_owned FALSE)
foreach(_src ${SOCOM_GAME_SOURCES})
  file(STRINGS "${_src}" _hit REGEX "@socom-skeleton (body|stub) _delete__FPvPCci ")
  if(_hit)
    set(_delete_owned TRUE)
  endif()
endforeach()
if(NOT _delete_owned)
  list(APPEND SOCOM_INTERIM_WRAP "-Wl,--wrap=_Z7_deletePvPKci")
endif()
if(SOCOM_INTERIM_WRAP)
  list(LENGTH SOCOM_INTERIM_WRAP _n)
  message(STATUS "socom port: interim allocator stand-ins for ${_n} functions")
  target_sources(socom_port PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/interim/zsys_memory_interim.c")
  target_link_options(socom_port PRIVATE ${SOCOM_INTERIM_WRAP})
endif()
