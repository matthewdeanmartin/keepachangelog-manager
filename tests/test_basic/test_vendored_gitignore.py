"""Tests for the stdlib ``.gitignore`` matcher vendored in place of ``pathspec``.

These cover the subset of the gitignore spec the version-bump walk relies on.
The matcher is a safety net over the hard directory excludes in ``discover``,
so a miss here degrades to "scanned but still excluded", never to a wrong write.
"""

from __future__ import annotations

import pytest

from changelogmanager.vendor.jiggle_version.gitignore import (
    GitIgnore,
    _compile_pattern,
    load_gitignore,
)


def build(*lines: str) -> GitIgnore:
    compiled = [c for c in (_compile_pattern(line) for line in lines) if c]
    return GitIgnore(compiled)


@pytest.mark.parametrize(
    ("patterns", "path", "is_dir", "expected"),
    [
        # A trailing slash means "directory only"...
        ((".venv/",), ".venv", True, True),
        ((".venv/",), ".venv", False, False),
        # ...but still ignores everything beneath it.
        ((".venv/",), ".venv/lib/x.py", False, True),
        # A pattern with no slash matches at any depth.
        (("build",), "build", True, True),
        (("build",), "sub/build/x.py", False, True),
        # A leading slash anchors to the ignore file's directory.
        (("/build",), "build", True, True),
        (("/build",), "sub/build", True, False),
        # "*" and "?" never cross a path separator.
        (("*.log",), "a/b/c.log", False, True),
        (("*.log",), "a/b/c.txt", False, False),
        (("doc/*.txt",), "doc/a.txt", False, True),
        (("doc/*.txt",), "doc/sub/a.txt", False, False),
        # "**" spans zero or more segments.
        (("a/**/c",), "a/c", True, True),
        (("a/**/c",), "a/b/x/c", True, True),
        # Character classes.
        (("[ab]x",), "ax", False, True),
        (("[ab]x",), "cx", False, False),
        # Later rules win, so "!" re-includes.
        (("node_modules", "!node_modules/keep"), "node_modules/keep", True, False),
        (("node_modules", "!node_modules/keep"), "node_modules/other", True, True),
    ],
)
def test_matching(patterns, path, is_dir, expected):
    assert build(*patterns).is_ignored(path, is_dir=is_dir) is expected


def test_comments_and_blank_lines_are_skipped():
    ignore = build("# a comment", "", "   ", "src")
    assert ignore.is_ignored("src", is_dir=True) is True
    assert ignore.is_ignored("a comment", is_dir=False) is False


def test_empty_relative_path_is_never_ignored():
    assert build("*").is_ignored("", is_dir=True) is False


def test_load_gitignore_reads_the_file_and_the_git_exclude(tmp_path):
    (tmp_path / ".gitignore").write_text("from_gitignore/\n", encoding="utf-8")
    exclude = tmp_path / ".git" / "info"
    exclude.mkdir(parents=True)
    (exclude / "exclude").write_text("from_exclude/\n", encoding="utf-8")

    ignore = load_gitignore(tmp_path)

    assert ignore.is_ignored("from_gitignore", is_dir=True) is True
    assert ignore.is_ignored("from_exclude", is_dir=True) is True


def test_load_gitignore_on_a_project_without_one_is_empty_not_an_error(tmp_path):
    ignore = load_gitignore(tmp_path)
    assert bool(ignore) is False
    assert ignore.is_ignored("anything", is_dir=True) is False
