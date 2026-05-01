"""Bug-hunting tests for CLI commands using real files (no mocking)."""

from pathlib import Path

import pytest

from changelogmanager.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_CHANGELOG = """\
# Changelog

## [Unreleased]
### Added
- New feature

## [1.0.0] - 2024-01-01
### Added
- Initial release
"""

RELEASED_ONLY = """\
# Changelog

## [1.0.0] - 2024-01-01
### Added
- Initial release
"""

EMPTY_UNRELEASED = """\
# Changelog

## [Unreleased]

## [1.0.0] - 2024-01-01
### Added
- Initial release
"""


def write_changelog(path: Path, content: str = VALID_CHANGELOG) -> str:
    p = path / "CHANGELOG.md"
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# create command
# ---------------------------------------------------------------------------

class TestCommandCreate:
    def test_create_makes_file(self, tmp_path):
        p = str(tmp_path / "CHANGELOG.md")
        rc = main(["--input-file", p, "create"])
        assert rc == 0
        assert Path(p).exists()

    def test_create_existing_file_returns_zero(self, tmp_path):
        p = write_changelog(tmp_path)
        rc = main(["--input-file", p, "create"])
        assert rc == 0

    def test_create_dry_run_does_not_create_file(self, tmp_path):
        p = str(tmp_path / "CHANGELOG.md")
        rc = main(["--input-file", p, "create", "--dry-run"])
        assert rc == 0
        assert not Path(p).exists()


# ---------------------------------------------------------------------------
# validate command
# ---------------------------------------------------------------------------

class TestCommandValidate:
    def test_validate_valid_file_returns_zero(self, tmp_path):
        p = write_changelog(tmp_path)
        rc = main(["--input-file", p, "validate"])
        assert rc == 0

    def test_validate_missing_file_returns_zero(self, tmp_path):
        p = str(tmp_path / "CHANGELOG.md")
        rc = main(["--input-file", p, "validate"])
        assert rc == 0

    def test_validate_invalid_file_returns_one(self, tmp_path):
        p = tmp_path / "CHANGELOG.md"
        p.write_text("## [bad-version]\n", encoding="utf-8")
        rc = main(["--input-file", str(p), "validate"])
        assert rc == 1

    def test_validate_github_error_format(self, tmp_path):
        p = write_changelog(tmp_path)
        rc = main(["--input-file", p, "-f", "github", "validate"])
        assert rc == 0


# ---------------------------------------------------------------------------
# version command
# ---------------------------------------------------------------------------

class TestCommandVersion:
    def test_version_current(self, tmp_path, capsys):
        p = write_changelog(tmp_path)
        rc = main(["--input-file", p, "version", "-r", "current"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "1.0.0" in out

    def test_version_future_with_unreleased_added(self, tmp_path, capsys):
        p = write_changelog(tmp_path)
        rc = main(["--input-file", p, "version", "-r", "future"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "1.1.0" in out

    def test_version_previous_returns_zero_when_not_enough(self, tmp_path):
        p = write_changelog(tmp_path, RELEASED_ONLY)
        rc = main(["--input-file", p, "version", "-r", "previous"])
        assert rc == 0

    def test_version_current_no_released_returns_zero(self, tmp_path):
        content = "# Changelog\n\n## [Unreleased]\n### Added\n- Thing\n"
        p = tmp_path / "CHANGELOG.md"
        p.write_text(content, encoding="utf-8")
        rc = main(["--input-file", str(p), "version", "-r", "current"])
        assert rc == 0

    def test_version_future_only_unreleased_returns_initial(self, tmp_path, capsys):
        content = "# Changelog\n\n## [Unreleased]\n### Fixed\n- A fix\n"
        p = tmp_path / "CHANGELOG.md"
        p.write_text(content, encoding="utf-8")
        rc = main(["--input-file", str(p), "version", "-r", "future"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "0.0.1" in out


# ---------------------------------------------------------------------------
# add command
# ---------------------------------------------------------------------------

class TestCommandAdd:
    def test_add_appends_to_unreleased(self, tmp_path):
        p = write_changelog(tmp_path, RELEASED_ONLY)
        rc = main(["--input-file", p, "add", "-t", "fixed", "-m", "A bug fix"])
        assert rc == 0
        text = Path(p).read_text(encoding="utf-8")
        assert "A bug fix" in text
        assert "[Unreleased]" in text

    def test_add_dry_run_does_not_modify(self, tmp_path):
        p = write_changelog(tmp_path, RELEASED_ONLY)
        original = Path(p).read_text(encoding="utf-8")
        rc = main(["--input-file", p, "add", "-t", "fixed", "-m", "dry change", "--dry-run"])
        assert rc == 0
        assert Path(p).read_text(encoding="utf-8") == original

    def test_add_all_change_types(self, tmp_path):
        for change_type in ["added", "changed", "deprecated", "removed", "fixed", "security"]:
            p = write_changelog(tmp_path, RELEASED_ONLY)
            rc = main(["--input-file", p, "add", "-t", change_type, "-m", f"A {change_type} entry"])
            assert rc == 0, f"Failed for change type: {change_type}"


# ---------------------------------------------------------------------------
# release command
# ---------------------------------------------------------------------------

class TestCommandRelease:
    def test_release_creates_new_version(self, tmp_path):
        p = write_changelog(tmp_path, VALID_CHANGELOG)
        rc = main(["--input-file", p, "release"])
        assert rc == 0
        text = Path(p).read_text(encoding="utf-8")
        assert "[Unreleased]" not in text
        assert "1.1.0" in text

    def test_release_with_override_version(self, tmp_path):
        p = write_changelog(tmp_path, VALID_CHANGELOG)
        rc = main(["--input-file", p, "release", "--override-version", "3.0.0"])
        assert rc == 0
        text = Path(p).read_text(encoding="utf-8")
        assert "3.0.0" in text

    def test_release_with_v_prefix_version(self, tmp_path):
        p = write_changelog(tmp_path, VALID_CHANGELOG)
        rc = main(["--input-file", p, "release", "--override-version", "v3.0.0"])
        assert rc == 0
        text = Path(p).read_text(encoding="utf-8")
        assert "3.0.0" in text

    def test_release_without_unreleased_returns_one(self, tmp_path):
        p = write_changelog(tmp_path, RELEASED_ONLY)
        rc = main(["--input-file", p, "release"])
        assert rc == 1

    def test_release_dry_run_does_not_modify(self, tmp_path):
        p = write_changelog(tmp_path, VALID_CHANGELOG)
        original = Path(p).read_text(encoding="utf-8")
        rc = main(["--input-file", p, "release", "--dry-run"])
        assert rc == 0
        assert Path(p).read_text(encoding="utf-8") == original

    def test_release_invalid_version_returns_one(self, tmp_path):
        p = write_changelog(tmp_path, VALID_CHANGELOG)
        rc = main(["--input-file", p, "release", "--override-version", "not-semver"])
        assert rc == 1

    def test_release_already_existing_version_returns_one(self, tmp_path):
        p = write_changelog(tmp_path, VALID_CHANGELOG)
        rc = main(["--input-file", p, "release", "--override-version", "1.0.0"])
        assert rc == 1

    def test_release_older_version_returns_one(self, tmp_path):
        p = write_changelog(tmp_path, VALID_CHANGELOG)
        rc = main(["--input-file", p, "release", "--override-version", "0.1.0"])
        assert rc == 1


# ---------------------------------------------------------------------------
# to-json command
# ---------------------------------------------------------------------------

class TestCommandToJson:
    def test_to_json_creates_file(self, tmp_path):
        p = write_changelog(tmp_path)
        out = str(tmp_path / "out.json")
        rc = main(["--input-file", p, "to-json", "--file-name", out])
        assert rc == 0
        assert Path(out).exists()

    def test_to_json_output_is_valid_json(self, tmp_path):
        import json as _json
        p = write_changelog(tmp_path)
        out = str(tmp_path / "changelog.json")
        main(["--input-file", p, "to-json", "--file-name", out])
        data = _json.loads(Path(out).read_text(encoding="utf-8"))
        assert isinstance(data, list)

    def test_to_json_dry_run_does_not_create_file(self, tmp_path):
        p = write_changelog(tmp_path)
        out = str(tmp_path / "should-not-exist.json")
        rc = main(["--input-file", p, "to-json", "--file-name", out, "--dry-run"])
        assert rc == 0
        assert not Path(out).exists()


# ---------------------------------------------------------------------------
# Error format flag
# ---------------------------------------------------------------------------

class TestErrorFormat:
    def test_github_error_format_on_invalid_file(self, tmp_path):
        p = tmp_path / "CHANGELOG.md"
        p.write_text("## [WRONG]\n", encoding="utf-8")
        rc = main(["--input-file", str(p), "-f", "github", "validate"])
        assert rc == 1

    def test_llvm_error_format_on_invalid_file(self, tmp_path):
        p = tmp_path / "CHANGELOG.md"
        p.write_text("## [WRONG]\n", encoding="utf-8")
        rc = main(["--input-file", str(p), "-f", "llvm", "validate"])
        assert rc == 1


# ---------------------------------------------------------------------------
# Config-driven multi-component
# ---------------------------------------------------------------------------

class TestConfigDrivenCLI:
    def test_config_selects_correct_changelog(self, tmp_path):
        changelog_path = tmp_path / "service.md"
        changelog_path.write_text(VALID_CHANGELOG, encoding="utf-8")

        config = tmp_path / "config.yml"
        config.write_text(
            "project:\n  components:\n    - name: mysvc\n      changelog: "
            + str(changelog_path).replace("\\", "/")
            + "\n",
            encoding="utf-8",
        )
        rc = main(["--config", str(config), "--component", "mysvc", "validate"])
        assert rc == 0

    def test_config_unknown_component_returns_one(self, tmp_path):
        config = tmp_path / "config.yml"
        config.write_text(
            "project:\n  components:\n    - name: real\n      changelog: CHANGELOG.md\n",
            encoding="utf-8",
        )
        rc = main(["--config", str(config), "--component", "nope", "validate"])
        assert rc == 1
