# SPDX-License-Identifier: MIT
# Vendored replacement for jiggle_version/gitignore.py (jiggle-version 2.1.1).
"""Minimal, stdlib-only ``.gitignore`` matching.

Upstream used ``pathspec.GitWildMatchPattern``. That third-party dependency is
not vendored, so this module implements the subset of the gitignore spec that
matters for deciding whether to descend into a directory during a version-bump
scan: comments, blank lines, ``!`` negation, leading/trailing ``/`` anchoring,
``**`` segments, and ``fnmatch``-style ``*``/``?``/``[]`` within a segment.

Deliberately not supported: backslash escaping of ``#``/``!``/spaces. Those are
vanishingly rare in real ignore files, and the failure mode of missing one is a
file that gets scanned rather than skipped -- which is only ever caught by the
hard directory excludes in :mod:`~changelogmanager.vendor.jiggle_version.discover`
anyway.

The matcher is used as a *safety net*, never as the only guard: the caller
applies :data:`~changelogmanager.vendor.jiggle_version.discover.DEFAULT_IGNORE_DIRS`
regardless of whether a ``.gitignore`` exists.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

__all__ = ["GitIgnore", "load_gitignore"]


def _translate_segment(segment: str) -> str:
    """Translate one path segment glob into a regex fragment.

    Unlike :func:`fnmatch.translate`, ``*`` and ``?`` never match ``/``.
    """
    out: list[str] = []
    index = 0
    length = len(segment)
    while index < length:
        char = segment[index]
        index += 1
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            # Copy the character class through to its closing bracket.
            end = index
            if end < length and segment[end] in ("!", "^"):
                end += 1
            if end < length and segment[end] == "]":
                end += 1
            while end < length and segment[end] != "]":
                end += 1
            if end >= length:
                out.append(re.escape("["))
            else:
                body = segment[index:end].replace("\\", "\\\\")
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append(f"[{body}]")
                index = end + 1
        else:
            out.append(re.escape(char))
    return "".join(out)


def _compile_pattern(pattern: str) -> tuple[re.Pattern[str], bool, bool] | None:
    """Compile one gitignore line.

    Returns ``(regex, negated, dir_only)``, or ``None`` for a line that matches
    nothing (blank, comment, or degenerate).
    """
    line = pattern.rstrip("\r\n")
    # Trailing spaces are insignificant unless escaped; escaping is unsupported.
    line = line.rstrip(" ")
    if not line or line.startswith("#"):
        return None

    negated = line.startswith("!")
    if negated:
        line = line[1:]
    if not line:
        return None

    dir_only = line.endswith("/")
    if dir_only:
        line = line.rstrip("/")
    if not line:
        return None

    # A pattern containing a non-trailing "/" is anchored to the ignore file's
    # directory; otherwise it matches at any depth.
    anchored = "/" in line
    line = line.lstrip("/")
    if not line:
        return None

    segments = line.split("/")
    parts: list[str] = []
    for position, segment in enumerate(segments):
        is_last = position == len(segments) - 1
        if segment == "**":
            # "**" matches zero or more path segments.
            parts.append("(?:[^/]+/)*" if not is_last else "[^/]+")
            continue
        parts.append(_translate_segment(segment))
        if not is_last:
            parts.append("/")

    body = "".join(parts).replace("/(?:[^/]+/)*", "(?:/[^/]+)*/")
    prefix = "" if anchored else "(?:.*/)?"
    # Match the path itself or anything beneath it -- ignoring a directory
    # ignores its whole subtree.
    regex = re.compile(f"^{prefix}{body}(?P<tail>/.*)?$")
    return regex, negated, dir_only


class GitIgnore:
    """A compiled set of gitignore rules rooted at a directory."""

    def __init__(self, rules: list[tuple[re.Pattern[str], bool, bool]]) -> None:
        self._rules = rules

    def __bool__(self) -> bool:
        return bool(self._rules)

    def is_ignored(self, relative_path: str, *, is_dir: bool) -> bool:
        """True if ``relative_path`` (POSIX, relative to the root) is ignored.

        Later rules win, matching git's own precedence.
        """
        path = relative_path.strip("/")
        if not path:
            return False

        ignored = False
        for regex, negated, dir_only in self._rules:
            match = regex.match(path)
            if not match:
                continue
            if dir_only and not is_dir and not match.group("tail"):
                # A "dir/" rule matches the directory itself only when the
                # candidate *is* a directory. It still ignores files beneath
                # it, which is the case where "tail" is non-empty.
                continue
            ignored = not negated
        return ignored


def load_gitignore(root: Path) -> GitIgnore:
    """Load ``root/.gitignore`` (plus ``.git/info/exclude``) into a matcher.

    A missing or unreadable file yields an empty matcher rather than an error;
    ignore rules are an optimization on top of the hard directory excludes.
    """
    rules: list[tuple[re.Pattern[str], bool, bool]] = []
    for candidate in (root / ".gitignore", root / ".git" / "info" / "exclude"):
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            compiled = _compile_pattern(line)
            if compiled is not None:
                rules.append(compiled)
    return GitIgnore(rules)


def relative_posix(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` as a POSIX string, or ``""``."""
    try:
        return PurePosixPath(path.relative_to(root).as_posix()).as_posix()
    except ValueError:
        return ""
