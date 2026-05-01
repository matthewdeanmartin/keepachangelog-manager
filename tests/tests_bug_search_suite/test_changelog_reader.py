"""Bug-hunting tests for ChangelogReader — validation logic."""

from pathlib import Path

import pytest

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.changelog_reader import ChangelogReader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write(path: Path, content: str) -> str:
    p = path / "CHANGELOG.md"
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# read() — missing file
# ---------------------------------------------------------------------------


class TestReadMissingFile:
    def test_returns_empty_dict_when_file_absent(self, tmp_path):
        reader = ChangelogReader(file_path=str(tmp_path / "CHANGELOG.md"))
        result = reader.read()
        assert result == {}


# ---------------------------------------------------------------------------
# validate_layout — heading depth
# ---------------------------------------------------------------------------


class TestValidateHeadingDepth:
    def test_four_hash_heading_is_an_error(self, tmp_path):
        content = "#### Too deep\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        errors = reader.validate_layout()
        assert errors > 0

    def test_three_hash_heading_with_valid_type_is_ok(self, tmp_path):
        content = "# Changelog\n\n" "## [Unreleased]\n" "### Added\n" "- Something\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() == 0

    def test_valid_full_changelog_no_errors(self, tmp_path):
        content = (
            "# Changelog\n\n"
            "## [Unreleased]\n"
            "### Fixed\n"
            "- A fix\n\n"
            "## [1.0.0] - 2024-01-01\n"
            "### Added\n"
            "- Initial\n"
        )
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() == 0


# ---------------------------------------------------------------------------
# validate_layout — version heading format
# ---------------------------------------------------------------------------


class TestValidateVersionHeading:
    def test_missing_version_tag_is_error(self, tmp_path):
        content = "## No brackets here\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() > 0

    def test_invalid_semver_in_version_tag_is_error(self, tmp_path):
        content = "## [not-semver] - 2024-01-01\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() > 0

    def test_missing_date_separator_is_error(self, tmp_path):
        content = "## [1.0.0]\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() > 0

    def test_missing_date_after_separator_is_error(self, tmp_path):
        content = "## [1.0.0] - \n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() > 0

    def test_wrong_date_format_is_error(self, tmp_path):
        content = "## [1.0.0] - 01/01/2024\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() > 0

    def test_impossible_date_is_error(self, tmp_path):
        content = "## [1.0.0] - 2024-13-99\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() > 0

    def test_unreleased_heading_no_date_required(self, tmp_path):
        content = "## [Unreleased]\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() == 0

    def test_valid_version_heading(self, tmp_path):
        content = "## [2.3.4] - 2024-06-15\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() == 0


# ---------------------------------------------------------------------------
# validate_layout — change type headings
# ---------------------------------------------------------------------------


class TestValidateChangeTypeHeading:
    def test_invalid_change_type_is_error(self, tmp_path):
        content = "### Miscellaneous\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() > 0

    def test_lowercase_change_type_is_error(self, tmp_path):
        content = "### added\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() > 0

    def test_all_valid_change_types_accepted(self, tmp_path):
        valid_types = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]
        for change_type in valid_types:
            content = f"### {change_type}\n"
            p = write(tmp_path, content)
            reader = ChangelogReader(file_path=p)
            errors = reader.validate_layout()
            assert (
                errors == 0
            ), f"Expected 0 errors for '### {change_type}', got {errors}"


# ---------------------------------------------------------------------------
# validate_layout — forbidden entry content
# ---------------------------------------------------------------------------


class TestValidateEntryContent:
    def test_sublist_bullet_is_error(self, tmp_path):
        content = "- outer\n  - inner item\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() > 0

    def test_numbered_list_in_entry_is_error(self, tmp_path):
        content = "- 1. This is a numbered sub-item\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() > 0

    def test_blockquote_in_entry_is_error(self, tmp_path):
        content = "- > This is a block quote\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() > 0

    def test_heading_in_entry_is_error(self, tmp_path):
        content = "- # Heading inside entry\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() > 0

    def test_plain_entry_is_ok(self, tmp_path):
        content = "- A normal changelog entry\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() == 0

    def test_entry_with_backticks_is_ok(self, tmp_path):
        content = "- Fixed `foo()` crashing on null input\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        assert reader.validate_layout() == 0


# ---------------------------------------------------------------------------
# validate_contents — ordering rules
# ---------------------------------------------------------------------------


class TestValidateContents:
    def test_versions_out_of_order_reports_warning(self, tmp_path):
        content = (
            "# Changelog\n\n"
            "## [1.0.0] - 2024-01-01\n"
            "### Added\n"
            "- Initial\n\n"
            "## [2.0.0] - 2024-06-01\n"
            "### Added\n"
            "- Newer but listed last\n"
        )
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        # Validation should report a warning (not raise), but layout is valid
        errors = reader.validate_layout()
        assert errors == 0  # layout is fine
        changelog = __import__("keepachangelog").to_dict(p, show_unreleased=True)
        # validate_contents only reports, does not raise
        reader.validate_contents(changelog)  # should not raise

    def test_unreleased_not_first_reports_warning(self, tmp_path):
        """validate_contents prints a warning but does not raise when Unreleased is not first."""
        import keepachangelog

        content = (
            "# Changelog\n\n"
            "## [1.0.0] - 2024-01-01\n"
            "### Added\n"
            "- Item\n\n"
            "## [Unreleased]\n"
            "### Fixed\n"
            "- Fix\n"
        )
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        # Layout is technically valid (keepachangelog handles this)
        # We just want to verify validate_contents doesn't crash or raise an exception
        try:
            changelog = keepachangelog.to_dict(p, show_unreleased=True)
            reader.validate_contents(changelog)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"validate_contents raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# read() — full integration (write file then read)
# ---------------------------------------------------------------------------


class TestReadIntegration:
    def test_read_valid_changelog_returns_dict(self, tmp_path):
        content = (
            "# Changelog\n\n"
            "## [Unreleased]\n"
            "### Added\n"
            "- Coming soon\n\n"
            "## [1.0.0] - 2024-01-01\n"
            "### Added\n"
            "- Initial release\n"
        )
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        result = reader.read()
        assert "unreleased" in result
        assert "1.0.0" in result

    def test_read_invalid_layout_raises_error(self, tmp_path):
        content = "## [not-valid]\n"
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        with pytest.raises(logging.Error):
            reader.read()

    def test_read_only_released_versions(self, tmp_path):
        content = (
            "# Changelog\n\n"
            "## [2.0.0] - 2024-06-01\n"
            "### Removed\n"
            "- Old API\n\n"
            "## [1.0.0] - 2024-01-01\n"
            "### Added\n"
            "- Initial\n"
        )
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        result = reader.read()
        assert "2.0.0" in result
        assert "1.0.0" in result
        assert "unreleased" not in result

    def test_read_empty_file_raises_or_returns_empty(self, tmp_path):
        p = tmp_path / "CHANGELOG.md"
        p.write_text("", encoding="utf-8")
        reader = ChangelogReader(file_path=str(p))
        # An empty file has no layout errors, but keepachangelog may return {}
        result = reader.read()
        assert isinstance(result, dict)

    def test_read_multiple_change_types(self, tmp_path):
        content = (
            "# Changelog\n\n"
            "## [1.0.0] - 2024-01-01\n"
            "### Added\n"
            "- Feature A\n"
            "### Fixed\n"
            "- Bug B\n"
            "### Security\n"
            "- Vuln C\n"
        )
        p = write(tmp_path, content)
        reader = ChangelogReader(file_path=p)
        result = reader.read()
        entry = result["1.0.0"]
        assert "added" in entry
        assert "fixed" in entry
        assert "security" in entry
