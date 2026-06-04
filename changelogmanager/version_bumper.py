# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""pyproject.toml / __version__ bumping via jiggle-version (optional dependency)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.runtime_logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

try:
    from jiggle_version.discover import find_source_files  # type: ignore[import-not-found]
    from jiggle_version.update import (  # type: ignore[import-not-found]
        update_pyproject_toml,
        update_python_file,
    )

    HAS_JIGGLE = True
except ImportError:
    HAS_JIGGLE = False


def jiggle_available() -> bool:
    """Returns True when jiggle-version is importable."""
    return HAS_JIGGLE


def bump_version_files(
    new_version: str,
    *,
    project_root: Path | None = None,
    pyproject_only: bool = False,
) -> list[Path]:
    """Bumps version strings in pyproject.toml and optionally Python source files.

    Returns the list of files that were modified.

    Raises logging.Error if jiggle-version is not installed.
    """
    if not HAS_JIGGLE:
        raise logging.Error(
            message=(
                "jiggle-version is required to bump version files. "
                "Install it with: pip install 'keepachangelog-manager-fork[jiggle]'"
            )
        )

    root = project_root or Path.cwd()
    bumped: list[Path] = []

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        logger.info("Bumping version in %s to %s", pyproject, new_version)
        update_pyproject_toml(pyproject, new_version)
        bumped.append(pyproject)

    if not pyproject_only:
        source_files = find_source_files(root)
        for path in source_files:
            if path == pyproject:
                continue
            if path.suffix == ".py":
                logger.info("Bumping version in %s to %s", path, new_version)
                update_python_file(path, new_version)
                bumped.append(path)

    logger.info("Version bumped to %s in %d file(s)", new_version, len(bumped))
    return bumped
