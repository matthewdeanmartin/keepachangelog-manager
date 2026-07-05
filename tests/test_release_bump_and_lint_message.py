"""Tests for the consolidated `release-bump` command and `lint-message` subcommand.

These cover the CLI wiring (arg parsing, dry-run rendering, exit codes) without
touching git or the network. The git-orchestration path of `release_bump` is
exercised separately via `services.release_bump` with a temp repo.
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
