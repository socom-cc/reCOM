"""Fail-closed interprocess lock files for control-state mutations."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .util import SocomError


@contextmanager
def exclusive_state_lock(path: Path) -> Iterator[Path]:
    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SocomError(
            f"state lock exists at {lock_path}; another mutation may be active"
        ) from exc
    try:
        os.write(
            descriptor,
            f"pid={os.getpid()} target={path.resolve()}\n".encode(
                "ascii", errors="replace"
            ),
        )
        os.fsync(descriptor)
        yield lock_path
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
