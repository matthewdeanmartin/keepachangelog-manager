# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Example-based tests for the *friendliness* of layout-validation messages.

Each of the six message improvements gets at least two tests: one proving the
new, helpful message/expectation appears, and one guarding against a regression
(the wrong or old message must NOT appear, or a valid input stays clean).

Property-based coverage lives in
``tests/test_hypothesis/test_validation_message_properties.py``.
"""

import pytest

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import TYPES_OF_CHANGE
from changelogmanager.changelog_reader import ChangelogReader


def capture_output(tmp_path, monkeypatch, text):
    """Write ``text`` to a CHANGELOG, run layout validation, return the errors.

    Returns a list of ``(message, expectations)`` tuples in report order plus
    the integer error count from ``validate_layout``.
    """

    changelog_file = tmp_path / "CHANGELOG.md"
    changelog_file.write_text(text, encoding="utf-8")
    reader = ChangelogReader(file_path=str(changelog_file))

    reported: list[tuple] = []
    monkeypatch.setattr(
        logging.Error,
        "report",
        lambda self: reported.append((self.message, self.expectations)),
    )

    count = reader.validate_layout()
    return reported, count


def get_messages(reported):
    return [msg for msg, _ in reported]


def get_expectations(reported):
    return [exp for _, exp in reported]


# ---------------------------------------------------------------------------
# Improvement 1: "## Changed" (change section at level 2 instead of 3)
# ---------------------------------------------------------------------------


def test_change_section_at_level_2_reports_heading_level(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "## Changed\n- a change\n")

    assert count == 1
    assert "change section but is at heading level 2" in get_messages(reported)[0]
    assert get_expectations(reported)[0] == "Use '### Changed' instead of '## Changed'"


def test_change_section_at_level_2_does_not_say_missing_version_tag(
    tmp_path, monkeypatch
):
    # This is the exact bug we fixed: "## Added" must not be reported as a
    # malformed version heading.
    reported, _ = capture_output(tmp_path, monkeypatch, "## Added\n- a feature\n")

    assert all("Missing version tag" not in msg for msg in get_messages(reported))
    assert get_expectations(reported)[0] == "Use '### Added' instead of '## Added'"


# ---------------------------------------------------------------------------
# Improvement 2: misspelled / mis-cased change type -> "Did you mean ...?"
# ---------------------------------------------------------------------------


def test_misspelled_change_type_at_level_3_suggests_correction(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "### Chnaged\n- a change\n")

    assert count == 1
    assert get_expectations(reported)[0] == "Did you mean '### Changed'?"


def test_miscased_change_type_at_level_3_suggests_canonical(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "### ADDED\n- a feature\n")

    assert count == 1
    assert get_expectations(reported)[0] == "Did you mean '### Added'?"


def test_unrecognizable_change_type_lists_valid_options(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "### Bananas\n- nope\n")

    assert count == 1
    expectation = get_expectations(reported)[0]
    assert expectation.startswith("Use one of: ")
    for change_type in TYPES_OF_CHANGE:
        assert change_type.title() in expectation


# ---------------------------------------------------------------------------
# Improvement 3: genuinely missing version tag still reported (with a hint)
# ---------------------------------------------------------------------------


def test_genuinely_missing_version_tag_keeps_message(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "## 1.0.0 - 2024-01-01\n")

    assert count == 1
    assert get_messages(reported)[0] == "Missing version tag"


def test_missing_version_tag_includes_format_hint(tmp_path, monkeypatch):
    reported, _ = capture_output(tmp_path, monkeypatch, "## 1.0.0 - 2024-01-01\n")

    assert (
        get_expectations(reported)[0]
        == "Use the form '## [1.2.3] - 2022-12-31' or '## [Unreleased]'"
    )


# ---------------------------------------------------------------------------
# Improvement 4: invalid SemVer version -> semver.org hint
# ---------------------------------------------------------------------------


def test_invalid_semver_includes_semver_hint(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "## [1.2] - 2024-01-01\n")

    assert count == 1
    assert "MUST be SemVer compliant" in get_messages(reported)[0]
    assert get_expectations(reported)[0] == (
        "Use MAJOR.MINOR.PATCH, e.g. '1.2.3' (see https://semver.org)"
    )


def test_valid_semver_version_heading_is_clean(tmp_path, monkeypatch):
    reported, count = capture_output(
        tmp_path, monkeypatch, "## [1.2.3] - 2024-01-01\n### Added\n- thing\n"
    )

    assert count == 0
    assert reported == []


# ---------------------------------------------------------------------------
# Improvement 5: missing metadata ('-') and bad release date hints
# ---------------------------------------------------------------------------


def test_missing_metadata_dash_suggests_release_date(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "## [1.2.3]\n")

    assert count == 1
    assert "Missing metadata" in get_messages(reported)[0]
    assert get_expectations(reported)[0] == (
        "Add a release date, e.g. '## [1.2.3] - 2022-12-31'"
    )


def test_non_date_metadata_suggests_iso_date(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "## [1.2.3] - someday\n")

    assert count == 1
    assert "Incompatible release date" in get_messages(reported)[0]
    assert (
        get_expectations(reported)[0]
        == "Use an ISO date, e.g. '## [1.2.3] - 2022-12-31'"
    )


def test_impossible_calendar_date_explains_why(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "## [1.2.3] - 2024-13-40\n")

    assert count == 1
    assert "Incompatible release date" in get_messages(reported)[0]
    expectation = get_expectations(reported)[0]
    assert "2024-13-40" in expectation
    assert "not a real calendar date" in expectation


# ---------------------------------------------------------------------------
# Improvement 6: heading-too-deep + entry-format hints
# ---------------------------------------------------------------------------


def test_heading_too_deep_explains_allowed_levels(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "#### Too Deep\n")

    assert count == 1
    assert "Heading depth is too high" in get_messages(reported)[0]
    expectation = get_expectations(reported)[0]
    assert "### Change type" in expectation


def test_numbered_list_entry_suggests_bullet(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "- 1. nested numbered\n")

    assert count == 1
    assert "Numbered lists are not permitted" in get_messages(reported)[0]
    assert get_expectations(reported)[0] == (
        "Use a '- ' bullet instead of a numbered '1.' list"
    )


def test_indented_sublist_entry_is_valid(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "  - indented entry\n")

    assert count == 0
    assert reported == []


def test_doubled_marker_entry_suggests_single_marker(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "- - doubled marker\n")

    assert count == 1
    assert "Doubled list markers are not permitted" in get_messages(reported)[0]
    assert "single '- ' marker" in get_expectations(reported)[0]


def test_block_quote_entry_suggests_plain_text(tmp_path, monkeypatch):
    reported, count = capture_output(tmp_path, monkeypatch, "- > quoted entry\n")

    assert count == 1
    assert "Block quotes are not permitted" in get_messages(reported)[0]
    assert "block-quote" in get_expectations(reported)[0]


# ---------------------------------------------------------------------------
# Cross-cutting: every reported Error carries an actionable expectation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "## Changed\n- x\n",
        "### Chnaged\n- x\n",
        "## 1.0.0 - 2024-01-01\n",
        "## [1.2] - 2024-01-01\n",
        "## [1.2.3]\n",
        "## [1.2.3] - someday\n",
        "## [1.2.3] - 2024-13-40\n",
        "#### Too Deep\n",
        "- 1. numbered\n",
    ],
)
def test_every_layout_error_has_an_expectation(tmp_path, monkeypatch, text):
    reported, count = capture_output(tmp_path, monkeypatch, text)

    assert count >= 1
    for _, expectation in reported:
        assert expectation, f"missing expectation for input {text!r}"
