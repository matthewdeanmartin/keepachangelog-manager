import argparse
import io
from contextlib import redirect_stderr
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

import changelogmanager.gui as gui_package
from changelogmanager.gui.app import AppController
from changelogmanager.gui.screens.backfill import BackfillScreen
from changelogmanager.gui.screens.components import ComponentsScreen
from changelogmanager.gui.screens.releases import ReleasesScreen
from changelogmanager.gui.state import AppState

VALID_CHANGELOG = """\
# Changelog

## [Unreleased]
### Added
- First feature

## [1.0.0] - 2024-01-01
### Added
- Initial release
"""


@pytest.fixture
def gui_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    try:
        yield root
    finally:
        root.update_idletasks()
        root.destroy()


def write_changelog(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(VALID_CHANGELOG, encoding="utf-8")


def test_app_state_reload_handles_missing_and_present_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("CI", "GITHUB_ACTIONS", "GITLAB_CI"):
        monkeypatch.delenv(name, raising=False)

    state = AppState()

    assert state.load_error == "CHANGELOG.md does not exist yet"
    assert state.raw_text() == ""
    assert state.dry_run is True

    write_changelog(tmp_path / "CHANGELOG.md")
    notifications: list[str | None] = []
    state.add_listener(lambda: notifications.append(state.load_error))

    state.reload()

    assert state.load_error is None
    assert state.changelog is not None
    assert state.raw_text().startswith("# Changelog")
    assert notifications == [None]


def test_app_controller_builds_hidden_gui_and_switches_screens(
    gui_root, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    write_changelog(tmp_path / "CHANGELOG.md")

    controller = AppController(gui_root)

    assert controller.current is controller.screens["Edit"]
    assert controller.state.load_error is None

    controller.show_screen(BackfillScreen.title)
    assert controller.current is controller.screens[BackfillScreen.title]

    controller.show_screen(ReleasesScreen.title)
    assert controller.current is controller.screens[ReleasesScreen.title]


def test_backfill_screen_create_dry_run_does_not_write_file(
    gui_root, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    write_changelog(tmp_path / "CHANGELOG.md")
    target = tmp_path / "NEW_CHANGELOG.md"

    controller = AppController(gui_root)
    controller.input_file_var.set(str(target))
    controller.dry_run_var.set(True)
    controller.sync_state_from_vars()

    screen = controller.screens[BackfillScreen.title]
    screen.create()

    output = screen.output.get("1.0", tk.END)
    assert "Dry run: would create" in output
    assert str(target) in output
    assert not target.exists()


def test_releases_screen_github_release_dry_run_redacts_token(
    gui_root, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    changelog_path = tmp_path / "CHANGELOG.md"
    original = VALID_CHANGELOG
    write_changelog(changelog_path)

    controller = AppController(gui_root)
    controller.dry_run_var.set(True)
    controller.sync_state_from_vars()

    screen = controller.screens[ReleasesScreen.title]
    screen.select("github-release")
    screen.repo_var.set("owner/repo")
    screen.token_var.set("super-secret-token")
    screen.run_selected()

    output = screen.output.get("1.0", tk.END)
    assert "--github-token ***" in output
    assert "super-secret-token" not in output
    assert "[exit 0]" in output
    assert changelog_path.read_text(encoding="utf-8") == original


def test_components_screen_validate_all_lists_components_and_runs(
    gui_root, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "changelogmanager.toml"
    config_path.write_text(
        "[[components]]\n"
        'name = "api"\n'
        'changelog = "api/CHANGELOG.md"\n'
        "\n"
        "[[components]]\n"
        'name = "web"\n'
        'changelog = "web/CHANGELOG.md"\n',
        encoding="utf-8",
    )
    write_changelog(tmp_path / "api" / "CHANGELOG.md")
    write_changelog(tmp_path / "web" / "CHANGELOG.md")
    write_changelog(tmp_path / "CHANGELOG.md")

    controller = AppController(gui_root)
    screen = controller.screens[ComponentsScreen.title]
    controller.show_screen(ComponentsScreen.title)

    labels = [child.cget("text") for child in screen.listing_body.winfo_children()]
    assert "• api → api/CHANGELOG.md" in labels
    assert "• web → web/CHANGELOG.md" in labels

    screen.validate_all()

    output = screen.output.get("1.0", tk.END)
    assert f"--config {config_path}" in output
    assert "validate --all" in output
    assert "[exit 0]" in output


def test_run_gui_reports_missing_tkinter_and_gui_subcommand_sets_handler(monkeypatch):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    gui_package.add_gui_subcommand(subparsers)

    args = parser.parse_args(["gui"])
    assert args.is_gui is True
    assert args.handler is gui_package.gui_handler

    monkeypatch.setattr(gui_package, "tk", None)
    monkeypatch.setattr(gui_package, "TK_IMPORT_ERROR", RuntimeError("no tk"))

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        exit_code = gui_package.run_gui()

    assert exit_code == 1
    assert "tkinter is not available" in stderr.getvalue()
