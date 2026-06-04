"""Keep docs/CHANGELOG.md in sync with the repository changelog."""

from __future__ import annotations

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_CHANGELOG = REPO_ROOT / "CHANGELOG.md"
DOCS_CHANGELOG = REPO_ROOT / "docs" / "CHANGELOG.md"


def main() -> None:
    DOCS_CHANGELOG.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE_CHANGELOG, DOCS_CHANGELOG)


if __name__ == "__main__":
    main()
