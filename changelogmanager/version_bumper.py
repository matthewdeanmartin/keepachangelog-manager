# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""pyproject.toml / __version__ bumping via a vendored jiggle-version subset."""

from __future__ import annotations

from pathlib import Path

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.file_updates import rollback_file_updates
from changelogmanager.runtime_logging import get_logger
from changelogmanager.vendor.jiggle_version import (
    find_source_files,
    update_pyproject_toml,
    update_python_file,
)
from changelogmanager.versioning import parse_version

logger = get_logger(__name__)

# The version-bump helpers are now vendored (changelogmanager.vendor.jiggle_version),
# so they are always importable. Kept as a module constant for backwards
# compatibility with callers/tests that reference it.
HAS_JIGGLE = True


def jiggle_available() -> bool:
    """Returns True; the version-bump helpers are vendored and always available."""
    return HAS_JIGGLE


def plan_version_files(
    *,
    project_root: Path | None = None,
    pyproject_only: bool = False,
    version_files: tuple[Path, ...] | None = None,
) -> list[Path]:
    """Returns the files a bump would consider, without writing anything.

    This is what ``--dry-run`` enumerates. A path listed here is a *candidate*:
    :func:`bump_version_files` may still decline to write it (no version
    assignment, or a build-backend-generated file), so the real bump can touch
    fewer files than this lists -- never more.
    """
    if version_files is not None:
        for path in version_files:
            if not path.is_file():
                raise logging.Error(message=f"Version file does not exist: {path}")
        return [
            path
            for path in version_files
            if not pyproject_only or path.name == "pyproject.toml"
        ]
    root = project_root or Path.cwd()
    candidates: list[Path] = []

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        candidates.append(pyproject)

    if not pyproject_only:
        for path in find_source_files(root):
            if path != pyproject and path.suffix == ".py":
                candidates.append(path)

    return candidates


def bump_version_files(
    new_version: str,
    *,
    project_root: Path | None = None,
    pyproject_only: bool = False,
    version_files: tuple[Path, ...] | None = None,
    versioning_scheme: str = "semver",
) -> list[Path]:
    """Bumps version strings in pyproject.toml and optionally Python source files.

    The search deliberately never descends into virtualenvs, ``site-packages``,
    package caches, or gitignored directories, and refuses files a build backend
    marks as generated -- rewriting an installed third-party package's
    ``__version__`` corrupts the environment (and any cache it was seeded from).

    Returns the list of files that were actually modified.
    """
    try:
        parse_version(new_version, versioning_scheme)
    except ValueError as exc:
        raise logging.Error(
            message=f"Invalid {versioning_scheme} version: {new_version}"
        ) from exc
    paths = plan_version_files(
        project_root=project_root,
        pyproject_only=pyproject_only,
        version_files=version_files,
    )
    bumped: list[Path] = []
    with rollback_file_updates(paths):
        for path in paths:
            before = path.read_bytes()
            updated = (
                update_pyproject_toml(path, new_version)
                if path.name == "pyproject.toml"
                else update_python_file(path, new_version)
            )
            if version_files is not None and updated is False:
                raise logging.Error(
                    message=f"Explicit version file has no editable version: {path}"
                )
            if path.read_bytes() != before:
                bumped.append(path)
    return bumped
