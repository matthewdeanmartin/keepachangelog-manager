# SPDX-License-Identifier: MIT
# Vendored and trimmed from jiggle_version/discover.py (jiggle-version 2.1.1).
"""Discover potential version source files in a project.

A version bump rewrites files in place, so the walk here is deliberately
conservative: anything that is not plausibly the *project's own* source is
skipped. Three independent guards apply, and a directory is skipped if any one
of them fires:

1. :data:`DEFAULT_IGNORE_DIRS` / :data:`IGNORE_DIR_GLOBS` -- an unconditional
   deny-list of directory kinds that hold third-party code: virtualenvs,
   ``site-packages``, package caches, ``node_modules``, build output.
2. :data:`VENV_SENTINEL_FILES` -- any directory containing a ``pyvenv.cfg`` is a
   virtualenv no matter what it is named (``.venv315rc2``, ``env2``, ...).
3. ``.gitignore`` -- restoring the behavior upstream got from ``pathspec``, via
   the stdlib matcher in :mod:`.gitignore`.

Guards 1 and 2 apply regardless of ignore-file contents; ``.gitignore`` only
ever *adds* exclusions. Nothing outside ``project_root`` is ever visited.
"""

from __future__ import annotations

import fnmatch
import logging
from pathlib import Path

from changelogmanager.vendor.jiggle_version.gitignore import (
    GitIgnore,
    load_gitignore,
    relative_posix,
)

# Files to search for recursively in the project tree.
RECURSIVE_SEARCH_FILES = ["_version.py", "__version__.py", "__about__.py"]

# Statically named files to check for only in the project root.
STATIC_SEARCH_FILES = ["pyproject.toml", "setup.cfg", "setup.py"]

# Directory names that never contain the project's own version, matched exactly.
DEFAULT_IGNORE_DIRS = {
    # VCS / editor / tooling metadata
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    # Python caches and tool state
    "__pycache__",
    ".mypy_cache",
    ".pytype",
    ".pyre",
    ".ruff_cache",
    ".pytest_cache",
    ".hypothesis",
    # Installed third-party code -- the bug this deny-list exists for
    "site-packages",
    "dist-packages",
    ".tox",
    ".nox",
    ".eggs",
    "node_modules",
    # Package manager caches: corruption here re-seeds every rebuilt env
    ".uv",
    ".uv-cache",
    ".pip-cache",
    ".cache",
    ".pdm-build",
    "__pypackages__",
    # Build output
    "build",
    "dist",
}

# Directory name globs, for families that are not a fixed name. ``.venv315rc2``
# and ``venv-3.13`` are as much virtualenvs as ``.venv`` is.
IGNORE_DIR_GLOBS = (
    ".venv*",
    "venv*",
    "*.egg-info",
    "*.dist-info",
    "*.egg",
)

# A directory containing any of these is a virtualenv, whatever it is named.
VENV_SENTINEL_FILES = ("pyvenv.cfg",)

LOGGER = logging.getLogger(__name__)


def is_ignored_dir_name(name: str) -> bool:
    """True if a directory named ``name`` must never be descended into."""
    if name in DEFAULT_IGNORE_DIRS:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in IGNORE_DIR_GLOBS)


def is_virtualenv_dir(path: Path) -> bool:
    """True if ``path`` looks like a virtualenv root (has a ``pyvenv.cfg``)."""
    for sentinel in VENV_SENTINEL_FILES:
        try:
            if (path / sentinel).is_file():
                return True
        except OSError as exc:
            LOGGER.warning("Skipping unreadable path %s: %s", path / sentinel, exc)
    return False


def find_source_files(
    project_root: Path,
    ignore_paths: list[str] | None = None,
    *,
    use_gitignore: bool = True,
) -> list[Path]:
    """Scan ``project_root`` for potential version source files.

    Args:
        project_root: The root directory of the project to scan.
        ignore_paths: Relative paths (to ``project_root``) to explicitly ignore.
        use_gitignore: Honor ``project_root/.gitignore``. Disabling this drops
            only guard 3; the hard directory excludes still apply.

    Returns:
        A sorted list of Path objects for all found source files.
    """
    LOGGER.debug("project root %s, ignore_paths %s", project_root, ignore_paths)
    found_files: set[Path] = set()

    explicit_ignore_set = {(project_root / p).resolve() for p in (ignore_paths or [])}
    gitignore = load_gitignore(project_root) if use_gitignore else None

    _walk_and_discover(
        current_dir=project_root,
        project_root=project_root,
        found_files=found_files,
        explicit_ignore_set=explicit_ignore_set,
        gitignore=gitignore,
    )

    return sorted(found_files)


def _is_explicitly_ignored(path: Path, ignored_paths: set[Path]) -> bool:
    """True if ``path`` equals or is a descendant of any ignored path."""
    abs_path = path.resolve()
    for raw in ignored_paths:
        ignored = raw.resolve()
        if abs_path == ignored or ignored in abs_path.parents:
            return True
    return False


def _walk_and_discover(
    *,
    current_dir: Path,
    project_root: Path,
    found_files: set[Path],
    explicit_ignore_set: set[Path],
    gitignore: GitIgnore | None = None,
) -> None:
    """Recursively walk directories to find source files."""
    try:
        items = list(current_dir.iterdir())
    except OSError as exc:
        LOGGER.warning("Skipping unreadable directory %s: %s", current_dir, exc)
        return

    for item in items:
        if _is_explicitly_ignored(item, explicit_ignore_set):
            continue

        try:
            is_dir = item.is_dir()
            is_file = item.is_file()
        except OSError as exc:
            LOGGER.warning("Skipping unreadable path %s: %s", item, exc)
            continue

        # Never follow a symlink out of (or back into) the tree.
        try:
            if item.is_symlink():
                LOGGER.debug("Skipping symlink %s", item)
                continue
        except OSError:
            continue

        if is_dir and is_ignored_dir_name(item.name):
            LOGGER.debug("Skipping excluded directory %s", item)
            continue

        if is_dir and is_virtualenv_dir(item):
            LOGGER.debug("Skipping virtualenv %s (has pyvenv.cfg)", item)
            continue

        if gitignore is not None:
            relative = relative_posix(item, project_root)
            if relative and gitignore.is_ignored(relative, is_dir=is_dir):
                LOGGER.debug("Skipping gitignored path %s", item)
                continue

        if is_dir:
            # A top-level package dir's __init__.py is a version candidate.
            init_file = item / "__init__.py"
            try:
                has_init = init_file.is_file()
            except OSError as exc:
                LOGGER.warning("Skipping unreadable path %s: %s", init_file, exc)
                has_init = False

            if has_init and current_dir == project_root:
                found_files.add(init_file)

            _walk_and_discover(
                current_dir=item,
                project_root=project_root,
                found_files=found_files,
                explicit_ignore_set=explicit_ignore_set,
                gitignore=gitignore,
            )

        elif is_file:
            # Root-only statics.
            if item.name in STATIC_SEARCH_FILES and item.parent == project_root:
                found_files.add(item)
            # Recursive targets.
            elif item.name in RECURSIVE_SEARCH_FILES:
                found_files.add(item)
