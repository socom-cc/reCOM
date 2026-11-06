# Functional port lane: build src/ with the pinned ps2dev toolchain.
#
# Configure inside the Linux side (WSL) with the toolchain file:
#   cmake -S port -B <build> -DCMAKE_TOOLCHAIN_FILE=$PS2DEV/share/ps2dev.cmake
#   cmake --build <build> -- -k        # keep going to collect every failure
#
# Targets:
#   socom_game  - every src/ unit except *_holding.cpp (never built)
#   socom_port  - the ELF: socom_game + port/compat + ps2sdk
# Nothing built here is evidence for the matching lane.
cmake_minimum_required(VERSION 3.13)
project(socom_port C CXX)

set(SOCOM_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")
get_filename_component(SOCOM_ROOT "${SOCOM_ROOT}" ABSOLUTE)

file(GLOB_RECURSE SOCOM_GAME_SOURCES CONFIGURE_DEPENDS
  "${SOCOM_ROOT}/src/*.cpp" "${SOCOM_ROOT}/src/*.c")
list(FILTER SOCOM_GAME_SOURCES EXCLUDE REGEX "_holding\\.cpp$")

set(SOCOM_PORT_FLAGS
  -std=gnu++17
  -fno-exceptions
  -fno-rtti
  -include "${CMAKE_CURRENT_SOURCE_DIR}/include/socom_port_prefix.h")

add_library(socom_game STATIC ${SOCOM_GAME_SOURCES})
target_compile_definitions(socom_game PRIVATE SOCOM_PORT _EE)
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
target_link_libraries(socom_port PRIVATE
  -Wl,--whole-archive socom_game -Wl,--no-whole-archive
  -lpatches -ldebug -lkernel)
