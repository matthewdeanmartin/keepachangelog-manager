"""Fixtures for snapshot tests.

These tests run outside the normal pytest suite (use ``-m snapshot`` or
``pytest tests/test_snapshots/`` explicitly) so they do not slow down the
standard ``make test`` run.  They are wired into ``make prerelease`` via
``make snapshot-check``.

To regenerate snapshots after an intentional change::

    uv run pytest tests/test_snapshots/ --snapshot-update
"""

import io
import textwrap
from pathlib import Path
from typing import Any

import mdformat
import pytest

# ---------------------------------------------------------------------------
# Re-use the repo-level isolate_cwd so snapshot tests also run in a temp dir.
# The root conftest.py registers it as autouse=True, so it applies here
# automatically — no extra import needed.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Known-state changelog fixtures
# ---------------------------------------------------------------------------

_FULL_CHANGELOG = textwrap.dedent("""\
    # Changelog
    All notable changes to this project will be documented in this file.

    The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
    and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

    ## [Unreleased]

    ### Added
    - New widget component

    ### Fixed
    - Off-by-one error in pagination

    ## [1.2.0] - 2024-06-01

    ### Added
    - Dark mode support

    ### Changed
    - Improved startup performance

    ## [1.1.0] - 2024-03-15

    ### Added
    - Export to CSV feature

    ### Deprecated
    - Legacy XML export

    ## [1.0.0] - 2024-01-01

    ### Added
    - Initial public release

    [Unreleased]: https://github.com/example/repo/compare/v1.2.0...HEAD
    [1.2.0]: https://github.com/example/repo/compare/v1.1.0...v1.2.0
    [1.1.0]: https://github.com/example/repo/compare/v1.0.0...v1.1.0
    [1.0.0]: https://github.com/example/repo/releases/tag/v1.0.0
""")

_MINIMAL_CHANGELOG = textwrap.dedent("""\
    # Changelog
    All notable changes to this project will be documented in this file.

    The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
    and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

    ## [1.0.0] - 2024-01-01

    ### Added
    - Initial release

    [1.0.0]: https://github.com/example/repo/releases/tag/v1.0.0
""")

_NO_UNRELEASED_CHANGELOG = textwrap.dedent("""\
    # Changelog
    All notable changes to this project will be documented in this file.

    The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
    and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

    ## [2.0.0] - 2024-12-01

    ### Added
    - Major overhaul

    ## [1.0.0] - 2024-01-01

    ### Added
    - Initial release

    [2.0.0]: https://github.com/example/repo/compare/v1.0.0...v2.0.0
    [1.0.0]: https://github.com/example/repo/releases/tag/v1.0.0
""")


@pytest.fixture()
def full_changelog(tmp_path: Path) -> Path:
    """A rich changelog with [Unreleased] and several past releases."""
    p = tmp_path / "CHANGELOG.md"
    p.write_text(_FULL_CHANGELOG, encoding="utf-8")
    return p


@pytest.fixture()
def minimal_changelog(tmp_path: Path) -> Path:
    """A minimal changelog with a single release and no [Unreleased]."""
    p = tmp_path / "CHANGELOG.md"
    p.write_text(_MINIMAL_CHANGELOG, encoding="utf-8")
    return p


@pytest.fixture()
def no_unreleased_changelog(tmp_path: Path) -> Path:
    """A changelog with multiple releases but no [Unreleased] section."""
    p = tmp_path / "CHANGELOG.md"
    p.write_text(_NO_UNRELEASED_CHANGELOG, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------


@pytest.fixture()
def run_cli():
    """Call ``changelogmanager.cli.main`` and return (exit_code, stdout)."""
    import sys
    from changelogmanager.cli import main

    def _run(*argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            rc = main(list(argv))
        finally:
            sys.stdout = old_stdout
        return rc, buf.getvalue()

    return _run


# ---------------------------------------------------------------------------
# Markdown normaliser
# ---------------------------------------------------------------------------


def normalise_md(text: str) -> str:
    """Run mdformat so cosmetic whitespace differences don't cause snapshot mismatches."""
    return mdformat.text(text)


def normalise_json(text: str) -> str:
    """Stable JSON: parse then re-serialise with sorted keys."""
    import json
    return json.dumps(json.loads(text), sort_keys=True, indent=2)


def normalise_paths(text: str, root: Path) -> str:
    """Replace the absolute temp path with a stable placeholder so snapshot
    comparisons are not sensitive to per-run temp directory numbers."""
    import re

    # Replace the root directory (forward and back-slash variants) with a placeholder.
    placeholder = "<CHANGELOG_PATH>"
    normalized = text.replace(str(root), placeholder)
    # Also collapse any remaining OS-specific separators so snapshots are
    # cross-platform if someone regenerates on a different OS.
    normalized = normalized.replace("\\", "/")
    # Normalise the placeholder itself just in case.
    normalized = normalized.replace(str(root).replace("\\", "/"), placeholder)
    return normalized
