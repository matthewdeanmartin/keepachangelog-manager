"""Release refresh keeps provider-owned assets and user-authored metadata."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from changelogmanager.change_types import VersionCore
from changelogmanager.cli import main
from changelogmanager.cli.loaders import load_changelog
from changelogmanager.commit_routing import file_matches
from changelogmanager.github import (
    NOTES_END,
    NOTES_START,
    GitHub,
    HttpMethods,
    merge_generated_notes,
)
from changelogmanager.versioning import bump_version, parse_version
from tests.test_maintenance_sprint1 import project


def test_refresh_exact_release_preserves_human_notes_and_metadata(
    tmp_path, monkeypatch
):
    config = project(tmp_path)
    existing = {
        "id": 17,
        "tag_name": "plugin-v1.1.0rc1",
        "draft": True,
        "prerelease": True,
        "name": "Our launch",
        "assets": [{"id": 41}],
        "body": f"Human introduction\n{NOTES_START}\nOld generated notes\n{NOTES_END}\nHuman footer",
    }
    other = {"id": 18, "tag_name": "v1.1.0rc1", "draft": True}
    monkeypatch.setattr(GitHub, "get_releases", lambda self: [other, existing])
    requests = []

    def request(self, method, api, data=None):
        requests.append((method, api, data))
        return {**existing, **data}

    monkeypatch.setattr(GitHub, "github_request", request)
    args = [
        "--config",
        str(config),
        "--component",
        "plugin",
        "github-release",
        "--repository",
        "owner/repo",
        "--github-token",
        "fake",
        "--version",
        "1.1.0rc1",
    ]
    assert main(args) == 0
    method, api, data = requests.pop()
    assert method == HttpMethods.PATCH and api == "releases/17"
    assert set(data) == {
        "body"
    }  # assets/name/channel/tag/target remain owned by GitHub/user
    assert data["body"].startswith("Human introduction\n")
    assert data["body"].endswith("\nHuman footer")
    assert "Repair parsing." in data["body"]
    assert "Old generated notes" not in data["body"]
    assert main([*args, "--release"]) == 0
    assert requests[-1][2]["draft"] is False


def test_create_pep440_prerelease_and_publish_existing_section(tmp_path, monkeypatch):
    config = project(tmp_path)
    monkeypatch.setattr(GitHub, "get_releases", lambda self: [])
    requests = []

    def request(self, method, api, data=None):
        requests.append((method, api, data))
        return {"id": 17, **data}

    monkeypatch.setattr(GitHub, "github_request", request)
    base = ["--config", str(config), "--component", "plugin"]
    remote = [
        "github-release",
        "--repository",
        "owner/repo",
        "--github-token",
        "fake",
        "--version",
        "plugin-v1.1.0rc1",
    ]
    assert main([*base, *remote]) == 0
    assert requests[-1][2]["prerelease"] is True
    assert requests[-1][2]["tag_name"] == "plugin-v1.1.0rc1"
    # The intentional local bump can happen before or after provider creation.
    assert main([*base, "release", "--override-version", "1.1.0rc1", "--yes"]) == 0
    assert main([*base, *remote, "--release"]) == 0
    assert "Repair parsing." in requests[-1][2]["body"]
    assert requests[-1][2]["draft"] is False


def test_failed_refresh_never_deletes_release_or_assets(tmp_path, monkeypatch):
    config = project(tmp_path)
    monkeypatch.setattr(
        GitHub,
        "get_releases",
        lambda self: [
            {"id": 17, "tag_name": "v1.0.1", "draft": True, "body": "Human note"}
        ],
    )
    requests = []

    def fail(self, method, api, data=None):
        requests.append(method)
        raise OSError("network failure")

    monkeypatch.setattr(GitHub, "github_request", fail)
    with pytest.raises(OSError, match="network failure"):
        GitHub("owner/repo", "fake").create_release(
            load_changelog(str(config), "plugin", None), True
        )
    assert requests == [HttpMethods.PATCH]


def test_background_refresh_leaves_published_release_unchanged(tmp_path, monkeypatch):
    config = project(tmp_path)
    existing = {
        "id": 17,
        "tag_name": "v1.0.1",
        "draft": False,
        "body": "Published notes",
    }
    monkeypatch.setattr(GitHub, "get_releases", lambda self: [existing])
    request = Mock(side_effect=AssertionError("must not mutate"))
    monkeypatch.setattr(GitHub, "github_request", request)
    result = GitHub("owner/repo", "fake").create_release(
        load_changelog(str(config), "plugin", None), True
    )
    assert result == existing
    request.assert_not_called()


def test_legacy_notes_preserved_and_refresh_is_idempotent():
    old = "Hand-edited legacy notes"
    first = merge_generated_notes(old, "Current generated notes")
    assert first.startswith(old)
    assert merge_generated_notes(first, "Current generated notes") == first
    with pytest.raises(Exception, match="markers"):
        merge_generated_notes(NOTES_START + "broken", "New notes")


@pytest.mark.parametrize(
    "path,pattern,expected",
    [
        ("api/readme.md", "api/**/*.py", False),
        ("api/main.py", "api/**/*.py", True),
        ("api/nested/main.py", "api/**/*.py", True),
        ("api/nested/main.py", "api/*.py", False),
        ("API/main.py", "api/**", False),
        ("api/main.py", "**/*.py", True),
        ("main.py", "**/*.py", True),
    ],
)
def test_component_globs_match_exact_file_patterns(path, pattern, expected):
    assert file_matches(path, [pattern]) is expected


def test_pep440_bump_preserves_epoch():
    assert (
        str(bump_version(parse_version("2!1.2.0", "pep440"), VersionCore.PATCH))
        == "2!1.2.1"
    )


def test_explicit_default_value_wins_over_config(tmp_path):
    from changelogmanager.cli.config_resolve import apply_config_defaults
    from changelogmanager.cli.parser import build_parser

    config = tmp_path / "changelogmanager.toml"
    config.write_text('[defaults]\ncommit_schema = "conventional"\n')
    parser = build_parser()
    args = parser.parse_args(["from-commits", "--commit-schema", "auto"])
    apply_config_defaults(args, str(config))
    assert args.commit_schema == "auto"
    args = parser.parse_args(["from-commits"])
    apply_config_defaults(args, str(config))
    assert args.commit_schema == "conventional"


def test_equivalent_pep440_release_is_rejected(tmp_path):
    config = project(tmp_path)
    changelog = load_changelog(str(config), "plugin", None)
    with pytest.raises(Exception, match="already released"):
        changelog.release("1.0")


def test_actions_outputs_preserve_existing_values_and_reject_injection(tmp_path):
    from changelogmanager.cli.actions_output import write_outputs

    output = tmp_path / "outputs"
    output.write_text("previous=value\n")
    write_outputs(
        output, {"version": "1.2rc1", "branch": "release/plugin", "commit_sha": "abc"}
    )
    assert (
        output.read_text()
        == "previous=value\nversion=1.2rc1\nbranch=release/plugin\ncommit_sha=abc\n"
    )
    before = output.read_bytes()
    with pytest.raises(Exception, match="multiline"):
        write_outputs(output, {"version": "1.2rc1\nevil=value"})
    assert output.read_bytes() == before


def test_gui_remote_release_passes_component_and_explicit_version(
    tmp_path, monkeypatch
):
    from changelogmanager.gui.screens.releases import ReleasesScreen

    config = project(tmp_path)
    runner = Mock(return_value=(0, ""))
    monkeypatch.setattr("changelogmanager.gui.screens.releases.run_cli", runner)

    def value(text):
        return SimpleNamespace(get=lambda: text)

    screen = SimpleNamespace(
        command="github-release",
        app_state=SimpleNamespace(
            config_path=str(config),
            component="plugin",
            input_file=str(tmp_path / "CHANGELOG.md"),
            error_format="llvm",
            dry_run=True,
        ),
        version_var=value("1.1.0rc1"),
        repo_var=value("owner/repo"),
        token_var=value("fake"),
        draft_var=value(True),
        output=Mock(),
        status=Mock(),
        redact=ReleasesScreen.redact,
    )
    ReleasesScreen.run_selected(screen)
    argv = runner.call_args.args[0]
    assert argv[argv.index("--component") + 1] == "plugin"
    assert argv[argv.index("--version") + 1] == "1.1.0rc1"
