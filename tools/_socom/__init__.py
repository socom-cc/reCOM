"""soCOM reconstruction tooling.

The package intentionally uses only the Python standard library.  The
reference reader and tracker are project-owned so the reconstruction does not
depend on a particular LLVM, Ghidra, or third-party DWARF version.
"""

from .constants import PROJECT_NAME, SCHEMA_VERSION

__all__ = ["PROJECT_NAME", "SCHEMA_VERSION"]
