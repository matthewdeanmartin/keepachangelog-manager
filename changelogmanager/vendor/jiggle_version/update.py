# SPDX-License-Identifier: MIT
# Vendored and trimmed from jiggle_version/update.py (jiggle-version 2.1.1).
"""Update version strings in source files.

``update_python_file`` is copied verbatim (pure ``re``). ``update_pyproject_toml``
is reimplemented with a section-aware line rewrite instead of upstream's
``tomlkit`` round-trip, so the vendored copy needs no third-party dependency. The
line rewrite preserves all surrounding formatting because it only replaces the
value on the single ``version = ...`` line, leaving every other byte untouched.

``update_setup_cfg`` is intentionally not vendored: ``bump_version_files`` never
calls it.
"""

from __future__ import annotations

import re
from pathlib import Path

_PYTHON_DUNDER_VERSION_RE = re.compile(
    r"""(?m)^(\s*__version__\s*=\s*)(['"])(.*?)(\2)"""
)
_PYTHON_SETUP_VERSION_RE = re.compile(r"""(?<![\w.])(version\s*=\s*)(['"])(.*?)(\2)""")

# A TOML table header line, e.g. ``[project]`` or ``[tool.setuptools]``.
_TABLE_HEADER_RE = re.compile(r"^\s*\[\s*(?P<name>[^\]]+?)\s*\]\s*$")
# A ``version = "..."`` assignment, capturing the prefix, quote, value, and tail
# (which may include a trailing comment) so only the value is replaced.
_VERSION_ASSIGN_RE = re.compile(
    r"""^(?P<prefix>\s*version\s*=\s*)(?P<quote>['"])(?P<value>.*?)(?P=quote)(?P<tail>.*)$"""
)

# Tables whose ``version`` key carries the project version, in priority order.
_VERSION_TABLES = ("project", "tool.setuptools")


def update_pyproject_toml(file_path: Path, new_version: str) -> None:
    """Update ``version`` in a pyproject.toml, preserving file formatting.

    Rewrites the ``version`` key under ``[project]`` if present, otherwise under
    ``[tool.setuptools]`` (mirroring upstream). Only the first matching key is
    changed; if no such key exists the file is left untouched.
    """
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    current_table: str | None = None
    for table in _VERSION_TABLES:
        for index, line in enumerate(lines):
            header = _TABLE_HEADER_RE.match(line)
            if header:
                current_table = header.group("name")
                continue
            if current_table != table:
                continue
            assign = _VERSION_ASSIGN_RE.match(line.rstrip("\r\n"))
            if not assign:
                continue
            line_ending = _line_ending(line)
            lines[index] = (
                f"{assign.group('prefix')}{assign.group('quote')}{new_version}"
                f"{assign.group('quote')}{assign.group('tail')}{line_ending}"
            )
            file_path.write_text("".join(lines), encoding="utf-8")
            return
        current_table = None


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def update_python_file(file_path: Path, new_version: str) -> None:
    """Update the version in a Python file (``__version__`` or ``setup.py``)."""
    content = file_path.read_text(encoding="utf-8")

    def replacer(match: re.Match[str]) -> str:
        return f"{match.group(1)}{match.group(2)}{new_version}{match.group(2)}"

    new_content, dunder_count = _PYTHON_DUNDER_VERSION_RE.subn(replacer, content)
    new_content, setup_count = _PYTHON_SETUP_VERSION_RE.subn(replacer, new_content)

    if dunder_count > 0 or setup_count > 0:
        file_path.write_text(new_content, encoding="utf-8")
