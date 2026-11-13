#!/bin/bash
# hdr.sh <build>: section headers of a port build
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
mips64r5900el-ps2-elf-objdump -h "$(socom_build_elf "$1")"
