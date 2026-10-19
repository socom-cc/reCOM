"""Fail-closed interprocess lock files for control-state mutations."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .util import SocomError


LOCK_WAIT_SECONDS = 30.0


@contextmanager
def exclusive_state_lock(path: Path, wait_seconds: float | None = None) -> Iterator[Path]:
    """Hold the lock file beside ``path``.

    A held lock is waited for (parallel agents mutate the tracker in quick
    succession) but never broken: after ``wait_seconds`` the mutation fails,
    so a stale lock from a crashed process still needs a person to remove it.
    """

    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + (LOCK_WAIT_SECONDS if wait_seconds is None else wait_seconds)
    while True:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise SocomError(
                    f"state lock exists at {lock_path}; another mutation may be active"
                ) from exc
            time.sleep(0.2)
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
