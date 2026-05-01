from pathlib import Path

from click.testing import CliRunner

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


def write_changelog(path: Path) -> None:
    """Creates a representative changelog fixture for CLI tests."""

    path.write_text(CHANGELOG_CONTENT, encoding="UTF-8")


def test_create_dry_run_does_not_write_file():
    """Dry-run create should not create a changelog file."""

    runner = CliRunner()

    with runner.isolated_filesystem():
        changelog_path = Path("CHANGELOG.md")
        result = runner.invoke(main, ["create", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run: would create CHANGELOG.md" in result.output
        assert not changelog_path.exists()


def test_add_dry_run_does_not_modify_file():
    """Dry-run add should leave the changelog untouched."""

    runner = CliRunner()

    with runner.isolated_filesystem():
        changelog_path = Path("CHANGELOG.md")
        write_changelog(changelog_path)
        original = changelog_path.read_text(encoding="UTF-8")

        result = runner.invoke(
            main,
            [
                "--input-file",
                str(changelog_path),
                "add",
                "--change-type",
                "added",
                "--message",
                "Smoke test entry",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Dry run: would update CHANGELOG.md" in result.output
        assert changelog_path.read_text(encoding="UTF-8") == original


def test_release_dry_run_does_not_modify_file():
    """Dry-run release should leave the changelog untouched."""

    runner = CliRunner()

    with runner.isolated_filesystem():
        changelog_path = Path("CHANGELOG.md")
        write_changelog(changelog_path)
        original = changelog_path.read_text(encoding="UTF-8")

        result = runner.invoke(
            main,
            [
                "--input-file",
                str(changelog_path),
                "release",
                "--override-version",
                "v1.1.0",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Dry run: would release CHANGELOG.md" in result.output
        assert changelog_path.read_text(encoding="UTF-8") == original


def test_to_json_dry_run_does_not_write_output_file():
    """Dry-run to-json should not create an output file."""

    runner = CliRunner()

    with runner.isolated_filesystem():
        changelog_path = Path("CHANGELOG.md")
        output_path = Path("CHANGELOG.json")
        write_changelog(changelog_path)

        result = runner.invoke(
            main,
            [
                "--input-file",
                str(changelog_path),
                "to-json",
                "--file-name",
                str(output_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Dry run: would write JSON output to CHANGELOG.json" in result.output
        assert not output_path.exists()


def test_github_release_dry_run_skips_github_calls(mocker):
    """Dry-run github-release should not instantiate the GitHub client."""

    runner = CliRunner()
    mocker.patch(
        "changelogmanager.cli.GitHub",
        side_effect=AssertionError("GitHub client should not be created in dry-run"),
    )

    with runner.isolated_filesystem():
        changelog_path = Path("CHANGELOG.md")
        write_changelog(changelog_path)

        result = runner.invoke(
            main,
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
            ],
        )

        assert result.exit_code == 0
        assert (
            "Dry run: would create or update published GitHub release v1.1.0 in example/repo"
            in result.output
        )


def test_read_only_commands_accept_dry_run():
    """Read-only commands should accept dry-run without changing behavior."""

    runner = CliRunner()

    with runner.isolated_filesystem():
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

        version_result = runner.invoke(
            main,
            [
                "--input-file",
                str(changelog_path),
                "version",
                "--reference",
                "future",
                "--dry-run",
            ],
        )
        validate_result = runner.invoke(
            main,
            ["--input-file", str(changelog_path), "validate", "--dry-run"],
        )
        component_result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "--component",
                "Service Component",
                "version",
                "--dry-run",
            ],
        )

        assert version_result.exit_code == 0
        assert "1.1.0" in version_result.output
        assert validate_result.exit_code == 0
        assert component_result.exit_code == 0
        assert "1.0.0" in component_result.output
