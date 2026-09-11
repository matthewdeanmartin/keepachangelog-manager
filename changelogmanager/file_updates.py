"""Atomic individual writes and rollback for ordinary multi-file failures."""

from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path


def atomic_write_bytes(path: Path, content: bytes) -> None:
    # Follow existing symlinks rather than replacing the link itself.
    path = path.resolve()
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            temporary.chmod(stat.S_IMODE(path.stat().st_mode))
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_write_text(path: Path, content: str) -> None:
    atomic_write_bytes(path, content.encode("utf-8"))


@contextmanager
def rollback_file_updates(paths: Sequence[Path]) -> Iterator[None]:
    """Restore original bytes on exceptions, not on process/power failure.

    Each replacement is atomic; multiple replacements are not a filesystem
    transaction. Report restoration failures without hiding the original error.
    """
    originals = {
        path.resolve(): path.read_bytes() if path.exists() else None for path in paths
    }
    try:
        yield
    except Exception as original:
        failures = []
        for path, content in originals.items():
            try:
                if content is None:
                    path.unlink(missing_ok=True)
                elif not path.exists() or path.read_bytes() != content:
                    atomic_write_bytes(path, content)
            except OSError:
                failures.append(str(path))
        if failures:
            raise OSError(
                "Could not restore files: " + ", ".join(failures)
            ) from original
        raise
