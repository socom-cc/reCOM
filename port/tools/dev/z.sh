#!/bin/bash
# z.sh <start-hex> <end-hex|+size> [reg=Class,...]: compact annotated disassembly of
# support/socom.elf (dis.sh | disx.py | cz.py). Runs from WSL/Linux, or from Git Bash on Windows
# (dis.sh then goes through wsl.exe, distribution $SOCOM_WSL_DISTRO).
set -u
H=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
S=$1; E=$2
case "$E" in +*) E=$(printf '0x%x' $(( S + ${E#+} )));; esac
T=(); [ -n "${3:-}" ] && T=(-t "$3")
if command -v wslpath >/dev/null 2>&1 || [ "$(uname -s)" = Linux ]; then
  PY=python3
else
  PY=python
fi
if [ $PY = python3 ]; then
  bash "$H/dis.sh" "$S" "$E"
else
  W=$(cygpath -w "$H/dis.sh")
  D=(); [ -n "${SOCOM_WSL_DISTRO:-}" ] && D=(-d "$SOCOM_WSL_DISTRO")
  L=$(MSYS_NO_PATHCONV=1 wsl.exe "${D[@]}" -e wslpath -u "$W" 2>/dev/null | tr -d '\r')
  MSYS_NO_PATHCONV=1 wsl.exe "${D[@]}" -e bash "$L" "$S" "$E" 2>/dev/null
fi | "$PY" "$H/disx.py" | "$PY" "$H/cz.py" "${T[@]}"
