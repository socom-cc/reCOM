# Functional port lane: build src/ with the pinned ps2dev toolchain.
#
# Configure inside the Linux side (WSL) with the toolchain file:
#   cmake -S port -B <build> -DCMAKE_TOOLCHAIN_FILE=$PS2DEV/share/ps2dev.cmake
#   cmake --build <build> -- -k        # keep going to collect every failure
#
# Targets:
#   socom_game  - every src/ unit, including the *_holding.cpp files and the .vsm microcode
#   socom_port  - the ELF: socom_game + port/compat + ps2sdk
# Nothing built here is evidence for the matching lane.
cmake_minimum_required(VERSION 3.13)
project(socom_port C CXX)

set(SOCOM_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")
get_filename_component(SOCOM_ROOT "${SOCOM_ROOT}" ABSOLUTE)

# Optional compiler cache: when ccache is installed, a new build dir of a tree that was built
# before takes its objects from the cache instead of compiling all of src/ again (test builds
# make a build dir per test). CCACHE_BASEDIR makes the paths under the tree relative and
# CCACHE_NOHASHDIR leaves the build dir out of the hash, so build dirs next to each other share
# entries. Nothing changes without ccache; -DSOCOM_PORT_CCACHE=OFF turns it off.
option(SOCOM_PORT_CCACHE "use ccache when it is installed" ON)
if(SOCOM_PORT_CCACHE AND NOT CMAKE_C_COMPILER_LAUNCHER AND NOT CMAKE_CXX_COMPILER_LAUNCHER)
  find_program(SOCOM_CCACHE_EXE ccache NO_CMAKE_FIND_ROOT_PATH)
  if(SOCOM_CCACHE_EXE)
    set(_socom_ccache "${CMAKE_COMMAND}" -E env "CCACHE_BASEDIR=${SOCOM_ROOT}" CCACHE_NOHASHDIR=1 "${SOCOM_CCACHE_EXE}")
    set(CMAKE_C_COMPILER_LAUNCHER ${_socom_ccache})
    set(CMAKE_CXX_COMPILER_LAUNCHER ${_socom_ccache})
    message(STATUS "socom port: compiler cache ${SOCOM_CCACHE_EXE}")
  endif()
endif()

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
  # Metrowerks guards function-local statics with a plain flag, no lock. GCC's thread-safe
  # statics take libstdc++'s guard mutex, which the threads layer makes (a heap block) the
  # first time it is locked: during the first mission load, so the block stayed in the middle
  # of the freed mission memory at every return to the menus (docs/port/notes/menu-heap.md).
  -fno-threadsafe-statics
  # Metrowerks compiles a load or store through a pointer as that load or store, whatever the
  # pointer may hold, and on the PS2 address 0 is readable and writable memory: the reference
  # ELF reads and writes through NULL in many places and carries on. GCC at -O2 / -O3 treats
  # such an access as "cannot happen": it removes NULL tests that follow one and turns a path it
  # can prove dereferences NULL into an unconditional trap (teq zero,zero; 221 of them in the
  # game library before these flags). With them the generated code does what the source says,
  # as the original compiler's did.
  -fno-delete-null-pointer-checks
  -fno-isolate-erroneous-paths-dereference
  # The reference ELF's integer divisions are a bare div / divu (82 in the game code, none
  # followed by a trap or a break): dividing by zero leaves garbage in HI / LO and execution
  # goes on. GCC for MIPS adds "teq divisor, zero" after every division by default.
  -mno-check-zero-division
  # Four more assumptions GCC's optimiser makes that Metrowerks' never did; the game's code was
  # written for, and its bodies here are reconstructed from, a compiler without them:
  # - it reads one object through pointers of another type (float bits through an int pointer,
  #   records through command headers); Metrowerks has no type-based alias analysis;
  -fno-strict-aliasing
  # - signed arithmetic is the machine's addu / subu / mult and wraps;
  -fwrapv
  # - memory keeps what was stored in it before a constructor runs and after a destructor has
  #   (operator new overloads that fill the block, members read after a destructor);
  -fno-lifetime-dse
  # - a loop runs as many times as its test says, even when that reads past the end of an
  #   array (the ELF's unbounded indexes are kept as quirks).
  -fno-aggressive-loop-optimizations
  -include "${CMAKE_CURRENT_SOURCE_DIR}/include/socom_port_prefix.h")

# VU microcode (src/**/*.vsm, e.g. zRender/zrndr_vu1.vsm): assembled with the ps2dev dvp-as and
# archived with the game units, so the ELF gets vu0_CodeSegment, vu1_CodeSegment1 and
# vu1_DataSegment1 (section .vutext; the DVP overlay tables are not loaded).
file(GLOB_RECURSE SOCOM_VSM_SOURCES CONFIGURE_DEPENDS "${SOCOM_ROOT}/src/*.vsm")
set(SOCOM_VSM_OBJECTS "")
if(SOCOM_VSM_SOURCES)
  find_program(SOCOM_DVP_AS dvp-as HINTS "$ENV{PS2DEV}/dvp/bin")
  if(NOT SOCOM_DVP_AS)
    message(FATAL_ERROR "socom port: dvp-as not found (ps2dev dvp binutils, $PS2DEV/dvp/bin)")
  endif()
  foreach(_vsm ${SOCOM_VSM_SOURCES})
    file(RELATIVE_PATH _rel "${SOCOM_ROOT}/src" "${_vsm}")
    set(_obj "${CMAKE_CURRENT_BINARY_DIR}/vsm/${_rel}.o")
    get_filename_component(_dir "${_obj}" DIRECTORY)
    add_custom_command(OUTPUT "${_obj}"
      COMMAND "${CMAKE_COMMAND}" -E make_directory "${_dir}"
      COMMAND "${SOCOM_DVP_AS}" -o "${_obj}" "${_vsm}"
      DEPENDS "${_vsm}"
      COMMENT "dvp-as ${_rel}"
      VERBATIM)
    list(APPEND SOCOM_VSM_OBJECTS "${_obj}")
  endforeach()
  set_source_files_properties(${SOCOM_VSM_OBJECTS} PROPERTIES EXTERNAL_OBJECT TRUE GENERATED TRUE)
endif()

add_library(socom_game STATIC ${SOCOM_GAME_SOURCES} ${SOCOM_VSM_OBJECTS})
target_compile_definitions(socom_game PRIVATE SOCOM_PORT _EE SOCOM_PORT_TRACE_ON)
target_include_directories(socom_game PRIVATE
  "${SOCOM_ROOT}/src"
  "${CMAKE_CURRENT_SOURCE_DIR}/compat/include")
target_compile_options(socom_game PRIVATE
  $<$<COMPILE_LANGUAGE:CXX>:${SOCOM_PORT_FLAGS}>)

file(GLOB_RECURSE SOCOM_COMPAT_SOURCES CONFIGURE_DEPENDS
  "${CMAKE_CURRENT_SOURCE_DIR}/compat/*.cpp" "${CMAKE_CURRENT_SOURCE_DIR}/compat/*.c")

# The image layout: the reference ELF has the 256 KB MFIFO ring (mfifoBase, zsys_spr.cpp, aligned to
# its size for the DMAC) at 0x100000, ahead of its code (.text from 0x140000). The pinned ps2sdk
# linker script starts .text at 0x100000 and leaves no room before it, and in .bss the ring cost
# 262,116 bytes of alignment padding (docs/port/notes/menu-heap.md). So the port links with that
# script copied here at configure time with one change: a .mfifo section (zsys_spr.cpp puts the ring
# there) at 0x100000 and .text right after it, as in the ELF. Not an option: it is the ELF's layout.
set(_socom_sdk_linkfile "$ENV{PS2SDK}/ee/startup/linkfile")
if(NOT EXISTS "${_socom_sdk_linkfile}")
  message(FATAL_ERROR "socom port: no ps2sdk linker script at ${_socom_sdk_linkfile} (PS2SDK)")
endif()
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_socom_sdk_linkfile}")
file(READ "${_socom_sdk_linkfile}" _socom_linkfile)
string(REPLACE ".text 0x00100000: {"
  ".mfifo 0x00100000: {\n\t\tKEEP(*(.mfifo))\n\t} :text\n\n\t.text ALIGN(128): {"
  _socom_port_linkfile "${_socom_linkfile}")
if(_socom_port_linkfile STREQUAL _socom_linkfile)
  message(FATAL_ERROR "socom port: the ps2sdk linker script has no '.text 0x00100000: {' to put .mfifo before")
endif()
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/socom_port.ld" "${_socom_port_linkfile}")
string(REGEX REPLACE "-T[^ ]*/ee/startup/linkfile" "-T${CMAKE_CURRENT_BINARY_DIR}/socom_port.ld"
  CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS}")
if(NOT CMAKE_EXE_LINKER_FLAGS MATCHES "socom_port.ld")
  message(FATAL_ERROR "socom port: CMAKE_EXE_LINKER_FLAGS has no ps2sdk -T linkfile to replace: ${CMAKE_EXE_LINKER_FLAGS}")
endif()

# Heap options, all OFF by default: deviations from the original game's heap use, for the menus'
# archive buffer that the original itself sometimes puts above the program break (about one return to
# the menus in eight; docs/port/notes/menu-heap.md, frame-limiter.md). Each is test-proven in one run.
#   SOCOM_PORT_HEAP_KEEP_MENU_ZAR   keep the place of run/uizanim.zar's 2.6 MB data buffer reserved
#                                   from the menus' UnInit across the mission to their next Init
#                                   (CMenuState, st_menu.cpp): the buffer always finds its hole; the
#                                   mission has 2.6 MB less heap.
#   SOCOM_PORT_HEAP_SHRINK_TEXLIST  after a mission, replace the texture manager's grown buffer list
#                                   with a tight copy (CCoreState unload, st_core.cpp), so its block no
#                                   longer bounds the top of the heap.
option(SOCOM_PORT_HEAP_KEEP_MENU_ZAR "port deviation: keep the menus' archive buffer reserved across a mission" OFF)
option(SOCOM_PORT_HEAP_SHRINK_TEXLIST "port deviation: shrink the texture manager's buffer list after a mission" OFF)
foreach(_opt SOCOM_PORT_HEAP_KEEP_MENU_ZAR SOCOM_PORT_HEAP_SHRINK_TEXLIST)
  if(${_opt})
    message(STATUS "socom port: heap option ${_opt}")
    target_compile_definitions(socom_game PRIVATE ${_opt})
  endif()
endforeach()

add_executable(socom_port ${SOCOM_COMPAT_SOURCES})
set_target_properties(socom_port PROPERTIES OUTPUT_NAME "socom_port.elf" LINKER_LANGUAGE CXX)
target_include_directories(socom_port PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/compat/include")
target_compile_definitions(socom_port PRIVATE SOCOM_PORT _EE SOCOM_PORT_TRACE_ON)
target_link_libraries(socom_port PRIVATE
  -Wl,--whole-archive socom_game -Wl,--no-whole-archive
  -liopreboot -lpatches -lcdvd -lpad -lmc -lmpeg -ldebug -leedebug -lkernel)

# Test hook, off by default: a scratch build configured with
#   -DSOCOM_PORT_FAKE_PAD=<when>:<BUTTON>[,<when>:<BUTTON>...]
# synthesizes pad port 0 and presses the buttons at those times (compat/libpad.c; <when> is a
# pad read count, or <anchor>[.<k>]+<fields>: 60 Hz fields after a point the game reached,
# e.g. menu+120:CROSS; <when>:<AXIS>=<0..255>[+<n>] terms move a stick; syntax in
# port/test-hooks/README.md), so batch emulator runs can drive the menus. The anchors come from
# port/test/fake_pad_anchors.cpp, compiled only here. Never set it in the default build.
set(SOCOM_PORT_FAKE_PAD "" CACHE STRING "port test hook: scripted pad 0 presses (empty = off)")
if(SOCOM_PORT_FAKE_PAD)
  message(STATUS "socom port: TEST HOOK SOCOM_PORT_FAKE_PAD=${SOCOM_PORT_FAKE_PAD}")
  target_compile_definitions(socom_port PRIVATE "SOCOM_PORT_FAKE_PAD=${SOCOM_PORT_FAKE_PAD}")
  set(_fake_pad_anchors "${CMAKE_CURRENT_SOURCE_DIR}/test/fake_pad_anchors.cpp")
  target_sources(socom_port PRIVATE "${_fake_pad_anchors}")
  set_source_files_properties("${_fake_pad_anchors}" PROPERTIES
    COMPILE_OPTIONS "${SOCOM_PORT_FLAGS}"
    INCLUDE_DIRECTORIES "${SOCOM_ROOT}/src")
endif()

# Test hook, off by default: a scratch build configured with -DSOCOM_PORT_VU1_TEST=ON draws one
# hand-built VU1 triangle at the end of every menu frame through CVisual::Render (port/test/
# vu1_test.cpp wraps zSysFifoEnd), to prove the EE -> VU1 packet contract before the game
# loop runs. Never set it in the default build.
option(SOCOM_PORT_VU1_TEST "port test hook: one VU1 triangle per menu frame" OFF)
if(SOCOM_PORT_VU1_TEST)
  message(STATUS "socom port: TEST HOOK SOCOM_PORT_VU1_TEST")
  set(_vu1_test "${CMAKE_CURRENT_SOURCE_DIR}/test/vu1_test.cpp")
  target_sources(socom_port PRIVATE "${_vu1_test}")
  set_source_files_properties("${_vu1_test}" PROPERTIES
    COMPILE_OPTIONS "${SOCOM_PORT_FLAGS}"
    INCLUDE_DIRECTORIES "${SOCOM_ROOT}/src")
  target_link_options(socom_port PRIVATE "-Wl,--wrap=_Z11zSysFifoEndv")
endif()

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
