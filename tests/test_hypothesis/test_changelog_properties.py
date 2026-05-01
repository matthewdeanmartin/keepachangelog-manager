"""Property-based tests for Changelog core logic."""

import json
import tempfile
from collections import OrderedDict
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from semantic_version import Version

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import CATEGORIES, TYPES_OF_CHANGE, UNRELEASED_ENTRY
from changelogmanager.changelog import INITIAL_VERSION, Changelog

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

valid_change_types = st.sampled_from(TYPES_OF_CHANGE)

# Printable text; min_size=1 keeps messages non-empty
changelog_message = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Zs")),
    min_size=1,
    max_size=120,
)

semver_strategy = st.builds(
    lambda major, minor, patch: f"{major}.{minor}.{patch}",
    major=st.integers(min_value=0, max_value=9),
    minor=st.integers(min_value=0, max_value=9),
    patch=st.integers(min_value=0, max_value=9),
)

# A non-empty subset of TYPES_OF_CHANGE
change_type_subsets = st.frozensets(valid_change_types, min_size=1)

# Suppress function-scoped-fixture warning: these tests create their own tmp dirs
_suppress = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])


def _tmp_changelog(tmp_dir: str) -> str:
    return str(Path(tmp_dir) / "CHANGELOG.md")


def make_changelog_with_unreleased(change_types, released_version=None, file_path="CHANGELOG.md"):
    changelog: dict = OrderedDict()
    unreleased: dict = {"metadata": {"version": UNRELEASED_ENTRY, "release_date": None}}
    for ct in change_types:
        unreleased[ct] = ["An entry"]
    changelog[UNRELEASED_ENTRY] = unreleased
    if released_version:
        v = Version(released_version)
        changelog[released_version] = {
            "metadata": {
                "version": released_version,
                "release_date": "2024-01-01",
                "semantic_version": {
                    "major": v.major,
                    "minor": v.minor,
                    "patch": v.patch,
                    "prerelease": None,
                    "buildmetadata": None,
                },
            }
        }
    return Changelog(file_path=file_path, changelog=changelog)


# ---------------------------------------------------------------------------
# add() invariants
# ---------------------------------------------------------------------------


class TestAddInvariants:
    @given(change_type=valid_change_types, message=changelog_message)
    def test_add_always_creates_unreleased(self, change_type, message):
        cl = Changelog(file_path="CHANGELOG.md", changelog={})
        cl.add(change_type, message)
        assert UNRELEASED_ENTRY in cl.get()

    @given(change_type=valid_change_types, message=changelog_message)
    def test_add_message_is_present(self, change_type, message):
        cl = Changelog(file_path="CHANGELOG.md", changelog={})
        cl.add(change_type, message)
        assert message in cl.get()[UNRELEASED_ENTRY][change_type]

    @given(change_type=valid_change_types, messages=st.lists(changelog_message, min_size=2, max_size=10))
    def test_add_preserves_insertion_order(self, change_type, messages):
        cl = Changelog(file_path="CHANGELOG.md", changelog={})
        for msg in messages:
            cl.add(change_type, msg)
        stored = cl.get()[UNRELEASED_ENTRY][change_type]
        assert stored == messages

    @given(change_type=valid_change_types, message=changelog_message)
    def test_unreleased_is_first_key_after_add(self, change_type, message):
        existing = OrderedDict({"1.0.0": {"metadata": {"version": "1.0.0", "release_date": "2024-01-01"}}})
        cl = Changelog(file_path="CHANGELOG.md", changelog=existing)
        cl.add(change_type, message)
        assert list(cl.get().keys())[0] == UNRELEASED_ENTRY

    @given(ct1=valid_change_types, ct2=valid_change_types, msg1=changelog_message, msg2=changelog_message)
    def test_add_multiple_types_both_present(self, ct1, ct2, msg1, msg2):
        cl = Changelog(file_path="CHANGELOG.md", changelog={})
        cl.add(ct1, msg1)
        cl.add(ct2, msg2)
        unreleased = cl.get()[UNRELEASED_ENTRY]
        assert msg1 in unreleased[ct1]
        assert msg2 in unreleased[ct2]

    @given(change_type=valid_change_types, message=changelog_message)
    def test_add_does_not_remove_existing_released_versions(self, change_type, message):
        existing = OrderedDict({"2.0.0": {"metadata": {"version": "2.0.0", "release_date": "2024-01-01"}}})
        cl = Changelog(file_path="CHANGELOG.md", changelog=existing)
        cl.add(change_type, message)
        assert "2.0.0" in cl.get()

    @given(change_type=valid_change_types, message=changelog_message)
    def test_add_count_increments(self, change_type, message):
        cl = Changelog(file_path="CHANGELOG.md", changelog={})
        cl.add(change_type, "existing")
        before = len(cl.get()[UNRELEASED_ENTRY][change_type])
        cl.add(change_type, message)
        after = len(cl.get()[UNRELEASED_ENTRY][change_type])
        assert after == before + 1


# ---------------------------------------------------------------------------
# suggest_future_version() invariants
# ---------------------------------------------------------------------------


class TestSuggestFutureVersionInvariants:
    @given(change_types=change_type_subsets)
    def test_only_unreleased_always_returns_initial(self, change_types):
        cl = make_changelog_with_unreleased(change_types)
        assert cl.suggest_future_version() == INITIAL_VERSION

    @given(change_types=change_type_subsets)
    def test_suggested_version_is_greater_than_current(self, change_types):
        cl = make_changelog_with_unreleased(change_types, released_version="1.0.0")
        assert cl.suggest_future_version() > Version("1.0.0")

    @given(change_types=change_type_subsets)
    def test_removed_always_bumps_major(self, change_types):
        assume("removed" in change_types)
        cl = make_changelog_with_unreleased(change_types, released_version="1.2.3")
        assert cl.suggest_future_version() == Version("2.0.0")

    @given(
        extra=st.frozensets(st.sampled_from([t for t in TYPES_OF_CHANGE if t not in ("added", "removed")]))
    )
    def test_added_without_removed_bumps_minor(self, extra):
        change_types = extra | {"added"}
        cl = make_changelog_with_unreleased(change_types, released_version="1.2.3")
        assert cl.suggest_future_version() == Version("1.3.0")

    @given(
        extra=st.frozensets(st.sampled_from(["fixed", "changed", "deprecated"]))
    )
    def test_security_without_removed_or_added_bumps_minor(self, extra):
        change_types = extra | {"security"}
        cl = make_changelog_with_unreleased(change_types, released_version="1.2.3")
        assert cl.suggest_future_version() == Version("1.3.0")

    @given(change_types=st.frozensets(st.sampled_from(["fixed", "changed", "deprecated"]), min_size=1))
    def test_patch_only_types_bump_patch(self, change_types):
        cl = make_changelog_with_unreleased(change_types, released_version="1.2.3")
        assert cl.suggest_future_version() == Version("1.2.4")

    @given(change_types=change_type_subsets, major=st.integers(min_value=0, max_value=5), minor=st.integers(min_value=0, max_value=9), patch=st.integers(min_value=0, max_value=9))
    def test_suggested_version_never_equal_to_current(self, change_types, major, minor, patch):
        released = f"{major}.{minor}.{patch}"
        cl = make_changelog_with_unreleased(change_types, released_version=released)
        assert cl.suggest_future_version() != Version(released)


# ---------------------------------------------------------------------------
# release() invariants
# ---------------------------------------------------------------------------


class TestReleaseInvariants:
    @given(change_types=change_type_subsets, override=semver_strategy)
    @settings(max_examples=50)
    def test_release_with_higher_version_removes_unreleased(self, change_types, override):
        assume(Version(override) > Version("0.0.0"))
        with tempfile.TemporaryDirectory() as tmp:
            cl = make_changelog_with_unreleased(change_types, released_version="0.0.0", file_path=_tmp_changelog(tmp))
            cl.release(override_version=override)
            assert UNRELEASED_ENTRY not in cl.get()

    @given(change_types=change_type_subsets, override=semver_strategy)
    @settings(max_examples=50)
    def test_release_new_version_is_first_key(self, change_types, override):
        assume(Version(override) > Version("0.0.0"))
        with tempfile.TemporaryDirectory() as tmp:
            cl = make_changelog_with_unreleased(change_types, released_version="0.0.0", file_path=_tmp_changelog(tmp))
            cl.release(override_version=override)
            assert list(cl.get().keys())[0] == override

    @given(change_types=change_type_subsets, override=semver_strategy)
    @settings(max_examples=50, deadline=None)
    def test_release_metadata_has_required_fields(self, change_types, override):
        assume(Version(override) > Version("0.0.0"))
        with tempfile.TemporaryDirectory() as tmp:
            cl = make_changelog_with_unreleased(change_types, released_version="0.0.0", file_path=_tmp_changelog(tmp))
            cl.release(override_version=override)
            meta = cl.get()[override]["metadata"]
            assert "version" in meta
            assert "release_date" in meta
            assert "semantic_version" in meta

    @given(change_types=change_type_subsets, override=semver_strategy)
    @settings(max_examples=50, deadline=None)
    def test_release_semver_fields_match_version_string(self, change_types, override):
        assume(Version(override) > Version("0.0.0"))
        with tempfile.TemporaryDirectory() as tmp:
            cl = make_changelog_with_unreleased(change_types, released_version="0.0.0", file_path=_tmp_changelog(tmp))
            cl.release(override_version=override)
            meta = cl.get()[override]["metadata"]
            v = Version(override)
            sv = meta["semantic_version"]
            assert sv["major"] == v.major
            assert sv["minor"] == v.minor
            assert sv["patch"] == v.patch

    @given(change_types=change_type_subsets)
    def test_release_without_override_produces_valid_semver(self, change_types):
        with tempfile.TemporaryDirectory() as tmp:
            cl = make_changelog_with_unreleased(change_types, released_version="1.0.0", file_path=_tmp_changelog(tmp))
            cl.release()
            for k in cl.get():
                if k != UNRELEASED_ENTRY:
                    Version(k)  # raises ValueError if not valid semver

    @given(change_types=change_type_subsets, override=semver_strategy)
    @settings(max_examples=50, deadline=None)
    def test_release_existing_versions_preserved(self, change_types, override):
        assume(Version(override) > Version("0.0.0"))
        with tempfile.TemporaryDirectory() as tmp:
            cl = make_changelog_with_unreleased(change_types, released_version="0.0.0", file_path=_tmp_changelog(tmp))
            cl.release(override_version=override)
            assert "0.0.0" in cl.get()

    @given(change_types=change_type_subsets, override=semver_strategy)
    @settings(max_examples=50)
    def test_release_date_is_iso_format(self, change_types, override):
        import re
        assume(Version(override) > Version("0.0.0"))
        with tempfile.TemporaryDirectory() as tmp:
            cl = make_changelog_with_unreleased(change_types, released_version="0.0.0", file_path=_tmp_changelog(tmp))
            cl.release(override_version=override)
            date_str = cl.get()[override]["metadata"]["release_date"]
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", date_str)


# ---------------------------------------------------------------------------
# release() error cases
# ---------------------------------------------------------------------------


class TestReleaseErrorCases:
    def test_release_without_unreleased_raises(self):
        cl = Changelog(file_path="CHANGELOG.md", changelog={})
        with pytest.raises(logging.Error):
            cl.release()

    @given(override=semver_strategy)
    def test_release_already_released_version_raises(self, override):
        changelog = OrderedDict()
        changelog[UNRELEASED_ENTRY] = {"metadata": {"version": UNRELEASED_ENTRY, "release_date": None}, "added": ["x"]}
        changelog[override] = {"metadata": {"version": override, "release_date": "2024-01-01"}}
        cl = Changelog(file_path="CHANGELOG.md", changelog=changelog)
        with pytest.raises(logging.Error):
            cl.release(override_version=override)

    @given(
        current=semver_strategy,
        older=semver_strategy,
    )
    def test_release_older_than_current_raises(self, current, older):
        assume(Version(older) < Version(current))
        changelog = OrderedDict()
        changelog[UNRELEASED_ENTRY] = {"metadata": {"version": UNRELEASED_ENTRY, "release_date": None}, "added": ["x"]}
        changelog[current] = {"metadata": {"version": current, "release_date": "2024-01-01"}}
        cl = Changelog(file_path="CHANGELOG.md", changelog=changelog)
        with pytest.raises(logging.Error):
            cl.release(override_version=older)


# ---------------------------------------------------------------------------
# v-prefix stripping in release()
# ---------------------------------------------------------------------------


class TestVPrefixStripping:
    @given(semver=semver_strategy)
    @settings(max_examples=40)
    def test_v_prefix_and_no_prefix_yield_same_result(self, semver):
        assume(Version(semver) > Version("0.0.0"))

        with tempfile.TemporaryDirectory() as tmp1:
            cl1 = make_changelog_with_unreleased({"added"}, released_version="0.0.0", file_path=_tmp_changelog(tmp1))
            cl1.release(override_version=semver)

        with tempfile.TemporaryDirectory() as tmp2:
            cl2 = make_changelog_with_unreleased({"added"}, released_version="0.0.0", file_path=_tmp_changelog(tmp2))
            cl2.release(override_version=f"v{semver}")

        assert semver in cl1.get()
        assert semver in cl2.get()


# ---------------------------------------------------------------------------
# version() / previous_version() ordering invariants
# ---------------------------------------------------------------------------


class TestVersionQueryInvariants:
    @given(versions=st.lists(semver_strategy, min_size=2, max_size=5, unique=True))
    def test_version_returns_first_non_unreleased_key(self, versions):
        changelog: dict = OrderedDict()
        changelog[UNRELEASED_ENTRY] = {"metadata": {"version": UNRELEASED_ENTRY, "release_date": None}}
        for v in versions:
            changelog[v] = {"metadata": {"version": v, "release_date": "2024-01-01"}}
        cl = Changelog(file_path="CHANGELOG.md", changelog=changelog)
        assert cl.version() == Version(versions[0])

    @given(versions=st.lists(semver_strategy, min_size=2, max_size=5, unique=True))
    def test_previous_version_returns_second_non_unreleased_key(self, versions):
        changelog: dict = OrderedDict()
        for v in versions:
            changelog[v] = {"metadata": {"version": v, "release_date": "2024-01-01"}}
        cl = Changelog(file_path="CHANGELOG.md", changelog=changelog)
        assert cl.previous_version() == Version(versions[1])

    @given(versions=st.lists(semver_strategy, min_size=1, max_size=5, unique=True))
    def test_version_empty_raises(self, versions):
        cl = Changelog(file_path="CHANGELOG.md", changelog={})
        with pytest.raises(logging.Warning):
            cl.version()

    @given(versions=st.lists(semver_strategy, min_size=1, max_size=1, unique=True))
    def test_previous_version_single_raises(self, versions):
        changelog = {versions[0]: {"metadata": {"version": versions[0], "release_date": "2024-01-01"}}}
        cl = Changelog(file_path="CHANGELOG.md", changelog=changelog)
        with pytest.raises(logging.Warning):
            cl.previous_version()


# ---------------------------------------------------------------------------
# to_json() round-trip
# ---------------------------------------------------------------------------


class TestJsonRoundtrip:
    @given(change_type=valid_change_types, messages=st.lists(changelog_message, min_size=1, max_size=5))
    def test_to_json_is_valid_json(self, change_type, messages):
        cl = Changelog(file_path="CHANGELOG.md", changelog={})
        for msg in messages:
            cl.add(change_type, msg)
        raw = cl.to_json()
        parsed = json.loads(raw)
        assert isinstance(parsed, list)

    @given(
        change_type=valid_change_types,
        messages=st.lists(changelog_message, min_size=1, max_size=5),
    )
    def test_to_json_messages_survive_roundtrip(self, change_type, messages):
        cl = Changelog(file_path="CHANGELOG.md", changelog={})
        for msg in messages:
            cl.add(change_type, msg)
        # Parse the JSON and verify messages are intact in the decoded structure
        parsed = json.loads(cl.to_json())
        stored = parsed[0][change_type]
        assert stored == messages
