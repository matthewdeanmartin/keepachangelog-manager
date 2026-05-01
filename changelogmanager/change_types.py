# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Categories of changes"""

from dataclasses import dataclass
from enum import Enum

from typing import Dict, List

UNRELEASED_ENTRY: str = "unreleased"
DEFAULT_CHANGELOG_FILE: str = "CHANGELOG.md"


class VersionCore(Enum):
    """SemVer Version Cores"""

    MAJOR = 3
    MINOR = 2
    PATCH = 1


@dataclass
class Category:
    """Category for a change"""

    emoji: str
    title: str
    bump: VersionCore


CATEGORIES: Dict[str, Category] = {
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

TYPES_OF_CHANGE: List[str] = list(CATEGORIES.keys())
