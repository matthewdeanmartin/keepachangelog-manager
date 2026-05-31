import pytest

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.schema_validation import (
    get_changelog_export_schema,
    get_changelog_mapping_schema,
    validate_changelog_export,
    validate_changelog_mapping,
)


def release(version="1.0.0", release_date="2024-01-01"):
    return {
        "metadata": {"version": version, "release_date": release_date},
        "added": ["Feature"],
    }


def test_current_schema_validates_current_mapping_and_export():
    validate_changelog_mapping({"1.0.0": release()})
    validate_changelog_export([release()])


def test_future_schema_versions_are_not_accepted_until_defined():
    with pytest.raises(logging.Error, match="Only the current schema exists today"):
        validate_changelog_export([release()], schema_version="v2")  # type: ignore[arg-type]


def test_schema_rejects_unknown_change_type():
    with pytest.raises(logging.Error, match="Invalid changelog data: 1.0.0"):
        validate_changelog_mapping(
            {"1.0.0": {**release(), "surprise": ["Nope"]}},
            file_path="CHANGELOG.md",
        )


def test_schema_rejects_bad_release_date():
    with pytest.raises(logging.Error, match="release_date"):
        validate_changelog_export(
            [{"metadata": {"version": "1.0.0", "release_date": "2024-99-99"}}],
            file_path="CHANGELOG.json",
        )


def test_schema_accessors_return_copies():
    mapping_schema = get_changelog_mapping_schema()
    export_schema = get_changelog_export_schema()

    mapping_schema["title"] = "mutated"
    export_schema["title"] = "mutated"

    assert get_changelog_mapping_schema()["title"] != "mutated"
    assert get_changelog_export_schema()["title"] != "mutated"
