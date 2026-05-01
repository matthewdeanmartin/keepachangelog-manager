import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from changelogmanager.cli import main

CHANGELOG_CONTENT = """\
# Changelog

## [Unreleased]
### Added
- New feature

### Changed
- Changed another feature

## [1.0.0] - 2022-03-14
### Removed
- Removed deprecated API call

### Fixed
- Fixed some bug

## [0.9.4] - 2022-03-13
### Deprecated
- Deprecated public API call
"""


class CliResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.output = stdout + stderr


def write_changelog(path: Path) -> None:
    """Creates a representative changelog fixture for CLI tests."""

    path.write_text(CHANGELOG_CONTENT, encoding="UTF-8")


def run_cli(arguments: list[str]) -> CliResult:
    """Runs the CLI and captures stdout/stderr."""

    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = main(arguments)

    return CliResult(
        exit_code=exit_code, stdout=stdout.getvalue(), stderr=stderr.getvalue()
    )


def test_top_level_help_lists_commands():
    """Top-level help should be rendered by argparse."""

    result = run_cli(["--help"])

    assert result.exit_code == 0
    assert "usage: changelogmanager" in result.stdout
    assert "config" in result.stdout
    assert "skill" in result.stdout
    assert "github-release" in result.stdout


def test_invalid_reference_returns_parser_error():
    """Invalid enum values should fail during parsing."""

    result = run_cli(["version", "--reference", "invalid"])

    assert result.exit_code == 2
    assert "invalid choice" in result.stderr


def test_create_dry_run_does_not_write_file(tmp_path, monkeypatch):
    """Dry-run create should not create a changelog file."""

    monkeypatch.chdir(tmp_path)
    changelog_path = Path("CHANGELOG.md")
    result = run_cli(["create", "--dry-run"])

    assert result.exit_code == 0
    assert "Dry run: would create CHANGELOG.md" in result.stdout
    assert not changelog_path.exists()


def test_config_show_uses_built_in_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = run_cli(["config"])

    assert result.exit_code == 0
    assert "Config source: built-in defaults" in result.stdout
    assert "style: conventional" in result.stdout
    assert "scheme: semver" in result.stdout


def test_config_show_reports_auto_detected_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".changelogmanager.yml"
    config_path.write_text(
        "project:\n"
        "  components:\n"
        "    - name: default\n"
        "      changelog: CHANGELOG.md\n"
        "  commits:\n"
        "    style: gitmoji\n",
        encoding="utf-8",
    )

    result = run_cli(["config"])

    assert result.exit_code == 0
    assert f"Config source: auto-detected ({config_path})" in result.stdout
    assert "style: gitmoji" in result.stdout


def test_config_init_writes_pyproject_by_default(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    mocker.patch(
        "changelogmanager.cli.inquirer.prompt",
        return_value={
            "config_format": "pyproject.toml",
            "commit_style": "Conventional Commits",
            "versioning_scheme": "PEP 440",
            "enforce_preamble": "Yes",
            "component_name": "default",
            "changelog_path": "CHANGELOG.md",
        },
    )

    result = run_cli(["config", "init"])

    assert result.exit_code == 0
    pyproject = (tmp_path / "pyproject.toml").read_text(encoding="UTF-8")
    assert "[tool.changelogmanager]" in pyproject
    assert 'scheme = "pep440"' in pyproject
    assert 'style = "conventional"' in pyproject
    assert "Wrote config: pyproject.toml" in result.stdout


def test_config_init_updates_existing_yaml_on_second_run(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".changelogmanager.yml"
    config_path.write_text(
        "project:\n"
        "  components:\n"
        "    - name: default\n"
        "      changelog: CHANGELOG.md\n"
        "  commits:\n"
        "    style: conventional\n"
        "  versioning:\n"
        "    scheme: semver\n",
        encoding="utf-8",
    )
    mocker.patch(
        "changelogmanager.cli.inquirer.prompt",
        return_value={
            "config_format": "YAML",
            "commit_style": "Gitmoji",
            "versioning_scheme": "Calendar Versioning",
            "enforce_preamble": "No",
            "component_name": "default",
            "changelog_path": "docs/CHANGELOG.md",
        },
    )

    result = run_cli(["config", "init"])

    assert result.exit_code == 0
    text = config_path.read_text(encoding="UTF-8")
    assert "style: gitmoji" in text
    assert "scheme: calver" in text
    assert "changelog: docs/CHANGELOG.md" in text
    assert f"Updated config: {config_path}" in result.stdout


def test_skill_export_writes_bundled_skill_to_requested_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    export_root = tmp_path / "exports"

    result = run_cli(["skill", "export", "--path", str(export_root)])

    assert result.exit_code == 0
    skill_file = export_root / "keepachangelog-manager-cli" / "SKILL.md"
    assert skill_file.exists()
    assert "keepachangelog-manager CLI" in skill_file.read_text(encoding="UTF-8")
    assert f"Exported skill: {skill_file.parent}" in result.stdout


def test_skill_export_prompts_for_common_location_when_path_missing(
    tmp_path, monkeypatch, mocker
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    mocker.patch(
        "changelogmanager.cli.inquirer.prompt",
        side_effect=[
            {
                "location": f"GitHub Copilot project ({tmp_path / '.github' / 'skills'})"
            }
        ],
    )

    result = run_cli(["skill", "export"])

    assert result.exit_code == 0
    assert (
        tmp_path
        / ".github"
        / "skills"
        / "keepachangelog-manager-cli"
        / "SKILL.md"
    ).exists()


def test_add_dry_run_does_not_modify_file(tmp_path, monkeypatch):
    """Dry-run add should leave the changelog untouched."""

    monkeypatch.chdir(tmp_path)
    changelog_path = Path("CHANGELOG.md")
    write_changelog(changelog_path)
    original = changelog_path.read_text(encoding="UTF-8")

    result = run_cli(
        [
            "--input-file",
            str(changelog_path),
            "add",
            "--change-type",
            "added",
            "--message",
            "Smoke test entry",
            "--dry-run",
        ]
    )

    assert result.exit_code == 0
    assert "Dry run: would update CHANGELOG.md" in result.stdout
    assert changelog_path.read_text(encoding="UTF-8") == original


def test_add_without_arguments_uses_prompt_answers(tmp_path, monkeypatch, mocker):
    """Interactive add should still work when argparse leaves fields unset."""

    monkeypatch.chdir(tmp_path)
    changelog_path = Path("CHANGELOG.md")
    write_changelog(changelog_path)
    mocker.patch(
        "changelogmanager.cli.inquirer.prompt",
        return_value={
            "change_type": "fixed",
            "message": "Prompted entry",
            "confirm": "Yes",
        },
    )

    result = run_cli(["--input-file", str(changelog_path), "add"])

    assert result.exit_code == 0
    assert "- Prompted entry" in changelog_path.read_text(encoding="UTF-8")


def test_release_dry_run_does_not_modify_file(tmp_path, monkeypatch):
    """Dry-run release should leave the changelog untouched."""

    monkeypatch.chdir(tmp_path)
    changelog_path = Path("CHANGELOG.md")
    write_changelog(changelog_path)
    original = changelog_path.read_text(encoding="UTF-8")

    result = run_cli(
        [
            "--input-file",
            str(changelog_path),
            "release",
            "--override-version",
            "v1.1.0",
            "--dry-run",
        ]
    )

    assert result.exit_code == 0
    assert "Dry run: would release CHANGELOG.md" in result.stdout
    assert changelog_path.read_text(encoding="UTF-8") == original


def test_to_json_dry_run_does_not_write_output_file(tmp_path, monkeypatch):
    """Dry-run to-json should not create an output file."""

    monkeypatch.chdir(tmp_path)
    changelog_path = Path("CHANGELOG.md")
    output_path = Path("CHANGELOG.json")
    write_changelog(changelog_path)

    result = run_cli(
        [
            "--input-file",
            str(changelog_path),
            "to-json",
            "--file-name",
            str(output_path),
            "--dry-run",
        ]
    )

    assert result.exit_code == 0
    assert "Dry run: would write JSON output to CHANGELOG.json" in result.stdout
    assert not output_path.exists()


def test_github_release_dry_run_skips_github_calls(tmp_path, monkeypatch, mocker):
    """Dry-run github-release should not instantiate the GitHub client."""

    monkeypatch.chdir(tmp_path)
    mocker.patch(
        "changelogmanager.cli.GitHub",
        side_effect=AssertionError("GitHub client should not be created in dry-run"),
    )
    changelog_path = Path("CHANGELOG.md")
    write_changelog(changelog_path)

    result = run_cli(
        [
            "--input-file",
            str(changelog_path),
            "github-release",
            "--repository",
            "example/repo",
            "--github-token",
            "token",
            "--release",
            "--dry-run",
        ]
    )

    assert result.exit_code == 0
    assert (
        "Dry run: would create or update published GitHub release v1.1.0 in example/repo"
        in result.stdout
    )


def test_read_only_commands_accept_dry_run(tmp_path, monkeypatch):
    """Read-only commands should accept dry-run without changing behavior."""

    monkeypatch.chdir(tmp_path)
    changelog_path = Path("CHANGELOG.md")
    config_path = Path("config.yml")
    component_changelog_path = Path("service") / "CHANGELOG.md"
    component_changelog_path.parent.mkdir()
    write_changelog(changelog_path)
    write_changelog(component_changelog_path)
    config_path.write_text(
        """\
project:
  components:
    - name: Service Component
      changelog: service/CHANGELOG.md
""",
        encoding="UTF-8",
    )

    version_result = run_cli(
        [
            "--input-file",
            str(changelog_path),
            "version",
            "--reference",
            "future",
            "--dry-run",
        ]
    )
    validate_result = run_cli(
        ["--input-file", str(changelog_path), "validate", "--dry-run"]
    )
    component_result = run_cli(
        [
            "--config",
            str(config_path),
            "--component",
            "Service Component",
            "version",
            "--dry-run",
        ]
    )

    assert version_result.exit_code == 0
    assert "1.1.0" in version_result.stdout
    assert validate_result.exit_code == 0
    assert component_result.exit_code == 0
    assert "1.0.0" in component_result.stdout
