"""User workflows and failure recovery, always in isolated temporary projects."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import tomlkit

from changelogmanager.changelog import Changelog
from changelogmanager.cli import main
from changelogmanager.cli.loaders import load_changelog
from changelogmanager.config import get_effective_configuration, write_configuration
from changelogmanager.release_scope import release_scope
from changelogmanager.services import release_changelog
from changelogmanager.vendor.jiggle_version import update_pyproject_toml
from changelogmanager.versioning import parse_version


def project(root, scheme="pep440"):
    root.mkdir(exist_ok=True)
    config = root / "pyproject.toml"
    config.write_text(
        '[project] # package metadata\nname = "sample"\nversion = "1.0.0" # current\n'
        "\n[tool.changelogmanager.versioning] # keep this\n"
        f'scheme = "{scheme}"\ninitial_version = "0.1.0"\n'
        '[[tool.changelogmanager.components]] # ownership\nname = "plugin"\n'
        'changelog = "CHANGELOG.md"\nversion_files = ["pyproject.toml"] # explicit\n'
        'tag_template = "plugin-v{version}"\n',
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n### Fixed\n- Repair parsing.\n\n"
        "## [1.0.0] - 2026-01-01\n### Added\n- Initial.\n",
        encoding="utf-8",
    )
    return config


def test_config_save_preserves_comments_ownership_and_initial_version(tmp_path):
    config = project(tmp_path)
    settings = get_effective_configuration(str(config))
    settings["project"]["versioning"]["scheme"] = "semver"
    write_configuration(str(config), settings)
    text = config.read_text()
    assert all(
        comment in text
        for comment in (
            "# package metadata",
            "# keep this",
            "# ownership",
            "# explicit",
        )
    )
    parsed = tomlkit.parse(text)
    assert parsed["project"]["version"] == "1.0.0"
    assert (
        parsed["tool"]["changelogmanager"]["versioning"]["initial_version"] == "0.1.0"
    )
    scope = release_scope(str(config), "plugin")
    assert scope.version_files == (config,)
    assert scope.tag("2.0.0") == "plugin-v2.0.0"


@pytest.mark.parametrize(
    "header", ["[project] # comment", '["project"]', "[ project ]"]
)
def test_toml_version_update_preserves_comments_and_crlf(tmp_path, header):
    target = tmp_path / "pyproject.toml"
    before = f'{header}\r\nname = "demo"\r\nversion = "1.0.0" # release\r\n'
    target.write_bytes(before.encode())
    update_pyproject_toml(target, "1.1.0rc1")
    assert target.read_bytes() == before.replace('"1.0.0"', '"1.1.0rc1"').encode()


def test_failed_render_keeps_original_file(tmp_path, monkeypatch):
    config = project(tmp_path)
    changelog = load_changelog(str(config), "plugin", None)
    target = Path(changelog.get_file_path())
    original = target.read_bytes()
    monkeypatch.setattr(
        changelog, "render", Mock(side_effect=ValueError("formatter failure"))
    )
    with pytest.raises(ValueError, match="formatter failure"):
        changelog.write_to_file()
    assert target.read_bytes() == original


def test_failed_companion_update_restores_changelog_and_version(tmp_path, monkeypatch):
    from changelogmanager import version_bumper

    config = project(tmp_path)
    changelog = load_changelog(str(config), "plugin", None)
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    before_model = changelog.render()

    def fail_after_write(path, version):
        update_pyproject_toml(path, version)
        raise OSError("disk failure")

    monkeypatch.setattr(version_bumper, "update_pyproject_toml", fail_after_write)
    with pytest.raises(OSError, match="disk failure"):
        release_changelog(
            changelog,
            "1.1.0rc1",
            bump_versions=True,
            scope=release_scope(str(config), "plugin"),
        )
    assert all(p.read_bytes() == data for p, data in before.items())
    assert changelog.render() == before_model


def test_nested_batch_validation_checks_real_file_and_accepts_pep440(tmp_path):
    config = project(tmp_path / "nested")
    target = config.parent / "CHANGELOG.md"
    target.write_text(target.read_text().replace("1.0.0", "1.0.0rc1"))
    args = ["--config", str(config), "validate", "--all"]
    assert main(args) == 0
    target.write_text(target.read_text().replace("1.0.0rc1", "not-a-version"))
    assert main(args) == 1
    target.unlink()
    assert main(args) == 1
    assert main(["--input-file", str(target), "validate"]) == 1


def test_explicit_pep440_release_updates_files_but_bad_version_does_not(tmp_path):
    config = project(tmp_path)
    args = [
        "--config",
        str(config),
        "--component",
        "plugin",
        "release",
        "--bump-versions",
        "--yes",
        "--override-version",
    ]
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    assert main([*args, "not-a-version"]) == 1
    assert all(p.read_bytes() == data for p, data in before.items())
    assert main([*args, "1.1.0rc1"]) == 0
    assert tomlkit.parse(config.read_text())["project"]["version"] == "1.1.0rc1"
    assert "## [1.1.0rc1]" in (tmp_path / "CHANGELOG.md").read_text()


def test_semver_prerelease_precedence_and_metadata():
    versions = [
        "1.0.0-alpha",
        "1.0.0-alpha.2",
        "1.0.0-alpha.10",
        "1.0.0-beta",
        "1.0.0-rc.1",
        "1.0.0",
    ]
    assert sorted(map(parse_version, reversed(versions))) == list(
        map(parse_version, versions)
    )
    assert parse_version("1.0.0+build1") == parse_version("1.0.0+build2")


@pytest.mark.parametrize("saved", [True, False])
def test_gui_local_release_passes_selected_component(tmp_path, monkeypatch, saved):
    from changelogmanager.gui.screens.edit import EditScreen

    config = project(tmp_path)
    changelog = load_changelog(str(config), "plugin", None)
    runner = Mock(return_value=(0, ""))
    monkeypatch.setattr("changelogmanager.gui.cli_runner.run_cli", runner)
    screen = SimpleNamespace(
        require_changelog=lambda: changelog,
        save_document=Mock(return_value=saved),
        prompt_release_options=Mock(return_value=(True, False)),
        app_state=SimpleNamespace(
            config_path=str(config),
            component="plugin",
            error_format="llvm",
            input_file=str(tmp_path / "CHANGELOG.md"),
            dry_run=True,
        ),
        status=Mock(),
        controller=SimpleNamespace(reload=Mock()),
    )
    EditScreen.release(screen)
    screen.save_document.assert_called_once_with()
    if not saved:
        screen.prompt_release_options.assert_not_called()
        runner.assert_not_called()
        screen.controller.reload.assert_not_called()
        return
    argv = runner.call_args.args[0]
    assert argv[argv.index("--component") + 1] == "plugin"
    assert argv[argv.index("--input-file") + 1] == str(tmp_path / "CHANGELOG.md")
