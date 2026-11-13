#!/bin/bash
# lg.sh <log> [n] [extra-regex]: the interesting lines of a PCSX2 boot log (hook and port traces,
# STOPs, exceptions, task and syscall faults); first n (default 40).
grep -a -E "HOOK|DIAG|CORE|PIPE|GRID|STOP|exception|epc|stack text|TASK|Syscall|LOAD: testLoad${3:+|$3}" "$1" | grep -v "PIPE: walk from 320 0 320" | head -n "${2:-40}"
