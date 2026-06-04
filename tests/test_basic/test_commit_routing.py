import io
import json
import subprocess
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

import changelogmanager.llvm_diagnostics as logging
from changelogmanager import cli, commit_routing, services
from changelogmanager.commit_routing import CommitWithFiles

VALID_CHANGELOG = """\
# Changelog

## [Unreleased]
### Added
- Existing entry

## [1.0.0] - 2024-01-01
### Added
- Initial release
"""


def run_cli(arguments: list[str]) -> tuple[int, str]:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = cli.main(arguments)
    return exit_code, stdout.getvalue()


def write_changelog(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(VALID_CHANGELOG, encoding="utf-8")


def write_component_config(path: Path) -> None:
    path.write_text(
        "[[components]]\n"
        'name = "api"\n'
        'changelog = "api/CHANGELOG.md"\n'
        'match = ["api/**"]\n'
        "\n"
        "[[components]]\n"
        'name = "web"\n'
        'changelog = "web/CHANGELOG.md"\n'
        'match = ["web/**"]\n'
        "\n"
        "[[components]]\n"
        'name = "default"\n'
        'changelog = "CHANGELOG.md"\n'
        "\n"
        "[versioning]\n"
        'scheme = "semver"\n',
        encoding="utf-8",
    )


def test_parse_log_with_files_parses_multifile_records():
    commits = commit_routing.parse_log_with_files(
        "\x1ecommit\x1efeat: add api\napi/service.py\napi/tests/test_service.py\n"
        "\x1ecommit\x1efix: repair ui\nweb/app.js\n"
    )

    assert commits == [
        CommitWithFiles(
            subject="feat: add api",
            files=("api/service.py", "api/tests/test_service.py"),
        ),
        CommitWithFiles(subject="fix: repair ui", files=("web/app.js",)),
    ]


def test_file_matches_supports_recursive_globs_and_windows_paths():
    assert commit_routing.file_matches(r"api\v1\users.py", ["api/**"])
    assert commit_routing.file_matches("api", ["api/**"])
    assert not commit_routing.file_matches("docs/README.md", ["api/**"])


def test_route_commit_returns_matches_or_fallback():
    components = [
        {"name": "api", "match": ["api/**", "shared/**"]},
        {"name": "web", "match": ["web/**", "shared/**"]},
        {"name": "default", "changelog": "CHANGELOG.md"},
    ]

    assert commit_routing.route_commit(["shared/models.py"], components) == {
        "api",
        "web",
    }
    assert commit_routing.route_commit(["README.md"], components) == {"default"}


def test_validate_routing_components_rejects_multiple_fallbacks():
    with pytest.raises(logging.Error, match="multiple: api, web"):
        commit_routing.validate_routing_components(
            [{"name": "api"}, {"name": "web"}, {"name": "docs", "match": ["docs/**"]}],
            config_path="changelogmanager.toml",
        )


def test_git_executable_errors_when_git_is_missing(monkeypatch):
    monkeypatch.setattr(commit_routing.shutil, "which", lambda name: None)

    with pytest.raises(logging.Error, match="git executable not found on PATH"):
        commit_routing.git_executable()


def test_git_log_with_files_invokes_git_and_parses_output(monkeypatch):
    monkeypatch.setattr(commit_routing, "git_executable", lambda: "git")
    recorded: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        recorded["cmd"] = cmd
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        return SimpleNamespace(stdout="\x1ecommit\x1efeat: add api\napi/service.py\n")

    monkeypatch.setattr(commit_routing.subprocess, "run", fake_run)

    commits = commit_routing.git_log_with_files("v1.0.0")

    assert recorded["cmd"] == [
        "git",
        "log",
        "--no-merges",
        "--name-only",
        "--pretty=format:\x1ecommit\x1e%s",
        "v1.0.0..HEAD",
    ]
    assert commits == [
        CommitWithFiles(subject="feat: add api", files=("api/service.py",))
    ]


def test_git_log_with_files_wraps_subprocess_failures(monkeypatch):
    monkeypatch.setattr(commit_routing, "git_executable", lambda: "git")

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["git", "log"])

    monkeypatch.setattr(commit_routing.subprocess, "run", fake_run)

    with pytest.raises(logging.Error, match="git log failed"):
        commit_routing.git_log_with_files(None)


def test_main_from_commits_all_routes_commits_to_matching_components(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "changelogmanager.toml"
    write_component_config(config_path)
    write_changelog(tmp_path / "CHANGELOG.md")
    write_changelog(tmp_path / "api" / "CHANGELOG.md")
    write_changelog(tmp_path / "web" / "CHANGELOG.md")

    monkeypatch.setattr(
        services,
        "git_log_with_files",
        lambda since: [
            CommitWithFiles("feat(api): add endpoint", ("api/service.py",)),
            CommitWithFiles("fix(ui): repair button", ("web/app.js",)),
            CommitWithFiles("feat: improve overview", ("README.md",)),
        ],
    )

    exit_code, output = run_cli(
        ["--config", str(config_path), "from-commits", "--all", "--all-history"]
    )

    assert exit_code == 0
    assert "[api] added: [added] add endpoint" in output
    assert "[web] added: [fixed] repair button" in output
    assert "[default] added: [added] improve overview" in output
    assert "add endpoint" in (tmp_path / "api" / "CHANGELOG.md").read_text(
        encoding="utf-8"
    )
    assert "repair button" in (tmp_path / "web" / "CHANGELOG.md").read_text(
        encoding="utf-8"
    )
    assert "improve overview" in (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")


def test_main_from_commits_all_dry_run_reports_json_and_skips_unmatched_strict_commits(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "changelogmanager.toml"
    write_component_config(config_path)
    for changelog_path in (
        tmp_path / "CHANGELOG.md",
        tmp_path / "api" / "CHANGELOG.md",
        tmp_path / "web" / "CHANGELOG.md",
    ):
        write_changelog(changelog_path)
    originals = {
        path: path.read_text(encoding="utf-8")
        for path in (
            tmp_path / "CHANGELOG.md",
            tmp_path / "api" / "CHANGELOG.md",
            tmp_path / "web" / "CHANGELOG.md",
        )
    }

    monkeypatch.setattr(
        services,
        "git_log_with_files",
        lambda since: [
            CommitWithFiles("this does not match", ("api/service.py",)),
            CommitWithFiles("feat: improve overview", ("README.md",)),
        ],
    )

    exit_code, output = run_cli(
        [
            "--json",
            "--config",
            str(config_path),
            "from-commits",
            "--all",
            "--all-history",
            "--strict",
            "--dry-run",
        ]
    )

    payload = json.loads(output)
    assert exit_code == 0
    assert payload["skipped"] == 1
    assert payload["since"] is None
    assert payload["dry_run"] == "would add 1 entries across 3 components"
    assert payload["components"] == [
        {"component": "api", "path": "api/CHANGELOG.md", "added": []},
        {"component": "web", "path": "web/CHANGELOG.md", "added": []},
        {
            "component": "default",
            "path": "CHANGELOG.md",
            "added": [{"change_type": "added", "message": "improve overview"}],
        },
    ]
    for path, original in originals.items():
        assert path.read_text(encoding="utf-8") == original


def test_main_from_commits_all_requires_a_config_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    assert cli.main(["from-commits", "--all", "--all-history"]) == 1
