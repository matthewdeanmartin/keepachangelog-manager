# SPDX-License-Identifier: MIT
# Vendored and trimmed from jiggle_version/discover.py (jiggle-version 2.1.1).
"""Discover potential version source files in a project.

Upstream walked the tree honoring ``.gitignore`` via ``pathspec``. That
third-party dependency is intentionally dropped here: matching is reduced to the
static :data:`DEFAULT_IGNORE_DIRS` set, which already covers the directories a
version bump must never descend into (``.git``, ``.tox``, ``.venv``,
``__pycache__``). The set of filenames searched for is unchanged, so the result
for a normal project layout matches upstream.
"""
from __future__ import annotations

import logging
from pathlib import Path

# Files to search for recursively in the project tree.
RECURSIVE_SEARCH_FILES = ["_version.py", "__version__.py", "__about__.py"]

# Statically named files to check for only in the project root.
STATIC_SEARCH_FILES = ["pyproject.toml", "setup.cfg", "setup.py"]

# Directories to always ignore (replaces upstream's pathspec/.gitignore walk).
DEFAULT_IGNORE_DIRS = {".git", ".tox", ".venv", "__pycache__"}

LOGGER = logging.getLogger(__name__)


def find_source_files(
    project_root: Path, ignore_paths: list[str] | None = None
) -> list[Path]:
    """Scan ``project_root`` for potential version source files.

    Args:
        project_root: The root directory of the project to scan.
        ignore_paths: Relative paths (to ``project_root``) to explicitly ignore.

    Returns:
        A sorted list of Path objects for all found source files.
    """
    LOGGER.debug("project root %s, ignore_paths %s", project_root, ignore_paths)
    found_files: set[Path] = set()

    explicit_ignore_set = {(project_root / p).resolve() for p in (ignore_paths or [])}

    _walk_and_discover(
        current_dir=project_root,
        project_root=project_root,
        found_files=found_files,
        explicit_ignore_set=explicit_ignore_set,
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
) -> None:
    """Recursively walk directories to find source files."""
    try:
        items = list(current_dir.iterdir())
    except OSError as exc:
        LOGGER.warning("Skipping unreadable directory %s: %s", current_dir, exc)
        return

    for item in items:
        if item.name in DEFAULT_IGNORE_DIRS or _is_explicitly_ignored(
            item, explicit_ignore_set
        ):
            continue

        try:
            is_dir = item.is_dir()
            is_file = item.is_file()
        except OSError as exc:
            LOGGER.warning("Skipping unreadable path %s: %s", item, exc)
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
            )

        elif is_file:
            # Root-only statics.
            if item.name in STATIC_SEARCH_FILES and item.parent == project_root:
                found_files.add(item)
            # Recursive targets.
            elif item.name in RECURSIVE_SEARCH_FILES:
                found_files.add(item)
