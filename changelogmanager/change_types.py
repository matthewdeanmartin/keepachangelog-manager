# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Categories of changes"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

UNRELEASED_ENTRY: str = "unreleased"
DEFAULT_CHANGELOG_FILE: str = "CHANGELOG.md"


class VersionCore(Enum):
    """SemVer Version Cores"""

    MAJOR = 3
    MINOR = 2
    PATCH = 1


@dataclass
class Category:
    """Category for a change.

    ``ships_to_changelog`` marks whether entries of this category are eligible
    to flow into a released ``CHANGELOG.md``. The six Keep a Changelog
    categories ship; the non-shipping categories below track real work (tests,
    chores, refactors) that should never appear in a user-facing changelog.
    """

    emoji: str
    title: str
    bump: VersionCore
    ships_to_changelog: bool = True


CATEGORIES: dict[str, Category] = {
    "added": Category(emoji="rocket", title="New Features", bump=VersionCore.MINOR),
    "changed": Category(
        emoji="scissors", title="Updated Features", bump=VersionCore.PATCH
    ),
    "deprecated": Category(
        emoji="warning", title="Deprecation", bump=VersionCore.PATCH
    ),
    "removed": Category(emoji="no_entry_sign", title="Removed", bump=VersionCore.MAJOR),
    "fixed": Category(emoji="bug", title="Bug Fixes", bump=VersionCore.PATCH),
    "security": Category(
        emoji="closed_lock_with_key", title="Security Changes", bump=VersionCore.MINOR
    ),
}

TYPES_OF_CHANGE: list[str] = list(CATEGORIES.keys())

# Non-shipping categories: real, trackable work for TASKS.md / task fragments
# that must never reach a user-facing changelog. Kept separate from CATEGORIES
# so existing changelog code (and the `add` / `fragments` choices that use
# TYPES_OF_CHANGE) only ever sees the six shipping Keep a Changelog types.
NON_SHIPPING: dict[str, Category] = {
    "internal": Category(
        emoji="hammer_and_wrench",
        title="Internal",
        bump=VersionCore.PATCH,
        ships_to_changelog=False,
    ),
    "chore": Category(
        emoji="broom", title="Chores", bump=VersionCore.PATCH, ships_to_changelog=False
    ),
    "docs": Category(
        emoji="book", title="Docs", bump=VersionCore.PATCH, ships_to_changelog=False
    ),
    "test": Category(
        emoji="test_tube",
        title="Tests",
        bump=VersionCore.PATCH,
        ships_to_changelog=False,
    ),
    "spike": Category(
        emoji="microscope",
        title="Spikes",
        bump=VersionCore.PATCH,
        ships_to_changelog=False,
    ),
}

# Every category the task-fragment tooling understands. Unknown categories are
# still accepted by the fragment parser (treated as non-shipping by default);
# this table just carries display metadata for the ones we know about.
ALL_CATEGORIES: dict[str, Category] = {**CATEGORIES, **NON_SHIPPING}

ALL_TYPES_OF_CHANGE: list[str] = list(ALL_CATEGORIES.keys())


def ships_to_changelog(change_type: str | None) -> bool:
    """Whether a category may flow into a released changelog.

    Unknown / unrecognized categories default to **False** so a typo'd or
    team-custom category can never silently leak into the public changelog.
    """

    if change_type is None:
        return False
    category = ALL_CATEGORIES.get(change_type)
    return bool(category and category.ships_to_changelog)
