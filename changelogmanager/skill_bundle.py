# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Helpers for bundled changelogmanager skills."""

from __future__ import annotations

from collections.abc import Iterator
from importlib import resources
from pathlib import Path
from typing import Protocol

SKILL_NAME = "keepachangelog-manager-cli"
COPILOT_SKILLS_DIR = Path(".github") / "skills"
CLAUDE_PROJECT_SKILLS_DIR = Path(".claude") / "skills"
CLAUDE_PERSONAL_SKILLS_DIR = Path.home() / ".claude" / "skills"


class Traversable(Protocol):
    """Protocol for importlib resource traversables."""

    name: str

    def is_dir(self) -> bool: ...

    def iterdir(self) -> Iterator["Traversable"]: ...

    def joinpath(self, child: str) -> "Traversable": ...

    def read_bytes(self) -> bytes: ...


def bundled_skill_root() -> Traversable:
    """Returns the bundled skill directory."""

    return resources.files("changelogmanager.skills").joinpath(SKILL_NAME)


def resolve_export_path(destination: str | Path) -> Path:
    """Resolves the final skill directory from a root or full path."""

    path = Path(destination).expanduser()
    if path.name == SKILL_NAME:
        return path
    return path / SKILL_NAME


def export_skill(destination: str | Path) -> Path:
    """Copies the bundled skill to a destination directory."""

    target = resolve_export_path(destination)
    _copy_tree(bundled_skill_root(), target)
    return target


def _copy_tree(source: Traversable, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(str(destination))

    destination.mkdir(parents=True, exist_ok=False)
    for child in source.iterdir():
        child_path = destination / child.name
        if child.is_dir():
            _copy_tree(child, child_path)
            continue
        child_path.write_bytes(child.read_bytes())
