# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Property-based tests for the friendliness of layout-validation messages.

These complement the example-based tests in
``tests/test_basic/test_changelog_reader_messages.py`` by asserting invariants
that must hold across the whole input space:

* validation never crashes on arbitrary heading/entry text;
* every reported error carries a non-empty, actionable ``expectations`` hint;
* a "Did you mean '### X'?" suggestion always names a *real* change type;
* a typo/mis-cased change type at level 2 is reported as a heading-level
  problem, never as the confusing "Missing version tag".
"""

from pathlib import Path

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import TYPES_OF_CHANGE
from changelogmanager.changelog_reader import ChangelogReader

# Tests write their own files into the function-scoped tmp_path fixture.
suppress = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])

ACCEPTED_TITLES = [ct.title() for ct in TYPES_OF_CHANGE]

# Text for a heading: letters/digits/spaces, no newlines, no '[' so it never
# accidentally looks like a valid version tag.
heading_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip() != "")


def capture_output(tmp_path, monkeypatch, text):
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog_file.write_text(text, encoding="utf-8")
    reader = ChangelogReader(file_path=str(changelog_file))

    reported: list = []
    monkeypatch.setattr(
        logging.Error,
        "report",
        lambda self, _sink=reported: _sink.append(self),
    )
    count = reader.validate_layout()
    return reported, count


# ---------------------------------------------------------------------------
# Robustness: arbitrary content must never crash the validator.
# ---------------------------------------------------------------------------


class TestValidatorRobustness:
    @suppress
    @given(text=st.text(max_size=200))
    def test_arbitrary_single_line_never_crashes(self, tmp_path, monkeypatch, text):
        # Strip newlines so this is genuinely one logical line.
        line = text.replace("\n", " ").replace("\r", " ")
        reported, count = capture_output(tmp_path, monkeypatch, line + "\n")
        assert count == len(reported)
        assert count >= 0

    @suppress
    @given(
        depth=st.integers(min_value=1, max_value=6),
        content=heading_text,
    )
    def test_arbitrary_heading_never_crashes(
        self, tmp_path, monkeypatch, depth, content
    ):
        line = ("#" * depth) + " " + content + "\n"
        reported, count = capture_output(tmp_path, monkeypatch, line)
        assert count == len(reported)


# ---------------------------------------------------------------------------
# Every reported error is actionable.
# ---------------------------------------------------------------------------


class TestEveryErrorIsActionable:
    @suppress
    @given(depth=st.integers(min_value=4, max_value=6), content=heading_text)
    def test_too_deep_heading_always_has_expectation(
        self, tmp_path, monkeypatch, depth, content
    ):
        line = ("#" * depth) + " " + content + "\n"
        reported, count = capture_output(tmp_path, monkeypatch, line)
        assert count == 1
        assert reported[0].expectations

    @suppress
    @given(content=heading_text)
    def test_level_3_unknown_heading_always_has_expectation(
        self, tmp_path, monkeypatch, content
    ):
        assume(content.strip() not in ACCEPTED_TITLES)
        line = "### " + content + "\n"
        reported, count = capture_output(tmp_path, monkeypatch, line)
        # Either it's flagged (with a hint) or it happened to be valid.
        for err in reported:
            assert err.expectations


# ---------------------------------------------------------------------------
# "Did you mean ...?" always names a real change type.
# ---------------------------------------------------------------------------


class TestDidYouMeanSuggestions:
    @suppress
    @given(change_type=st.sampled_from(TYPES_OF_CHANGE))
    def test_uppercased_change_type_suggests_exact_canonical(
        self, tmp_path, monkeypatch, change_type
    ):
        line = "### " + change_type.upper() + "\n"
        reported, count = capture_output(tmp_path, monkeypatch, line)
        assert count == 1
        assert reported[0].expectations == f"Did you mean '### {change_type.title()}'?"

    @suppress
    @given(content=heading_text)
    def test_did_you_mean_only_ever_names_valid_types(
        self, tmp_path, monkeypatch, content
    ):
        assume(content.strip() not in ACCEPTED_TITLES)
        line = "### " + content + "\n"
        reported, _ = capture_output(tmp_path, monkeypatch, line)
        for err in reported:
            exp = err.expectations or ""
            if exp.startswith("Did you mean '### "):
                suggested = exp[len("Did you mean '### ") : -len("'?")]
                assert suggested in ACCEPTED_TITLES


# ---------------------------------------------------------------------------
# The core bug: a change type written at level 2 is never "Missing version tag".
# ---------------------------------------------------------------------------


class TestChangeSectionAtLevel2:
    @suppress
    @given(change_type=st.sampled_from(TYPES_OF_CHANGE))
    def test_canonical_change_type_at_level_2_is_heading_level_error(
        self, tmp_path, monkeypatch, change_type
    ):
        title = change_type.title()
        line = "## " + title + "\n"
        reported, count = capture_output(tmp_path, monkeypatch, line)
        assert count == 1
        assert "Missing version tag" not in reported[0].message
        assert reported[0].expectations == f"Use '### {title}' instead of '## {title}'"

    @suppress
    @given(change_type=st.sampled_from(TYPES_OF_CHANGE))
    def test_uppercased_change_type_at_level_2_still_caught(
        self, tmp_path, monkeypatch, change_type
    ):
        line = "## " + change_type.upper() + "\n"
        reported, count = capture_output(tmp_path, monkeypatch, line)
        assert count == 1
        assert "Missing version tag" not in reported[0].message
        assert "heading level 2" in reported[0].message


# ---------------------------------------------------------------------------
# Valid version headings stay clean across the whole semver space.
# ---------------------------------------------------------------------------


class TestValidHeadingsStayClean:
    @suppress
    @given(
        major=st.integers(min_value=0, max_value=99),
        minor=st.integers(min_value=0, max_value=99),
        patch=st.integers(min_value=0, max_value=99),
        year=st.integers(min_value=1970, max_value=2999),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
    )
    def test_well_formed_version_heading_has_no_errors(
        self, tmp_path, monkeypatch, major, minor, patch, year, month, day
    ):
        line = f"## [{major}.{minor}.{patch}] - {year:04d}-{month:02d}-{day:02d}\n"
        reported, count = capture_output(tmp_path, monkeypatch, line)
        assert count == 0
        assert reported == []

    @suppress
    @given(change_type=st.sampled_from(TYPES_OF_CHANGE))
    def test_canonical_change_section_at_level_3_is_clean(
        self, tmp_path, monkeypatch, change_type
    ):
        line = "### " + change_type.title() + "\n"
        reported, count = capture_output(tmp_path, monkeypatch, line)
        assert count == 0
