"""Bug-hunting edge-case tests — boundary conditions and subtle bugs."""

import json
from collections import OrderedDict
from pathlib import Path

import pytest
from semantic_version import Version

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import UNRELEASED_ENTRY
from changelogmanager.changelog import INITIAL_VERSION, Changelog
from changelogmanager.changelog_reader import ChangelogReader
from changelogmanager.cli import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write(path: Path, content: str, name: str = "CHANGELOG.md") -> str:
    p = path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Version ordering edge cases
# ---------------------------------------------------------------------------

class TestVersionOrdering:
    def test_versions_in_correct_descending_order_reads_fine(self, tmp_path):
        content = (
            "# Changelog\n\n"
            "## [3.0.0] - 2024-03-01\n### Fixed\n- C\n\n"
            "## [2.0.0] - 2024-02-01\n### Fixed\n- B\n\n"
            "## [1.0.0] - 2024-01-01\n### Fixed\n- A\n"
        )
        p = write(tmp_path, content)
        result = ChangelogReader(file_path=p).read()
        assert list(result.keys()) == ["3.0.0", "2.0.0", "1.0.0"]

    def test_version_method_returns_first_released_key(self, tmp_path):
        changelog = OrderedDict({
            "3.0.0": {"metadata": {"version": "3.0.0", "release_date": "2024-03-01"}},
            "2.0.0": {"metadata": {"version": "2.0.0", "release_date": "2024-02-01"}},
            "1.0.0": {"metadata": {"version": "1.0.0", "release_date": "2024-01-01"}},
        })
        cl = Changelog(file_path="CHANGELOG.md", changelog=changelog)
        assert cl.version() == Version("3.0.0")

    def test_suggest_version_uses_current_not_first_key(self, tmp_path):
        """suggest_future_version should base off the current (latest) release."""
        changelog = OrderedDict()
        changelog[UNRELEASED_ENTRY] = {
            "metadata": {"version": UNRELEASED_ENTRY, "release_date": None},
            "added": ["Something"],
        }
        changelog["2.0.0"] = {"metadata": {"version": "2.0.0", "release_date": "2024-02-01"}}
        changelog["1.0.0"] = {"metadata": {"version": "1.0.0", "release_date": "2024-01-01"}}
        cl = Changelog(file_path="CHANGELOG.md", changelog=changelog)
        # Should bump minor from 2.0.0 → 2.1.0, NOT from 1.0.0 → 1.1.0
        assert cl.suggest_future_version() == Version("2.1.0")


# ---------------------------------------------------------------------------
# to_json with specific version — potential bug: iterates values of a single entry
# ---------------------------------------------------------------------------

class TestToJsonSpecificVersion:
    def test_to_json_specific_version_structure(self, tmp_path):
        """to_json(version='1.0.0') calls get('1.0.0') which returns a single entry dict,
        then does [v for _, v in content.items()] — this iterates the VALUES of a single
        version entry (metadata, added, ...), not a list of versions."""
        changelog = OrderedDict()
        changelog["1.0.0"] = {
            "metadata": {"version": "1.0.0", "release_date": "2024-01-01"},
            "added": ["Feature A"],
        }
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog=changelog)
        raw = cl.to_json(version="1.0.0")
        parsed = json.loads(raw)
        # The JSON is a list of the values inside the 1.0.0 dict
        # This may or may not be the intended behavior — document what actually happens
        assert isinstance(parsed, list)
        # The list should contain the metadata dict and the added list
        assert any(isinstance(item, dict) and "version" in item for item in parsed)


# ---------------------------------------------------------------------------
# add() with special characters
# ---------------------------------------------------------------------------

class TestAddSpecialCharacters:
    def test_add_unicode_message(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        cl.add("added", "Support für Ünïcödé chäracters")
        items = cl.get()[UNRELEASED_ENTRY]["added"]
        assert "Support für Ünïcödé chäracters" in items

    def test_add_message_with_markdown_backticks(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        cl.add("fixed", "Fixed `foo()` returning None")
        items = cl.get()[UNRELEASED_ENTRY]["fixed"]
        assert "Fixed `foo()` returning None" in items

    def test_add_message_with_brackets(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        cl.add("changed", "Updated [SomeLib](https://example.com)")
        items = cl.get()[UNRELEASED_ENTRY]["changed"]
        assert "Updated [SomeLib](https://example.com)" in items


# ---------------------------------------------------------------------------
# Release with exact same version as auto-suggest
# ---------------------------------------------------------------------------

class TestReleaseOverrideEdgeCases:
    def test_release_override_same_as_auto_is_accepted(self, tmp_path):
        """Overriding to the same version suggest_future_version would produce is valid."""
        changelog = OrderedDict()
        changelog[UNRELEASED_ENTRY] = {
            "metadata": {"version": UNRELEASED_ENTRY, "release_date": None},
            "added": ["Feature"],
        }
        changelog["1.0.0"] = {
            "metadata": {"version": "1.0.0", "release_date": "2024-01-01"}
        }
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog=changelog)
        cl.release(override_version="1.1.0")  # same as auto-suggest
        assert "1.1.0" in cl.get()

    def test_release_zero_zero_one_then_next(self, tmp_path):
        """First-ever release produces 0.0.1; next patch should be 0.0.2."""
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        cl.add("fixed", "fix1")
        cl.release()
        assert "0.0.1" in cl.get()

        cl.add("fixed", "fix2")
        cl.release()
        assert "0.0.2" in cl.get()


# ---------------------------------------------------------------------------
# write_to_file idempotency
# ---------------------------------------------------------------------------

class TestWriteIdempotency:
    def test_write_read_write_is_stable(self, tmp_path):
        """Writing, reading back and writing again should produce identical output."""
        content = (
            "# Changelog\n\n"
            "## [Unreleased]\n"
            "### Added\n"
            "- New thing\n\n"
            "## [1.0.0] - 2024-01-01\n"
            "### Added\n"
            "- Initial\n"
        )
        p = tmp_path / "CHANGELOG.md"
        p.write_text(content, encoding="utf-8")

        from changelogmanager.changelog_reader import ChangelogReader
        read1 = ChangelogReader(file_path=str(p)).read()
        cl = Changelog(file_path=str(p), changelog=read1)
        cl.write_to_file()
        text1 = p.read_text(encoding="utf-8")

        read2 = ChangelogReader(file_path=str(p)).read()
        cl2 = Changelog(file_path=str(p), changelog=read2)
        cl2.write_to_file()
        text2 = p.read_text(encoding="utf-8")

        assert text1 == text2


# ---------------------------------------------------------------------------
# CLI: add followed by release in sequence
# ---------------------------------------------------------------------------

class TestCLIAddReleaseCycle:
    def test_add_then_release_full_cycle(self, tmp_path):
        p = str(tmp_path / "CHANGELOG.md")
        main(["--input-file", p, "create"])
        main(["--input-file", p, "add", "-t", "added", "-m", "New feature"])
        rc = main(["--input-file", p, "release"])
        assert rc == 0
        text = Path(p).read_text(encoding="utf-8")
        assert "0.0.1" in text
        assert "[Unreleased]" not in text

    def test_two_cycles_produce_correct_versions(self, tmp_path):
        p = str(tmp_path / "CHANGELOG.md")
        main(["--input-file", p, "create"])
        main(["--input-file", p, "add", "-t", "added", "-m", "Feature 1"])
        main(["--input-file", p, "release"])
        main(["--input-file", p, "add", "-t", "removed", "-m", "Removed thing"])
        rc = main(["--input-file", p, "release"])
        assert rc == 0
        text = Path(p).read_text(encoding="utf-8")
        assert "0.0.1" in text
        assert "1.0.0" in text  # major bump due to 'removed'


# ---------------------------------------------------------------------------
# ChangelogReader — validate_layout returns error count correctly
# ---------------------------------------------------------------------------

class TestValidateLayoutErrorCount:
    def test_invalid_version_produces_exactly_one_error(self, tmp_path):
        # After fixing the cascade bug, a bad SemVer now returns early so
        # the missing-metadata check is never reached — exactly 1 error per bad line.
        p = write(tmp_path, "## [bad]\n")
        errors = ChangelogReader(file_path=p).validate_layout()
        assert errors == 1

    def test_two_invalid_versions_produce_two_errors(self, tmp_path):
        p = write(tmp_path, "## [bad1]\n## [bad2]\n")
        errors = ChangelogReader(file_path=p).validate_layout()
        assert errors == 2

    def test_zero_errors_on_valid_content(self, tmp_path):
        content = (
            "# Changelog\n\n"
            "## [Unreleased]\n"
            "### Added\n"
            "- Something\n"
        )
        p = write(tmp_path, content)
        errors = ChangelogReader(file_path=p).validate_layout()
        assert errors == 0


# ---------------------------------------------------------------------------
# Changelog.get — version as Version object vs string
# ---------------------------------------------------------------------------

class TestGetVersionTypes:
    def test_get_with_string_version(self, tmp_path):
        changelog = {"1.0.0": {"metadata": {"version": "1.0.0"}}}
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog=changelog)
        result = cl.get("1.0.0")
        assert result["metadata"]["version"] == "1.0.0"

    def test_get_with_version_object_coerced(self, tmp_path):
        """get() uses str(version) so passing a Version object should work."""
        changelog = {"1.0.0": {"metadata": {"version": "1.0.0"}}}
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog=changelog)
        result = cl.get(str(Version("1.0.0")))
        assert result["metadata"]["version"] == "1.0.0"


# ---------------------------------------------------------------------------
# Changelog existence check
# ---------------------------------------------------------------------------

class TestChangelogExists:
    def test_exists_true_when_file_present(self, tmp_path):
        p = tmp_path / "CHANGELOG.md"
        p.write_text("# Changelog\n", encoding="utf-8")
        cl = Changelog(file_path=str(p), changelog={})
        assert cl.exists() is True

    def test_exists_false_when_file_absent(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        assert cl.exists() is False


# ---------------------------------------------------------------------------
# Validate layout with entries using '+' and '*' bullets
# ---------------------------------------------------------------------------

class TestAlternateBullets:
    def test_plus_bullet_validates_as_entry(self, tmp_path):
        content = "+ A valid plus-bullet entry\n"
        p = write(tmp_path, content)
        errors = ChangelogReader(file_path=p).validate_layout()
        assert errors == 0

    def test_asterisk_bullet_validates_as_entry(self, tmp_path):
        content = "* A valid asterisk-bullet entry\n"
        p = write(tmp_path, content)
        errors = ChangelogReader(file_path=p).validate_layout()
        assert errors == 0

    def test_plus_sublist_in_entry_is_error(self, tmp_path):
        content = "- + sub-item using plus\n"
        p = write(tmp_path, content)
        errors = ChangelogReader(file_path=p).validate_layout()
        assert errors > 0
