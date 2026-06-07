from __future__ import annotations

from pathlib import Path

from changelogmanager import cli

CHANGELOG = """\
# Changelog

## [Unreleased]
"""


def test_normal_add_still_updates_changelog_directly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("CHANGELOG.md").write_text(CHANGELOG, encoding="UTF-8")

    result = cli.main(["add", "-t", "added", "-m", "Keep direct add simple"])

    assert result == 0
    text = Path("CHANGELOG.md").read_text(encoding="UTF-8")
    assert "Keep direct add simple" in text
    assert not Path("changelog.d").exists()


def test_add_fragment_writes_fragment_without_changelog(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = cli.main(
        ["add", "-t", "fixed", "-m", "Preserve links", "--fragment", "issue-123"]
    )

    assert result == 0
    assert not Path("CHANGELOG.md").exists()
    fragment = Path("changelog.d/issue-123.fixed.md")
    assert fragment.read_text(encoding="UTF-8") == "Preserve links\n"


def test_tasks_promote_moves_checked_items_to_unreleased(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("CHANGELOG.md").write_text(CHANGELOG, encoding="UTF-8")
    Path("TASKS.md").write_text(
        """\
# Tasks

## Fixed

- [x] Preserve links during task promotion. <!-- done: 2026-06-06 -->
- [ ] Leave unfinished work alone.
""",
        encoding="UTF-8",
    )

    result = cli.main(["tasks", "promote", "--tasks-file", "TASKS.md"])

    assert result == 0
    changelog = Path("CHANGELOG.md").read_text(encoding="UTF-8")
    tasks = Path("TASKS.md").read_text(encoding="UTF-8")
    assert "Preserve links during task promotion." in changelog
    assert "Preserve links during task promotion." not in tasks
    assert "Leave unfinished work alone." in tasks


def test_fragments_collect_keeps_old_add_behavior_opt_in(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("CHANGELOG.md").write_text(CHANGELOG, encoding="UTF-8")
    fragment_dir = Path("changelog.d")
    fragment_dir.mkdir()
    (fragment_dir / "task-files.added.md").write_text(
        "Support TASKS.md as a changelog source.\n", encoding="UTF-8"
    )

    result = cli.main(["fragments", "collect", "--consume", "keep"])

    assert result == 0
    changelog = Path("CHANGELOG.md").read_text(encoding="UTF-8")
    assert "Support TASKS.md as a changelog source." in changelog
    assert (fragment_dir / "task-files.added.md").is_file()

