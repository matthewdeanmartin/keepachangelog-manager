# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""pyproject.toml / __version__ bumping via a vendored jiggle-version subset."""

from __future__ import annotations

from pathlib import Path

from changelogmanager.runtime_logging import get_logger
from changelogmanager.vendor.jiggle_version import (
    find_source_files,
    update_pyproject_toml,
    update_python_file,
)

logger = get_logger(__name__)

# The version-bump helpers are now vendored (changelogmanager.vendor.jiggle_version),
# so they are always importable. Kept as a module constant for backwards
# compatibility with callers/tests that reference it.
HAS_JIGGLE = True


def jiggle_available() -> bool:
    """Returns True; the version-bump helpers are vendored and always available."""
    return HAS_JIGGLE


def bump_version_files(
    new_version: str,
    *,
    project_root: Path | None = None,
    pyproject_only: bool = False,
) -> list[Path]:
    """Bumps version strings in pyproject.toml and optionally Python source files.

    Returns the list of files that were modified.
    """
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
