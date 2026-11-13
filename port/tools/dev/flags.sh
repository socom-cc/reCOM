#!/bin/bash
# flags.sh <build>: the C++ compile flags of the socom_game library of a build
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
B=$(dirname "$(socom_build_elf "$1")")
cat "$(find "$B" -path '*socom_game.dir/flags.make' | head -1)"
