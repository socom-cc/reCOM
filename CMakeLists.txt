cmake_minimum_required(VERSION 3.25)

project(soCOMReconstruction LANGUAGES NONE)

find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)

enable_testing()

add_test(
  NAME socom-tooling
  COMMAND "${Python3_EXECUTABLE}" -m pytest -q tests/tools
)
set_tests_properties(
  socom-tooling
  PROPERTIES
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    ENVIRONMENT "PYTHONPATH=${CMAKE_SOURCE_DIR}"
)

add_custom_target(
  socom-doctor
  COMMAND
    "${Python3_EXECUTABLE}" tools/socom.py doctor
    --infrastructure-only --ghidra
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  USES_TERMINAL
)
