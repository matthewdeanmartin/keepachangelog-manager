# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Config knobs: [versioning].initial_version and [defaults].skip_ci."""

from __future__ import annotations

import json
from pathlib import Path

from changelogmanager import cli
from changelogmanager.changelog import Changelog
from changelogmanager.config import get_initial_version, get_skip_ci

EMPTY_CHANGELOG = """\
# Changelog

## [Unreleased]
### Added
- First ever feature
"""


def test_default_initial_version_is_unchanged():
    cl = Changelog(file_path="CHANGELOG.md", changelog={"unreleased": {}})
    # No override: classic 0.0.1 for the first release.
    assert str(cl.suggest_future_version()) == "0.0.1"


def test_initial_version_override_applies():
    cl = Changelog(
        file_path="CHANGELOG.md",
        changelog={"unreleased": {}},
        initial_version="0.1.0",
    )
    assert str(cl.suggest_future_version()) == "0.1.0"


def test_invalid_initial_version_falls_back():
    cl = Changelog(
        file_path="CHANGELOG.md",
        changelog={"unreleased": {}},
        initial_version="not-a-version",
    )
    assert str(cl.suggest_future_version()) == "0.0.1"


def test_get_initial_version_reads_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "changelogmanager.toml"
    config.write_text(
        '[versioning]\nscheme = "semver"\ninitial_version = "0.1.0"\n',
        encoding="UTF-8",
    )
    assert get_initial_version(str(config)) == "0.1.0"


def test_get_initial_version_absent_is_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert get_initial_version(None) is None


def test_get_skip_ci_default_true_and_configurable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert get_skip_ci(None) is True
    config = tmp_path / "changelogmanager.toml"
    config.write_text("[defaults]\nskip_ci = false\n", encoding="UTF-8")
    assert get_skip_ci(str(config)) is False


def _github_pr_title(capsys, monkeypatch, *extra_args):
    """Runs `github-pr --dry-run --json` and returns the resolved PR title."""

    monkeypatch.setenv("GITHUB_TOKEN", "x")
    Path("CHANGELOG.md").write_text(EMPTY_CHANGELOG, encoding="UTF-8")
    argv = [
        "--json",
        "github-pr",
        "--repository",
        "owner/repo",
        "--head",
        "release/bump-1",
        "--base",
        "main",
        "--title",
        "chore: release 1.2.0",
        "--dry-run",
        *extra_args,
    ]
    assert cli.main(argv) == 0
    payload = json.loads(capsys.readouterr().out)
    return payload["title"]


def test_github_pr_title_appends_skip_ci_by_default(tmp_path, monkeypatch, capsys):
    # Default config => skip_ci True => [skip ci] appended to conserve CI minutes.
    monkeypatch.chdir(tmp_path)
    assert _github_pr_title(capsys, monkeypatch) == "chore: release 1.2.0 [skip ci]"


def test_github_pr_no_skip_ci_flag_overrides(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    title = _github_pr_title(capsys, monkeypatch, "--no-skip-ci")
    assert title == "chore: release 1.2.0"


def test_github_pr_title_follows_config_false(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    Path("changelogmanager.toml").write_text(
        '[[components]]\nname = "default"\nchangelog = "CHANGELOG.md"\n\n'
        "[defaults]\nskip_ci = false\n",
        encoding="UTF-8",
    )
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    Path("CHANGELOG.md").write_text(EMPTY_CHANGELOG, encoding="UTF-8")
    assert (
        cli.main(
            [
                "--json",
                "--config",
                "changelogmanager.toml",
                "github-pr",
                "--repository",
                "owner/repo",
                "--head",
                "h",
                "--base",
                "main",
                "--title",
                "chore: release 1.2.0",
                "--dry-run",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["title"] == "chore: release 1.2.0"


def test_github_pr_skip_ci_is_idempotent(tmp_path, monkeypatch, capsys):
    # An explicit title already carrying the tag isn't double-tagged.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    Path("CHANGELOG.md").write_text(EMPTY_CHANGELOG, encoding="UTF-8")
    assert (
        cli.main(
            [
                "--json",
                "github-pr",
                "--repository",
                "owner/repo",
                "--head",
                "h",
                "--base",
                "main",
                "--title",
                "chore: release 1.2.0 [skip ci]",
                "--skip-ci",
                "--dry-run",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["title"] == "chore: release 1.2.0 [skip ci]"


def test_version_future_honors_initial_version_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("CHANGELOG.md").write_text(EMPTY_CHANGELOG, encoding="UTF-8")
    Path("changelogmanager.toml").write_text(
        '[[components]]\nname = "default"\nchangelog = "CHANGELOG.md"\n\n'
        '[versioning]\nscheme = "semver"\ninitial_version = "0.1.0"\n',
        encoding="UTF-8",
    )
    # The future reference should propose the configured initial version.
    assert (
        cli.main(
            ["--config", "changelogmanager.toml", "version", "--reference", "future"]
        )
        == 0
    )
