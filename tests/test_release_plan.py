"""Release metadata controls versions without relying on git or provider state."""

import json
from pathlib import Path

import pytest

from changelogmanager.change_types import VersionCore
from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader
from changelogmanager.cli import main
from changelogmanager.cli.loaders import load_changelog
from changelogmanager.github import GitHub
from changelogmanager.release_plan import get_plan
from changelogmanager.versioning import bump_version, parse_version


def text(
    phase=None, target=None, versions=("1.3.0",), category="Added", heading="## Release"
):
    plan = ""
    if phase is not None:
        plan = f"{heading}\n- Phase: {phase}\n"
        if target is not None:
            plan += f"- Target: {target}\n"
        plan += "\n"
    upcoming = "## [Unreleased]\n\n"
    if heading.startswith("###"):
        upcoming += plan
        plan = ""
    if category:
        upcoming += f"### {category}\n- Support Python 3.17.\n\n"
    history = "".join(
        f"## [{v}] - 2026-01-01\n### Added\n- Previous release.\n\n" for v in versions
    )
    return (
        "# Changelog\n\nAll notable changes follow Keep a Changelog and PEP 440.\n\n"
        + plan
        + upcoming
        + history
    )


def model(content, tmp_path, scheme="pep440"):
    target = tmp_path / "CHANGELOG.md"
    target.write_text(content, encoding="utf-8")
    return Changelog(
        str(target),
        ChangelogReader(str(target), versioning_scheme=scheme).read(),
        versioning_scheme=scheme,
    )


@pytest.mark.parametrize("heading", ["## Release", "### Release"])
def test_round_trip_preserves_release_fields_through_edits_and_format(
    tmp_path, heading
):
    changelog = model(text("Alpha", "1.4.0", heading=heading), tmp_path)
    assert str(changelog.suggest_future_version()) == "1.4.0a1"
    changelog.add("fixed", "Handle Windows.")
    changelog.write_to_file()
    loaded = model(Path(changelog.get_file_path()).read_text(), tmp_path)
    assert get_plan(loaded.get()) == {"phase": "alpha", "target": "1.4.0"}
    assert "Handle Windows." in loaded.render()
    assert (
        main(
            [
                "--input-file",
                str(tmp_path / "CHANGELOG.md"),
                "validate",
                "--fix",
                "--format",
            ]
        )
        == 0
    )
    assert "- Phase: alpha" in (tmp_path / "CHANGELOG.md").read_text()
    exported = json.loads(loaded.to_json())
    assert exported[0]["metadata"]["release_plan"]["target"] == "1.4.0"


@pytest.mark.parametrize(
    "phase,versions,expected",
    [
        ("alpha", ("1.3.0",), "1.4.0a1"),
        (None, ("1.4.0a1", "1.3.0"), "1.4.0a2"),
        ("beta", ("1.4.0a2", "1.3.0"), "1.4.0b1"),
        (None, ("1.4.0b9", "1.4.0b2", "1.3.0"), "1.4.0b10"),
        ("rc", ("1.4.0b1", "1.3.0"), "1.4.0rc1"),
        ("final", ("1.4.0rc1", "1.3.0"), "1.4.0"),
        ("dev", ("1.3.0",), "1.4.0.dev1"),
        (None, ("1.4.0.dev1", "1.3.0"), "1.4.0.dev2"),
        ("alpha", ("1.4.0.dev2", "1.3.0"), "1.4.0a1"),
        (None, ("1.3.0",), "1.4.0"),
        ("alpha", ("2!1.3.0",), "2!1.4.0a1"),
    ],
)
def test_phase_progression_and_repeatable_previews(tmp_path, phase, versions, expected):
    changelog = model(text(phase, versions=versions), tmp_path)
    before = (tmp_path / "CHANGELOG.md").read_bytes()
    assert str(changelog.suggest_future_version()) == expected
    assert str(changelog.suggest_future_version()) == expected
    assert (tmp_path / "CHANGELOG.md").read_bytes() == before


def test_optional_target_and_first_release(tmp_path):
    changelog = model(text("rc", "3.0", versions=()), tmp_path)
    assert str(changelog.suggest_future_version()) == "3.0rc1"
    changelog = model(text("alpha", versions=()), tmp_path)
    changelog.initial_version_override = "0.2.0"
    assert str(changelog.suggest_future_version()) == "0.2.0a1"


@pytest.mark.parametrize(
    "content,error",
    [
        (text("preview"), "Phase"),
        (text("alpha", "nonsense"), "Target"),
        (text("alpha", "1.4.0rc2"), "Target"),
        (text("alpha", "1.4.0+local"), "Target"),
        (
            text("alpha").replace("- Phase: alpha", "- Phase: alpha\n- Phase: beta"),
            "Duplicate",
        ),
        (text("alpha").replace("- Phase: alpha", "- Maturity: alpha"), "Phase"),
        (text("alpha").replace("- Phase: alpha", "- Target: 1.4.0"), "Phase"),
        (
            text("alpha").replace(
                "## Release", "## Release\n- Phase: beta\n\n## Release"
            ),
            "Only one",
        ),
        (text("alpha", versions=("1.4.0b1", "1.3.0")), "does not advance"),
        (text("rc", "1.3.0"), "does not advance"),
        (text("rc", versions=("1.4.0a1", "1.3.0"), category="Removed"), "Target"),
        (
            text("alpha").replace("## [Unreleased]", "## [1.4.0] - 2026-01-01"),
            "Unreleased",
        ),
    ],
)
def test_invalid_plans_fail_without_modifying_file(tmp_path, content, error):
    target = tmp_path / "CHANGELOG.md"
    target.write_text(content)
    before = target.read_bytes()
    with pytest.raises(Exception, match=error):
        ChangelogReader(str(target), versioning_scheme="pep440").read()
    assert target.read_bytes() == before


def test_release_block_cannot_be_attached_to_historical_release(tmp_path):
    with pytest.raises(Exception, match="history"):
        model(text() + "### Release\n- Phase: alpha\n", tmp_path)


def test_explicit_retarget_handles_larger_changes(tmp_path):
    changelog = model(
        text("alpha", "2.0.0", versions=("1.4.0a1", "1.3.0"), category="Removed"),
        tmp_path,
    )
    assert str(changelog.suggest_future_version()) == "2.0.0a1"


def test_cli_release_consumes_plan_and_updates_package_then_finalizes(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "pyproject.toml"
    config.write_text(
        '[project]\nname = "demo"\nversion = "1.3.0"\n[tool.changelogmanager.versioning]\nscheme = "pep440"\n'
    )
    changelog = model(text("alpha"), tmp_path)
    assert main(["release", "--bump-versions", "--yes"]) == 0
    assert 'version = "1.4.0a1"' in config.read_text()
    assert "## Release" not in (tmp_path / "CHANGELOG.md").read_text()
    changelog = load_changelog(str(config), "default", str(tmp_path / "CHANGELOG.md"))
    changelog.set_release_plan("final")
    changelog.write_to_file()
    calls = []
    monkeypatch.setattr(GitHub, "get_releases", lambda self: [])
    monkeypatch.setattr(
        GitHub,
        "github_request",
        lambda self, method, api, data: calls.append(data) or {"id": 1, **data},
    )
    assert (
        main(
            ["github-release", "--repository", "example/repo", "--github-token", "fake"]
        )
        == 0
    )
    assert calls[-1]["tag_name"] == "v1.4.0"
    assert calls[-1]["prerelease"] is False
    assert main(["release", "--bump-versions", "--yes"]) == 0
    assert 'version = "1.4.0"' in config.read_text()
    assert main(["validate", "--strict"]) == 0


def test_override_cannot_contradict_changelog_plan(tmp_path):
    changelog = model(text("alpha", "1.4.0"), tmp_path)
    with pytest.raises(Exception, match="Phase"):
        changelog.release("1.4.0rc1")
    with pytest.raises(Exception, match="Target"):
        changelog.release("1.5.0a1")


def test_github_prerelease_is_derived_from_plan(tmp_path, monkeypatch):
    changelog = model(text("beta", "1.4.0"), tmp_path)
    calls = []
    monkeypatch.setattr(GitHub, "get_releases", lambda self: [])
    monkeypatch.setattr(
        GitHub,
        "github_request",
        lambda self, method, api, data: calls.append(data) or {"id": 1, **data},
    )
    GitHub(repository="example/repo", token="fake").create_release(
        changelog, draft=True
    )
    assert calls[-1]["prerelease"] is True
    assert calls[-1]["tag_name"] == "v1.4.0b1"
    assert "Phase:" not in calls[-1]["body"]
    assert "Support Python 3.17." in calls[-1]["body"]


def test_empty_finalization_cannot_retarget(tmp_path):
    with pytest.raises(Exception, match="active prerelease Target"):
        model(
            text("final", "2.0.0", versions=("1.4.0rc1", "1.3.0"), category=None),
            tmp_path,
        )


def test_semver_prereleases_and_explicit_overrides_still_work(tmp_path):
    changelog = model(
        text(versions=("1.4.0-alpha.1",)).replace("PEP 440", "Semantic Versioning"),
        tmp_path,
        "semver",
    )
    changelog.release("1.4.0-beta.1")
    assert str(changelog.version()) == "1.4.0-beta.1"


@pytest.mark.parametrize(
    "scheme,previous,expected",
    [("semver", "1.3.0", "1.4.0"), ("calver", "2026.09.0", None)],
)
def test_non_pep440_projects_keep_existing_bump_behavior(
    tmp_path, scheme, previous, expected
):
    content = text(versions=(previous,)).replace(
        "PEP 440",
        "Semantic Versioning" if scheme == "semver" else "Calendar Versioning",
    )
    changelog = model(content, tmp_path, scheme)
    result = changelog.suggest_future_version()
    assert result == bump_version(parse_version(previous, scheme), VersionCore.MINOR)
    if expected:
        assert str(result) == expected
    with pytest.raises(Exception, match="pep440"):
        model(text("alpha", versions=(previous,)), tmp_path, scheme)
