# SPDX-License-Identifier: MIT

"""Slim vendored subset of jiggle-version.

Only the three symbols ``changelogmanager.version_bumper`` needs are vendored:

* :func:`find_source_files` -- locate ``.py`` files that may carry ``__version__``
* :func:`update_pyproject_toml` -- rewrite ``[project].version``
* :func:`update_python_file` -- rewrite ``__version__ = "..."`` assignments

This copy is reimplemented to depend only on the standard library: upstream's
``find_source_files`` used ``pathspec`` for .gitignore matching and
``update_pyproject_toml`` used ``tomlkit`` for formatting-preserving writes.
Neither third-party dependency is vendored or required here; see ``UPSTREAM.md``
for exactly what was cut and why.

Upstream project: https://github.com/matthewdeanmartin/jiggle_version (MIT,
copied from version 2.1.1).
"""

from __future__ import annotations

from changelogmanager.vendor.jiggle_version.discover import find_source_files
from changelogmanager.vendor.jiggle_version.update import (
    update_pyproject_toml,
    update_python_file,
)

__all__ = [
    "find_source_files",
    "update_pyproject_toml",
    "update_python_file",
]
