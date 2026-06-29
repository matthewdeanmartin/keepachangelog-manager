# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Regex backend shim.

Prefers Google's :mod:`re2` (linear-time, no catastrophic backtracking) when it
is installed, and transparently falls back to the standard library :mod:`re`
otherwise. ``google-re2`` ships native wheels that are not yet available for
every interpreter (e.g. brand-new CPython releases), so it is an *optional*
dependency; importing this module always works.

The subset of the API used by this project -- ``compile`` and ``sub`` -- has the
same signature in both backends, and every pattern in the codebase is written to
be accepted by both engines, so the swap is invisible to callers.

Use :data:`USING_RE2` if you need to know which backend is active.
"""

import re as _stdlib_re

try:
    import re2 as _backend  # type: ignore[import-untyped]

    USING_RE2 = True
except ImportError:  # pragma: no cover - exercised on interpreters lacking re2 wheels
    _backend = _stdlib_re
    USING_RE2 = False

compile = _backend.compile  # noqa: A001 - mirror the stdlib/re2 module attribute name
sub = _backend.sub

__all__ = ["USING_RE2", "compile", "sub"]
