"""Tests for the `release-bump`, `release-rollback`, and `lint-message` commands.

These cover the CLI wiring (arg parsing, dry-run rendering, exit codes). The
`release-bump` cases stay dry-run (no git/network); the `release-rollback` cases
use a real temp git repo for the tag path and mock ``GitHub`` for the release
deletion path.
"""

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from changelogmanager.cli import main

_CHANGELOG = """\
# Changelog

## [Unreleased]
### Added
- New feature

## [1.0.0] - 2022-03-14
### Fixed
- Fixed some bug
"""


class _Result:
    def __init__(self, exit_code, stdout, stderr):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.output = stdout + stderr


def run_cli(arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            exit_code = main(arguments)
        except SystemExit as exc:  # lint-message delegates via SystemExit
            exit_code = exc.code if isinstance(exc.code, int) else 1
    return _Result(exit_code, stdout.getvalue(), stderr.getvalue())


def _write_project(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text(_CHANGELOG, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
    )


def test_release_bump_dry_run_reports_branch_and_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)

    result = run_cli(
        [
            "--json",
            "release-bump",
            "--version",
            "v1.1.0",
            "--base",
            "main",
            "--release-id",
            "42",
            "--dry-run",
        ]
    )

    assert result.exit_code == 0
    assert '"version": "1.1.0"' in result.stdout
    assert '"branch": "release/bump-42"' in result.stdout
    assert '"committed": false' in result.stdout


def test_release_bump_dry_run_defaults_branch_to_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)

    result = run_cli(["--json", "release-bump", "--version", "2.0.0", "--dry-run"])

    assert result.exit_code == 0
    assert '"branch": "release/bump-2.0.0"' in result.stdout


def test_release_bump_help_mentions_ci_helper():
    result = run_cli(["release-bump", "--help"])

    assert result.exit_code == 0
    assert "--open-pr" in result.stdout
    assert "--release-id" in result.stdout


def test_lint_message_accepts_valid_subject(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat: add a thing\n", encoding="utf-8")

    result = run_cli(["lint-message", "--schema", "conventional", str(msg)])

    assert result.exit_code == 0


def test_lint_message_rejects_unclassifiable_subject(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("garbage nonsense line\n", encoding="utf-8")

    result = run_cli(["lint-message", "--schema", "conventional", str(msg)])

    # Exit code 1 is the lint-failure contract (the diagnostic is written to the
    # process stderr fd by the llvm formatter, not the redirected buffer).
    assert result.exit_code == 1


# ----------------------------------------------------------------------
# release-rollback
# ----------------------------------------------------------------------


def _init_repo_with_tag(tmp_path: Path, tag: str) -> None:
    import subprocess  # noqa: PLC0415

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init")
    git("config", "user.email", "t@t.co")
    git("config", "user.name", "t")
    (tmp_path / "f").write_text("x", encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "init")
    git("tag", tag)


def _tag_exists(tmp_path: Path, tag: str) -> bool:
    import subprocess  # noqa: PLC0415

    out = subprocess.run(
        ["git", "tag", "--list", tag], cwd=tmp_path, capture_output=True, text=True
    )
    return tag in out.stdout.split()


def test_release_rollback_dry_run_touches_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _init_repo_with_tag(tmp_path, "v5.2.0")

    result = run_cli(
        [
            "--json",
            "release-rollback",
            "--tag",
            "v5.2.0",
            "--no-github",
            "--no-remote-tag",
            "--dry-run",
        ]
    )

    assert result.exit_code == 0
    assert '"tag": "v5.2.0"' in result.stdout
    # Dry-run must not actually delete the local tag.
    assert _tag_exists(tmp_path, "v5.2.0")


def test_release_rollback_dry_run_never_calls_github(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    _init_repo_with_tag(tmp_path, "v5.2.0")
    # Dry-run must not construct a GitHub client or require a token, even when
    # release deletion is enabled.
    mocker.patch(
        "changelogmanager.github.GitHub",
        side_effect=AssertionError("GitHub client should not be created in dry-run"),
    )

    result = run_cli(
        [
            "--json",
            "release-rollback",
            "--tag",
            "v5.2.0",
            "--repository",
            "owner/repo",
            "--dry-run",
        ]
    )

    assert result.exit_code == 0
    assert '"release_deleted": true' in result.stdout
    assert _tag_exists(tmp_path, "v5.2.0")


def test_release_rollback_deletes_local_tag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _init_repo_with_tag(tmp_path, "v5.2.0")

    result = run_cli(
        [
            "--json",
            "release-rollback",
            "--tag",
            "v5.2.0",
            "--no-github",
            "--no-remote-tag",
            "--yes",
        ]
    )

    assert result.exit_code == 0
    assert '"local_tag_deleted": true' in result.stdout
    assert not _tag_exists(tmp_path, "v5.2.0")


def test_release_rollback_refuses_without_yes_when_noninteractive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _init_repo_with_tag(tmp_path, "v5.2.0")

    # --json forces non-interactive; without --yes the deletion must be refused.
    result = run_cli(
        ["--json", "release-rollback", "--tag", "v5.2.0", "--no-github", "--no-remote-tag"]
    )

    assert result.exit_code == 1
    assert _tag_exists(tmp_path, "v5.2.0")


def test_release_rollback_deletes_github_release(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    _init_repo_with_tag(tmp_path, "v5.2.0")

    fake = mocker.MagicMock()
    fake.find_release_by_tag.return_value = {"id": 123, "tag_name": "v5.2.0"}
    mocker.patch("changelogmanager.github.GitHub", return_value=fake)

    result = run_cli(
        [
            "--json",
            "release-rollback",
            "--tag",
            "v5.2.0",
            "--repository",
            "owner/repo",
            "--github-token",
            "token",
            "--no-remote-tag",
            "--yes",
        ]
    )

    assert result.exit_code == 0
    assert '"release_deleted": true' in result.stdout
    fake.delete_release.assert_called_once_with({"id": 123, "tag_name": "v5.2.0"})


def test_release_rollback_reports_missing_github_release(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    _init_repo_with_tag(tmp_path, "v5.2.0")

    fake = mocker.MagicMock()
    fake.find_release_by_tag.return_value = None
    mocker.patch("changelogmanager.github.GitHub", return_value=fake)

    result = run_cli(
        [
            "--json",
            "release-rollback",
            "--tag",
            "v5.2.0",
            "--repository",
            "owner/repo",
            "--github-token",
            "token",
            "--no-remote-tag",
            "--yes",
        ]
    )

    assert result.exit_code == 0
    assert '"release_missing": true' in result.stdout
    fake.delete_release.assert_not_called()
