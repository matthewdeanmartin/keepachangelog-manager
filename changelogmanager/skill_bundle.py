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


class Traversable(Protocol):  # pylint: disable=missing-function-docstring
    """Protocol for bundled resource traversables."""

    @property
    def name(self) -> str:
        """Return the resource name."""
        raise NotImplementedError

    def is_dir(self) -> bool:
        """Return whether the resource is a directory."""
        raise NotImplementedError

    def iterdir(self) -> Iterator[Traversable]:
        """Iterate over child resources."""
        raise NotImplementedError

    def joinpath(self, child: str, /) -> Traversable:
        """Return a child resource."""
        raise NotImplementedError

    def read_bytes(self) -> bytes:
        """Read the resource bytes."""
        raise NotImplementedError


class SkillFrontmatterError(ValueError):
    """Raised when a SKILL.md is missing usable YAML frontmatter."""


def parse_skill_frontmatter(text: str) -> dict[str, str]:
    """Parses the leading ``---`` YAML block of a SKILL.md into a dict.

    Only the flat ``key: value`` subset a skill header uses is understood; that
    is all the format allows, and it avoids a PyYAML dependency.

    Raises:
        SkillFrontmatterError: if the block is absent, unterminated, or has no
            ``name``/``description``.

    A bare ``mdformat`` run (one without ``mdformat-frontmatter``) rewrites the
    ``---`` fences into a thematic break and folds the keys into a heading. The
    skill then still installs and lists, but its description renders as
    underscores, so agents never select it -- a silent failure this parser turns
    into a loud one.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillFrontmatterError(
            "SKILL.md must start with a '---' YAML frontmatter fence "
            "(a bare mdformat run destroys it)"
        )

    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        raise SkillFrontmatterError(
            "SKILL.md frontmatter is not terminated by a closing '---'"
        ) from None

    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise SkillFrontmatterError(
                f"SKILL.md frontmatter line is not 'key: value': {line!r}"
            )
        fields[key.strip()] = value.strip().strip("'\"")

    for required in ("name", "description"):
        if not fields.get(required):
            raise SkillFrontmatterError(
                f"SKILL.md frontmatter is missing a non-empty '{required}'"
            )
    return fields


def validate_skill_dir(skill_dir: Path) -> dict[str, str]:
    """Validates the SKILL.md in ``skill_dir`` and returns its frontmatter.

    Raises:
        SkillFrontmatterError: if SKILL.md is missing or its header is unusable.
    """
    skill_file = skill_dir / "SKILL.md"
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillFrontmatterError(f"Cannot read {skill_file}: {exc}") from exc
    return parse_skill_frontmatter(text)


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
    copy_tree(bundled_skill_root(), target)
    # An exported skill with broken frontmatter installs and lists but never
    # triggers, because agents select on the description. Fail loudly instead.
    frontmatter = validate_skill_dir(target)
    logger.log(VERBOSE, "Exported skill %s validated", frontmatter["name"])
    return target


def copy_tree(source: Traversable, destination: Path) -> None:
    if destination.exists():
        logger.error("Skill export destination already exists: %s", destination)
        raise FileExistsError(str(destination))

    logger.log(VERBOSE, "Creating skill directory %s", destination)
    destination.mkdir(parents=True, exist_ok=False)
    for child in source.iterdir():
        child_path = destination / child.name
        if child.is_dir():
            logger.log(VERBOSE, "Recursively copying skill directory %s", child_path)
            copy_tree(child, child_path)
            continue
        logger.log(VERBOSE, "Copying skill file %s", child_path)
        child_path.write_bytes(child.read_bytes())
