from collections import OrderedDict

import pytest

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import UNRELEASED_ENTRY
from changelogmanager.changelog_reader import ChangelogReader


def test_read_returns_empty_mapping_when_file_is_missing(tmp_path):
    reader = ChangelogReader(file_path=str(tmp_path / "missing.md"))

    assert reader.read() == {}


def test_read_raises_when_layout_validation_fails(tmp_path, monkeypatch):
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog_file.write_text("# placeholder\n", encoding="utf-8")
    reader = ChangelogReader(file_path=str(changelog_file))

    monkeypatch.setattr(reader, "validate_layout", lambda: 2)

    with pytest.raises(logging.Error, match="2 errors detected in the layout"):
        reader.read()


def test_read_returns_parsed_changelog_after_validation(tmp_path, monkeypatch):
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog_file.write_text("# placeholder\n", encoding="utf-8")
    reader = ChangelogReader(file_path=str(changelog_file))
    parsed = OrderedDict(
        [
            (
                UNRELEASED_ENTRY,
                {"metadata": {"version": UNRELEASED_ENTRY, "release_date": None}},
            )
        ]
    )
    seen = {}

    monkeypatch.setattr(reader, "validate_layout", lambda: 0)
    monkeypatch.setattr(
        "changelogmanager.changelog_reader.keepachangelog.to_dict",
        lambda path, show_unreleased: parsed,
    )
    monkeypatch.setattr(
        reader,
        "validate_contents",
        lambda changelog: seen.setdefault("value", changelog),
    )

    assert reader.read() == parsed
    assert seen["value"] is parsed


def test_validate_layout_reports_heading_and_entry_errors(tmp_path, monkeypatch):
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog_file.write_text(
        "#### Too Deep\n"
        "## 1.0.0 - 2024-01-01\n"
        "### Unexpected\n"
        "* 1. nested list\n",
        encoding="utf-8",
    )
    reader = ChangelogReader(file_path=str(changelog_file))
    messages = []

    monkeypatch.setattr(
        logging.Error, "report", lambda self: messages.append(self.message)
    )

    error_count = reader.validate_layout()

    assert error_count == 4
    assert "Heading depth is too high, MUST be less or equal to 3" in messages
    assert "Missing version tag" in messages
    assert "Incompatible change type provided, MUST be one of:" in messages[2]
    assert "Numbered lists are not permitted in changelog entries" in messages


def test_validate_contents_reports_ordering_warnings(monkeypatch):
    reader = ChangelogReader(file_path="CHANGELOG.md")
    warnings = []

    monkeypatch.setattr(
        logging.Warning, "report", lambda self: warnings.append(self.message)
    )

    reader.validate_contents(
        OrderedDict(
            [
                ("1.0.0", {}),
                (UNRELEASED_ENTRY, {}),
                ("1.1.0", {}),
            ]
        )
    )

    assert "Unreleased version should be on top of the CHANGELOG.md file" in warnings
    assert "Versions are incorrectly ordered: 1.0.0 -> 1.1.0" in warnings
