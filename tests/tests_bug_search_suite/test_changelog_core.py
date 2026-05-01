"""Bug-hunting tests for Changelog core logic."""

import json
from collections import OrderedDict
from pathlib import Path

import pytest
from semantic_version import Version

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.changelog import Changelog, INITIAL_VERSION
from changelogmanager.change_types import UNRELEASED_ENTRY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_changelog(path: Path, content: str) -> Path:
    p = path / "CHANGELOG.md"
    p.write_text(content, encoding="utf-8")
    return p


MINIMAL_RELEASED = """\
# Changelog

## [1.0.0] - 2024-01-01
### Added
- Initial release
"""

WITH_UNRELEASED = """\
# Changelog

## [Unreleased]
### Fixed
- Some fix

## [1.0.0] - 2024-01-01
### Added
- Initial release
"""

MULTI_VERSION = """\
# Changelog

## [Unreleased]
### Added
- New thing

## [2.0.0] - 2024-06-01
### Removed
- Old thing

## [1.0.0] - 2024-01-01
### Added
- Initial release
"""


# ---------------------------------------------------------------------------
# Changelog.add
# ---------------------------------------------------------------------------

class TestChangelogAdd:
    def test_add_creates_unreleased_when_absent(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        cl.add("fixed", "Bug squashed")
        data = cl.get()
        assert UNRELEASED_ENTRY in data
        assert "Bug squashed" in data[UNRELEASED_ENTRY]["fixed"]

    def test_add_appends_to_existing_list(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        cl.add("added", "First")
        cl.add("added", "Second")
        items = cl.get()[UNRELEASED_ENTRY]["added"]
        assert items == ["First", "Second"]

    def test_add_multiple_change_types(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        cl.add("added", "Feature A")
        cl.add("fixed", "Bug B")
        data = cl.get()[UNRELEASED_ENTRY]
        assert "Feature A" in data["added"]
        assert "Bug B" in data["fixed"]

    def test_add_keeps_unreleased_first(self, tmp_path):
        changelog = OrderedDict({
            "1.0.0": {"metadata": {"version": "1.0.0", "release_date": "2024-01-01"}},
        })
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog=changelog)
        cl.add("fixed", "Something")
        keys = list(cl.get().keys())
        assert keys[0] == UNRELEASED_ENTRY, "Unreleased must be first after add"

    def test_add_empty_message(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        cl.add("fixed", "")
        items = cl.get()[UNRELEASED_ENTRY]["fixed"]
        assert "" in items

    def test_add_preserves_existing_released_versions(self, tmp_path):
        changelog = OrderedDict({
            "1.0.0": {"metadata": {"version": "1.0.0", "release_date": "2024-01-01"}},
        })
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog=changelog)
        cl.add("added", "New thing")
        assert "1.0.0" in cl.get()

    def test_add_does_not_mutate_original_changelog_dict(self, tmp_path):
        original = {}
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog=original)
        cl.add("added", "Something")
        assert original == {}, "Original dict should not be mutated"


# ---------------------------------------------------------------------------
# Changelog.release
# ---------------------------------------------------------------------------

class TestChangelogRelease:
    def _make_with_unreleased(self, tmp_path, change_type="added", released_version=None):
        changelog = OrderedDict()
        changelog[UNRELEASED_ENTRY] = {
            "metadata": {"version": UNRELEASED_ENTRY, "release_date": None},
            change_type: ["Something new"],
        }
        if released_version:
            changelog[released_version] = {
                "metadata": {"version": released_version, "release_date": "2024-01-01"},
                "added": ["Previous thing"],
            }
        return Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog=changelog)

    def test_release_without_unreleased_raises(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        with pytest.raises(logging.Error):
            cl.release()

    def test_release_only_unreleased_gives_initial_version(self, tmp_path):
        cl = self._make_with_unreleased(tmp_path)
        cl.release()
        data = cl.get()
        assert str(INITIAL_VERSION) in data
        assert UNRELEASED_ENTRY not in data

    def test_release_with_override_version(self, tmp_path):
        cl = self._make_with_unreleased(tmp_path, released_version="1.0.0")
        cl.release(override_version="2.0.0")
        assert "2.0.0" in cl.get()
        assert UNRELEASED_ENTRY not in cl.get()

    def test_release_strips_v_prefix(self, tmp_path):
        cl = self._make_with_unreleased(tmp_path, released_version="1.0.0")
        cl.release(override_version="v2.0.0")
        assert "2.0.0" in cl.get()

    def test_release_rejects_already_released_version(self, tmp_path):
        cl = self._make_with_unreleased(tmp_path, released_version="1.0.0")
        with pytest.raises(logging.Error, match="already released"):
            cl.release(override_version="1.0.0")

    def test_release_rejects_older_version_than_current(self, tmp_path):
        cl = self._make_with_unreleased(tmp_path, released_version="2.0.0")
        with pytest.raises(logging.Error, match="older than the last release"):
            cl.release(override_version="1.0.0")

    def test_release_invalid_semver_raises(self, tmp_path):
        cl = self._make_with_unreleased(tmp_path, released_version="1.0.0")
        with pytest.raises(logging.Error, match="SemVer"):
            cl.release(override_version="not-a-version")

    def test_release_sets_release_date_today(self, tmp_path):
        from datetime import date
        cl = self._make_with_unreleased(tmp_path, released_version="1.0.0")
        cl.release(override_version="2.0.0")
        release_date = cl.get()["2.0.0"]["metadata"]["release_date"]
        assert release_date == date.today().strftime("%Y-%m-%d")

    def test_release_new_version_is_first_entry(self, tmp_path):
        cl = self._make_with_unreleased(tmp_path, released_version="1.0.0")
        cl.release(override_version="2.0.0")
        keys = list(cl.get().keys())
        assert keys[0] == "2.0.0"

    def test_release_auto_bump_added_gives_minor(self, tmp_path):
        cl = self._make_with_unreleased(tmp_path, change_type="added", released_version="1.0.0")
        cl.release()
        assert "1.1.0" in cl.get()

    def test_release_auto_bump_removed_gives_major(self, tmp_path):
        cl = self._make_with_unreleased(tmp_path, change_type="removed", released_version="1.0.0")
        cl.release()
        assert "2.0.0" in cl.get()

    def test_release_auto_bump_fixed_gives_patch(self, tmp_path):
        cl = self._make_with_unreleased(tmp_path, change_type="fixed", released_version="1.0.0")
        cl.release()
        assert "1.0.1" in cl.get()

    def test_release_preserves_existing_versions(self, tmp_path):
        cl = self._make_with_unreleased(tmp_path, released_version="1.0.0")
        cl.release(override_version="2.0.0")
        assert "1.0.0" in cl.get()

    def test_release_metadata_contains_semver_fields(self, tmp_path):
        cl = self._make_with_unreleased(tmp_path, released_version="1.0.0")
        cl.release(override_version="2.3.4")
        meta = cl.get()["2.3.4"]["metadata"]
        assert meta["semantic_version"]["major"] == 2
        assert meta["semantic_version"]["minor"] == 3
        assert meta["semantic_version"]["patch"] == 4

    def test_release_equal_to_current_version_is_rejected(self, tmp_path):
        """Equal version is already released — must raise."""
        cl = self._make_with_unreleased(tmp_path, released_version="1.0.0")
        with pytest.raises(logging.Error):
            cl.release(override_version="1.0.0")


# ---------------------------------------------------------------------------
# Changelog.version / previous_version
# ---------------------------------------------------------------------------

class TestChangelogVersionQueries:
    def _make(self, versions: list[str], with_unreleased=False) -> Changelog:
        changelog = OrderedDict()
        if with_unreleased:
            changelog[UNRELEASED_ENTRY] = {
                "metadata": {"version": UNRELEASED_ENTRY, "release_date": None},
            }
        for v in versions:
            changelog[v] = {"metadata": {"version": v, "release_date": "2024-01-01"}}
        return Changelog(file_path="CHANGELOG.md", changelog=changelog)

    def test_version_empty_changelog_raises(self):
        cl = Changelog(file_path="CHANGELOG.md", changelog={})
        with pytest.raises(logging.Warning):
            cl.version()

    def test_version_only_unreleased_raises(self):
        cl = self._make([], with_unreleased=True)
        with pytest.raises(logging.Warning):
            cl.version()

    def test_version_returns_latest_released(self):
        cl = self._make(["2.0.0", "1.0.0"])
        assert cl.version() == Version("2.0.0")

    def test_version_with_unreleased_skips_it(self):
        cl = self._make(["2.0.0", "1.0.0"], with_unreleased=True)
        assert cl.version() == Version("2.0.0")

    def test_previous_version_empty_raises(self):
        cl = Changelog(file_path="CHANGELOG.md", changelog={})
        with pytest.raises(logging.Warning):
            cl.previous_version()

    def test_previous_version_single_released_raises(self):
        cl = self._make(["1.0.0"])
        with pytest.raises(logging.Warning):
            cl.previous_version()

    def test_previous_version_with_only_unreleased_and_one_release_raises(self):
        cl = self._make(["1.0.0"], with_unreleased=True)
        with pytest.raises(logging.Warning):
            cl.previous_version()

    def test_previous_version_two_released(self):
        cl = self._make(["2.0.0", "1.0.0"])
        assert cl.previous_version() == Version("1.0.0")

    def test_previous_version_with_unreleased(self):
        cl = self._make(["2.0.0", "1.0.0"], with_unreleased=True)
        assert cl.previous_version() == Version("1.0.0")


# ---------------------------------------------------------------------------
# Changelog.suggest_future_version
# ---------------------------------------------------------------------------

class TestSuggestFutureVersion:
    def _make_unreleased(self, change_types: list[str], released_version=None) -> Changelog:
        changelog = OrderedDict()
        unreleased: dict = {"metadata": {"version": UNRELEASED_ENTRY, "release_date": None}}
        for ct in change_types:
            unreleased[ct] = ["An entry"]
        changelog[UNRELEASED_ENTRY] = unreleased
        if released_version:
            changelog[released_version] = {
                "metadata": {"version": released_version, "release_date": "2024-01-01"}
            }
        return Changelog(file_path="CHANGELOG.md", changelog=changelog)

    def test_only_unreleased_returns_initial_version(self):
        cl = self._make_unreleased(["added"])
        assert cl.suggest_future_version() == INITIAL_VERSION

    def test_added_bumps_minor(self):
        cl = self._make_unreleased(["added"], released_version="1.0.0")
        assert cl.suggest_future_version() == Version("1.1.0")

    def test_removed_bumps_major(self):
        cl = self._make_unreleased(["removed"], released_version="1.0.0")
        assert cl.suggest_future_version() == Version("2.0.0")

    def test_fixed_bumps_patch(self):
        cl = self._make_unreleased(["fixed"], released_version="1.0.0")
        assert cl.suggest_future_version() == Version("1.0.1")

    def test_security_bumps_minor(self):
        cl = self._make_unreleased(["security"], released_version="1.0.0")
        assert cl.suggest_future_version() == Version("1.1.0")

    def test_removed_plus_added_bumps_major(self):
        """Removed (MAJOR) wins over Added (MINOR)."""
        cl = self._make_unreleased(["added", "removed"], released_version="1.0.0")
        assert cl.suggest_future_version() == Version("2.0.0")

    def test_added_plus_fixed_bumps_minor(self):
        """Added (MINOR) wins over Fixed (PATCH)."""
        cl = self._make_unreleased(["added", "fixed"], released_version="1.0.0")
        assert cl.suggest_future_version() == Version("1.1.0")

    def test_deprecated_bumps_patch(self):
        cl = self._make_unreleased(["deprecated"], released_version="1.0.0")
        assert cl.suggest_future_version() == Version("1.0.1")

    def test_changed_bumps_patch(self):
        cl = self._make_unreleased(["changed"], released_version="1.0.0")
        assert cl.suggest_future_version() == Version("1.0.1")

    def test_empty_unreleased_bumps_patch(self):
        """No change types in unreleased → PATCH is default."""
        cl = self._make_unreleased([], released_version="1.0.0")
        assert cl.suggest_future_version() == Version("1.0.1")


# ---------------------------------------------------------------------------
# Changelog.get
# ---------------------------------------------------------------------------

class TestChangelogGet:
    def test_get_no_version_returns_all(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={"1.0.0": {}})
        result = cl.get()
        assert "1.0.0" in result

    def test_get_specific_version_returns_that_version(self, tmp_path):
        changelog = {"1.0.0": {"metadata": {}}, "2.0.0": {"metadata": {}}}
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog=changelog)
        assert cl.get("1.0.0") == {"metadata": {}}

    def test_get_missing_version_raises_warning(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={"1.0.0": {}})
        with pytest.raises(logging.Warning, match="not available"):
            cl.get("9.9.9")


# ---------------------------------------------------------------------------
# Changelog.to_json / write_to_json
# ---------------------------------------------------------------------------

class TestChangelogJson:
    def _make_simple(self, tmp_path) -> Changelog:
        changelog = OrderedDict()
        changelog["1.0.0"] = {
            "metadata": {"version": "1.0.0", "release_date": "2024-01-01"},
            "added": ["Feature A"],
        }
        return Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog=changelog)

    def test_to_json_returns_valid_json(self, tmp_path):
        cl = self._make_simple(tmp_path)
        raw = cl.to_json()
        parsed = json.loads(raw)
        assert isinstance(parsed, list)

    def test_to_json_full_contains_all_versions(self, tmp_path):
        changelog = OrderedDict()
        changelog["2.0.0"] = {"metadata": {"version": "2.0.0", "release_date": "2024-06-01"}}
        changelog["1.0.0"] = {"metadata": {"version": "1.0.0", "release_date": "2024-01-01"}}
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog=changelog)
        parsed = json.loads(cl.to_json())
        assert len(parsed) == 2

    def test_write_to_json_creates_file(self, tmp_path):
        cl = self._make_simple(tmp_path)
        out = tmp_path / "out.json"
        cl.write_to_json(str(out))
        assert out.exists()
        parsed = json.loads(out.read_text())
        assert isinstance(parsed, list)

    def test_to_json_specific_version(self, tmp_path):
        changelog = OrderedDict()
        changelog["2.0.0"] = {"metadata": {"version": "2.0.0", "release_date": "2024-06-01"}}
        changelog["1.0.0"] = {"metadata": {"version": "1.0.0", "release_date": "2024-01-01"}}
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog=changelog)
        parsed = json.loads(cl.to_json(version="1.0.0"))
        # When requesting a specific version, get() returns the dict for that version
        # to_json wraps it in a list by iterating values — so it should be one item per field
        assert isinstance(parsed, list)


# ---------------------------------------------------------------------------
# Changelog.write_to_file / roundtrip
# ---------------------------------------------------------------------------

class TestChangelogWriteRoundtrip:
    def test_write_to_file_creates_file(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        cl.write_to_file()
        assert (tmp_path / "CHANGELOG.md").exists()

    def test_write_and_read_roundtrip(self, tmp_path):
        from changelogmanager.changelog_reader import ChangelogReader

        p = tmp_path / "CHANGELOG.md"
        changelog = OrderedDict()
        changelog[UNRELEASED_ENTRY] = {
            "metadata": {"version": UNRELEASED_ENTRY, "release_date": None},
            "added": ["Something new"],
        }
        changelog["1.0.0"] = {
            "metadata": {
                "version": "1.0.0",
                "release_date": "2024-01-01",
                "semantic_version": {
                    "major": 1, "minor": 0, "patch": 0,
                    "prerelease": None, "buildmetadata": None,
                },
            },
            "added": ["Initial release"],
        }
        cl = Changelog(file_path=str(p), changelog=changelog)
        cl.write_to_file()

        read_back = ChangelogReader(file_path=str(p)).read()
        assert UNRELEASED_ENTRY in read_back
        assert "1.0.0" in read_back


# ---------------------------------------------------------------------------
# Release then re-release (state mutation safety)
# ---------------------------------------------------------------------------

class TestReleaseSequence:
    def test_double_release_creates_two_distinct_versions(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        cl.add("added", "First feature")
        cl.release()  # → 0.0.1

        cl.add("fixed", "A fix")
        cl.release()  # → 0.0.2

        keys = list(cl.get().keys())
        assert "0.0.1" in keys
        assert "0.0.2" in keys
        assert UNRELEASED_ENTRY not in keys

    def test_release_then_add_then_release(self, tmp_path):
        cl = Changelog(file_path=str(tmp_path / "CHANGELOG.md"), changelog={})
        cl.add("added", "First")
        cl.release()
        cl.add("removed", "Dropped")
        cl.release()  # should be major bump from 0.0.1 → 1.0.0
        assert "1.0.0" in cl.get()
