import argparse
import io
from contextlib import redirect_stderr
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

import changelogmanager.gui as gui_package
from changelogmanager.gui.app import SCREEN_CLASSES, AppController
from changelogmanager.gui.screens.backfill import BackfillScreen
from changelogmanager.gui.screens.components import ComponentsScreen
from changelogmanager.gui.screens.edit import EditScreen
from changelogmanager.gui.screens.fragments_screen import FragmentsScreen
from changelogmanager.gui.screens.lint_screen import LintScreen
from changelogmanager.gui.screens.releases import ReleasesScreen
from changelogmanager.gui.screens.tasks_screen import TasksScreen
from changelogmanager.gui.screens.tools_screen import ToolsScreen
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
    assert any("api → api/CHANGELOG.md" in text for text in labels)
    assert any("web → web/CHANGELOG.md" in text for text in labels)

    screen.validate_all()

    output = screen.output.get("1.0", tk.END)
    assert f"--config {config_path}" in output
    assert "validate --all" in output
    assert "[exit 0]" in output


def test_selecting_component_updates_tasks_file_picker(gui_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "changelogmanager.toml").write_text(
        '[[components]]\nname = "default"\nchangelog = "CHANGELOG.md"\n\n'
        '[[components]]\nname = "api"\nchangelog = "api/CHANGELOG.md"\n'
        'tasks_file = "api/TASKS.md"\n',
        encoding="utf-8",
    )
    write_changelog(tmp_path / "CHANGELOG.md")
    write_changelog(tmp_path / "api" / "CHANGELOG.md")

    controller = AppController(gui_root)
    controller.config_var.set("changelogmanager.toml")
    controller.sync_state_from_vars()

    screen = controller.screens[ComponentsScreen.title]
    controller.show_screen(ComponentsScreen.title)
    screen.select_component("api")

    # The active component's changelog and tasks file drive the workspace pickers.
    assert controller.input_file_var.get() == "api/CHANGELOG.md"
    assert controller.tasks_file_var.get() == "api/TASKS.md"

    # A component without a tasks_file falls back to the resolved default.
    screen.select_component("default")
    assert controller.tasks_file_var.get().endswith("TASKS.md")
    assert controller.tasks_file_var.get() != "api/TASKS.md"


def test_new_screens_are_registered():
    titles = {cls.title for cls in SCREEN_CLASSES}
    assert {"Tasks", "Fragments", "Commit Lint", "Tools / Export"} <= titles


def _capture_argv(monkeypatch, module):
    """Patches ``run_cli`` in a screen module and records the argv it is given."""

    calls: list[list[str]] = []

    def fake_run_cli(argv):
        calls.append(list(argv))
        return 0, "ok"

    monkeypatch.setattr(module, "run_cli", fake_run_cli)
    return calls


def test_tasks_screen_promote_dry_run_argv(gui_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_changelog(tmp_path / "CHANGELOG.md")
    import changelogmanager.gui.screens.tasks_screen as mod

    controller = AppController(gui_root)
    controller.dry_run_var.set(True)
    controller.sync_state_from_vars()
    screen = controller.screens[TasksScreen.title]

    calls = _capture_argv(monkeypatch, mod)
    screen.promote()

    promote_calls = [c for c in calls if "promote" in c]
    assert promote_calls, calls
    argv = promote_calls[0]
    assert argv[-2:] == ["tasks", "promote"] or "promote" in argv
    assert "--dry-run" in argv


def test_tasks_screen_add_argv(gui_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_changelog(tmp_path / "CHANGELOG.md")
    import changelogmanager.gui.screens.tasks_screen as mod

    controller = AppController(gui_root)
    screen = controller.screens[TasksScreen.title]
    calls = _capture_argv(monkeypatch, mod)

    screen.add_type_var.set("fixed")
    screen.add_message_var.set("A new task")
    screen.add_task()

    add_calls = [c for c in calls if "add" in c]
    assert add_calls, calls
    argv = add_calls[0]
    # The add type/message are passed positionally, in order.
    idx = argv.index("add")
    assert argv[idx : idx + 3] == ["add", "fixed", "A new task"]
    # The tasks file is now always populated (prefilled to the resolved default),
    # so it is forwarded as an explicit --tasks-file rather than left blank.
    assert "--tasks-file" in argv
    assert argv[argv.index("--tasks-file") + 1].endswith("TASKS.md")


def test_fragments_screen_collect_argv(gui_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_changelog(tmp_path / "CHANGELOG.md")
    import changelogmanager.gui.screens.fragments_screen as mod

    controller = AppController(gui_root)
    controller.dry_run_var.set(True)
    controller.sync_state_from_vars()
    screen = controller.screens[FragmentsScreen.title]
    calls = _capture_argv(monkeypatch, mod)

    screen.consume_var.set("delete")
    screen.collect()

    collect_calls = [c for c in calls if "collect" in c]
    assert collect_calls, calls
    argv = collect_calls[0]
    assert "fragments" in argv and "collect" in argv
    assert argv[argv.index("--consume") + 1] == "delete"
    assert "--dry-run" in argv


def test_lint_screen_lint_and_rewrite_argv(gui_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_changelog(tmp_path / "CHANGELOG.md")
    import changelogmanager.gui.screens.lint_screen as mod

    controller = AppController(gui_root)
    screen = controller.screens[LintScreen.title]
    calls = _capture_argv(monkeypatch, mod)

    screen.all_history_var.set(True)
    screen.strict_var.set(True)
    screen.schema_var.set("conventional")
    screen.lint_commits()

    argv = calls[-1]
    assert argv[0:1] != []  # has at least an --error-format prefix
    assert "lint-commits" in argv
    assert "--all-history" in argv
    assert "--strict" in argv
    assert argv[argv.index("--commit-schema") + 1] == "conventional"

    screen.auto_prefix_var.set("changed")
    screen.plan_rewrites()
    argv = calls[-1]
    assert "rewrite-messages" in argv
    assert argv[argv.index("--auto-prefix") + 1] == "changed"


def test_tools_screen_version_and_export_argv(gui_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_changelog(tmp_path / "CHANGELOG.md")
    import changelogmanager.gui.screens.tools_screen as mod

    controller = AppController(gui_root)
    controller.dry_run_var.set(True)
    controller.sync_state_from_vars()
    screen = controller.screens[ToolsScreen.title]
    calls = _capture_argv(monkeypatch, mod)

    screen.reference_var.set("future")
    screen.get_version()
    assert calls[-1][-2:] == ["version", "--reference"] or "future" in calls[-1]
    assert "future" in calls[-1]

    screen.export_json()
    argv = calls[-1]
    assert "to-json" in argv
    assert "--dry-run" in argv

    screen.check_credentials()
    assert calls[-1][-2:] == ["credentials", "check"]


def test_releases_screen_hides_irrelevant_fields(gui_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_changelog(tmp_path / "CHANGELOG.md")

    controller = AppController(gui_root)
    screen = controller.screens[ReleasesScreen.title]

    screen.select("gitlab-release")
    gui_root.update_idletasks()
    # GitHub repo/token/PR rows are hidden; GitLab project/token rows shown.
    visible = {row.winfo_manager() != "" for _tags, row in screen.field_rows}
    shown_for_gitlab = [
        bool(row.winfo_manager())
        for tags, row in screen.field_rows
        if "gitlab-release" in tags
    ]
    hidden_for_gitlab = [
        bool(row.winfo_manager())
        for tags, row in screen.field_rows
        if "gitlab-release" not in tags
    ]
    assert all(shown_for_gitlab)
    assert not any(hidden_for_gitlab)
    assert True in visible

    screen.select("github-pr")
    gui_root.update_idletasks()
    # [skip ci] does not apply to the PR command.
    assert not screen.skip_ci_row.winfo_manager()


def test_releases_screen_skip_ci_default_from_config(gui_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_changelog(tmp_path / "CHANGELOG.md")
    (tmp_path / "changelogmanager.toml").write_text(
        '[[components]]\nname = "default"\nchangelog = "CHANGELOG.md"\n\n'
        "[defaults]\nskip_ci = false\n",
        encoding="utf-8",
    )
    controller = AppController(gui_root)
    controller.config_var.set("changelogmanager.toml")
    controller.sync_state_from_vars()
    # Rebuild the releases screen so it re-reads config for the default.
    screen = ReleasesScreen(controller.container, controller)
    assert screen.skip_ci_var.get() is False


def test_changelog_picker_hidden_on_commit_lint(gui_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_changelog(tmp_path / "CHANGELOG.md")

    controller = AppController(gui_root)
    controller.show_screen(ReleasesScreen.title)
    gui_root.update_idletasks()
    assert controller.changelog_picker.winfo_manager()  # shown where it applies

    controller.show_screen(LintScreen.title)
    gui_root.update_idletasks()
    assert not controller.changelog_picker.winfo_manager()  # hidden on Commit Lint

    controller.show_screen(ReleasesScreen.title)
    gui_root.update_idletasks()
    assert controller.changelog_picker.winfo_manager()  # shown again


def test_tasks_file_picker_prefilled_and_swaps_with_changelog(
    gui_root, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    write_changelog(tmp_path / "CHANGELOG.md")

    controller = AppController(gui_root)
    # The tasks file is prefilled with the resolved default (no "blank = auto").
    assert controller.tasks_file_var.get().endswith("TASKS.md")
    # The Tasks screen shares the controller's tasks-file var.
    screen = controller.screens[TasksScreen.title]
    assert screen.tasks_file_var is controller.tasks_file_var

    # On the Tasks screen the top panel shows the Tasks-file picker, not the
    # Changelog picker; they share the same slot.
    controller.show_screen(TasksScreen.title)
    gui_root.update_idletasks()
    assert controller.tasks_file_picker.winfo_manager()
    assert not controller.changelog_picker.winfo_manager()

    # Back on a changelog screen the Changelog picker returns.
    controller.show_screen(EditScreen.title)
    gui_root.update_idletasks()
    assert controller.changelog_picker.winfo_manager()
    assert not controller.tasks_file_picker.winfo_manager()


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
