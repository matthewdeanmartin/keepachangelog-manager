# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Helpers for bundled changelogmanager skills."""

from __future__ import annotations

from collections.abc import Iterator
from importlib import resources
from pathlib import Path
from typing import Protocol

from changelogmanager.runtime_logging import VERBOSE, get_logger

SKILL_NAME = "keepachangelog-manager-cli"
COPILOT_SKILLS_DIR = Path(".github") / "skills"
CLAUDE_PROJECT_SKILLS_DIR = Path(".claude") / "skills"
CLAUDE_PERSONAL_SKILLS_DIR = Path.home() / ".claude" / "skills"
logger = get_logger(__name__)


class Traversable(Protocol):
    """Protocol for importlib resource traversables."""

    name: str

    def is_dir(self) -> bool: ...

    def iterdir(self) -> Iterator[Traversable]: ...

    def joinpath(self, child: str) -> Traversable: ...

    def read_bytes(self) -> bytes: ...


def bundled_skill_root() -> Traversable:
    """Returns the bundled skill directory."""

    logger.log(VERBOSE, "Resolving bundled skill root")
    return resources.files("changelogmanager.skills").joinpath(SKILL_NAME)


def resolve_export_path(destination: str | Path) -> Path:
    """Resolves the final skill directory from a root or full path."""

    path = Path(destination).expanduser()
    logger.log(VERBOSE, "Resolving skill export path from %s", path)
    if path.name == SKILL_NAME:
        return path
    return path / SKILL_NAME


def export_skill(destination: str | Path) -> Path:
    """Copies the bundled skill to a destination directory."""

    target = resolve_export_path(destination)
    logger.info("Exporting bundled skill to %s", target)
    _copy_tree(bundled_skill_root(), target)
    return target


def _copy_tree(source: Traversable, destination: Path) -> None:
    if destination.exists():
        logger.error("Skill export destination already exists: %s", destination)
        raise FileExistsError(str(destination))

    logger.log(VERBOSE, "Creating skill directory %s", destination)
    destination.mkdir(parents=True, exist_ok=False)
    for child in source.iterdir():
        child_path = destination / child.name
        if child.is_dir():
            logger.log(VERBOSE, "Recursively copying skill directory %s", child_path)
            _copy_tree(child, child_path)
            continue
        logger.log(VERBOSE, "Copying skill file %s", child_path)
        child_path.write_bytes(child.read_bytes())
