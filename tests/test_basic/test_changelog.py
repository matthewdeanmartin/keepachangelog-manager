import json
from collections import OrderedDict
from datetime import datetime as real_datetime

import pytest
from semantic_version import Version

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import UNRELEASED_ENTRY
from changelogmanager.changelog import INITIAL_VERSION, Changelog


def released_entry(version, release_date="2024-01-01", **sections):
    entry = {"metadata": {"version": version, "release_date": release_date}}
    entry.update(sections)
    return entry


def test_add_creates_unreleased_section_on_top_and_appends_messages():
    changelog = Changelog(
        changelog=OrderedDict([("1.0.0", released_entry("1.0.0", fixed=["Old fix"]))])
    )

    changelog.add("fixed", "Fresh fix")
    changelog.add("fixed", "Another fix")

    content = changelog.get()
    assert list(content) == [UNRELEASED_ENTRY, "1.0.0"]
    assert content[UNRELEASED_ENTRY]["metadata"] == {
        "version": UNRELEASED_ENTRY,
        "release_date": None,
    }
    assert content[UNRELEASED_ENTRY]["fixed"] == ["Fresh fix", "Another fix"]


def test_get_returns_specific_version_and_warns_for_missing_version():
    changelog = Changelog(changelog=OrderedDict([("1.0.0", released_entry("1.0.0"))]))

    assert changelog.get("1.0.0")["metadata"]["version"] == "1.0.0"

    with pytest.raises(logging.Warning, match="Version '2.0.0' not available"):
        changelog.get("2.0.0")


def test_release_requires_unreleased_section():
    changelog = Changelog(changelog=OrderedDict([("1.0.0", released_entry("1.0.0"))]))

    with pytest.raises(logging.Error, match="Unable to release without \\[Unreleased\\] section"):
        changelog.release()


def test_release_strips_v_prefix_and_updates_metadata(monkeypatch):
    class FrozenDateTime:
        @classmethod
        def now(cls):
            return real_datetime(2024, 2, 3)

    monkeypatch.setattr("changelogmanager.changelog.datetime", FrozenDateTime)
    changelog = Changelog(
        changelog=OrderedDict(
            [
                (
                    UNRELEASED_ENTRY,
                    {
                        "metadata": {"version": UNRELEASED_ENTRY, "release_date": None},
                        "added": ["New thing"],
                    },
                ),
                ("1.0.0", released_entry("1.0.0")),
            ]
        )
    )

    changelog.release("v1.1.0")

    assert list(changelog.get()) == ["1.1.0", "1.0.0"]
    metadata = changelog.get("1.1.0")["metadata"]
    assert metadata["version"] == "1.1.0"
    assert metadata["release_date"] == "2024-02-03"
    assert metadata["semantic_version"] == {
        "buildmetadata": None,
        "major": 1,
        "minor": 1,
        "patch": 0,
        "prerelease": None,
    }


def test_release_rejects_duplicate_and_older_versions():
    duplicate = Changelog(
        changelog=OrderedDict(
            [
                (
                    UNRELEASED_ENTRY,
                    {"metadata": {"version": UNRELEASED_ENTRY, "release_date": None}},
                ),
                ("1.0.0", released_entry("1.0.0")),
            ]
        )
    )
    with pytest.raises(logging.Error, match="already released version '1.0.0'"):
        duplicate.release("1.0.0")

    older = Changelog(
        changelog=OrderedDict(
            [
                (
                    UNRELEASED_ENTRY,
                    {"metadata": {"version": UNRELEASED_ENTRY, "release_date": None}},
                ),
                ("2.0.0", released_entry("2.0.0")),
                ("1.0.0", released_entry("1.0.0")),
            ]
        )
    )
    with pytest.raises(logging.Error, match="Unable to release a version older than the last release '2.0.0'"):
        older.release("1.5.0")


def test_version_and_previous_version_cover_edge_cases():
    with pytest.raises(logging.Warning, match="No versions available"):
        Changelog().version()

    only_unreleased = Changelog(
        changelog=OrderedDict(
            [
                (
                    UNRELEASED_ENTRY,
                    {"metadata": {"version": UNRELEASED_ENTRY, "release_date": None}},
                )
            ]
        )
    )
    with pytest.raises(logging.Warning, match="Only an Unreleased version is available"):
        only_unreleased.version()
    with pytest.raises(logging.Warning, match="No previous versions available"):
        only_unreleased.previous_version()

    released = Changelog(
        changelog=OrderedDict(
            [
                (
                    UNRELEASED_ENTRY,
                    {"metadata": {"version": UNRELEASED_ENTRY, "release_date": None}},
                ),
                ("2.0.0", released_entry("2.0.0")),
                ("1.5.0", released_entry("1.5.0")),
            ]
        )
    )

    assert released.version() == Version("2.0.0")
    assert released.previous_version() == Version("1.5.0")


def test_suggest_future_version_uses_highest_bump_and_initial_version():
    only_unreleased = Changelog(
        changelog=OrderedDict(
            [
                (
                    UNRELEASED_ENTRY,
                    {
                        "metadata": {"version": UNRELEASED_ENTRY, "release_date": None},
                        "fixed": ["Patch only"],
                    },
                )
            ]
        )
    )
    assert only_unreleased.suggest_future_version() == INITIAL_VERSION

    changelog = Changelog(
        changelog=OrderedDict(
            [
                (
                    UNRELEASED_ENTRY,
                    {
                        "metadata": {"version": UNRELEASED_ENTRY, "release_date": None},
                        "fixed": ["Patch"],
                        "added": ["Minor"],
                        "removed": ["Major"],
                    },
                ),
                ("1.2.3", released_entry("1.2.3")),
            ]
        )
    )

    assert changelog.suggest_future_version() == Version("2.0.0")


def test_to_json_and_write_to_json_render_changelog_content(tmp_path):
    changelog = Changelog(
        changelog=OrderedDict([("1.0.0", released_entry("1.0.0", added=["Feature"]))])
    )

    rendered = changelog.to_json()
    assert json.loads(rendered) == [
        {"metadata": {"version": "1.0.0", "release_date": "2024-01-01"}, "added": ["Feature"]}
    ]

    output_file = tmp_path / "CHANGELOG.json"
    changelog.write_to_json(str(output_file))
    assert json.loads(output_file.read_text(encoding="utf-8")) == json.loads(rendered)


def test_write_to_file_uses_string_representation_and_exists(tmp_path, monkeypatch):
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog = Changelog(file_path=str(changelog_file), changelog=OrderedDict())

    monkeypatch.setattr(
        "changelogmanager.changelog.keepachangelog.from_dict",
        lambda data: "rendered changelog",
    )

    assert not changelog.exists()
    assert str(changelog) == "rendered changelog"

    changelog.write_to_file()

    assert changelog.exists()
    assert changelog_file.read_text(encoding="utf-8") == "rendered changelog"
