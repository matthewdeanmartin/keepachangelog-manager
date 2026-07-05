# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Unit tests for the GUI layer (non-display logic only).

Strategy: create a hidden Tk root (``root.withdraw()``) so Tkinter is fully
initialised without showing a window. Subcommand logic, state management, and
CLI-runner utilities are tested through their public Python APIs; no mouse /
keyboard events are simulated.

Covered modules:
* ``changelogmanager.gui.state`` -- AppState, running_in_ci
* ``changelogmanager.gui.cli_runner`` -- run_cli (success, failure, SystemExit)
* ``changelogmanager.gui.widgets`` -- StatusBar, CommandList, ScrollableFrame
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Skip the entire module when Tkinter is unavailable (headless Linux CI
# without Xvfb, missing Tcl/Tk installation, etc.) so the suite degrades
# gracefully.
# ---------------------------------------------------------------------------
tk_available = True
try:
    _root_probe = tk.Tk()
    _root_probe.destroy()
except Exception:  # pylint: disable=broad-exception-caught
    tk_available = False

pytestmark = pytest.mark.skipif(
    not tk_available, reason="tkinter not available / no display"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def root():
    """A hidden Tk root for the duration of one test."""
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not usable in this environment: {exc}")
    r.withdraw()
    yield r
    import contextlib

    with contextlib.suppress(tk.TclError):
        r.destroy()


# ---------------------------------------------------------------------------
# running_in_ci
# ---------------------------------------------------------------------------


def test_running_in_ci_false_when_no_env_vars(monkeypatch):
    from changelogmanager.gui.state import CI_ENV_VARS, running_in_ci

    for var in CI_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    assert running_in_ci() is False


def test_running_in_ci_true_when_ci_set(monkeypatch):
    from changelogmanager.gui.state import running_in_ci

    monkeypatch.setenv("CI", "1")
    assert running_in_ci() is True


def test_running_in_ci_true_when_github_actions(monkeypatch):
    from changelogmanager.gui.state import CI_ENV_VARS, running_in_ci

    for var in CI_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert running_in_ci() is True


# ---------------------------------------------------------------------------
# AppState -- construction and reload
# ---------------------------------------------------------------------------


def test_appstate_defaults(tmp_path, monkeypatch):
    from changelogmanager.gui.state import AppState

    monkeypatch.chdir(tmp_path)
    # Patch auto_detect_config to return None so we don't need a pyproject.toml.
    with (
        patch("changelogmanager.gui.state.auto_detect_config", return_value=None),
        patch("changelogmanager.gui.state.running_in_ci", return_value=False),
    ):
        state = AppState()

    assert state.input_file == "CHANGELOG.md"
    assert state.component == "default"
    assert state.error_format == "llvm"
    assert state.dry_run is True  # not in CI -> default to dry-run


def test_appstate_loads_existing_changelog(tmp_path, monkeypatch):
    from changelogmanager.gui.state import AppState

    monkeypatch.chdir(tmp_path)
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- First entry\n",
        encoding="UTF-8",
    )
    with patch("changelogmanager.gui.state.auto_detect_config", return_value=None):
        state = AppState()

    assert state.changelog is not None
    assert state.load_error is None


def test_appstate_missing_changelog_sets_load_error(tmp_path, monkeypatch):
    from changelogmanager.gui.state import AppState

    monkeypatch.chdir(tmp_path)
    with patch("changelogmanager.gui.state.auto_detect_config", return_value=None):
        state = AppState()

    # CHANGELOG.md does not exist; state should record a load error.
    assert state.load_error is not None
    # But changelog object is still created (empty model).
    assert state.changelog is not None


def test_appstate_invalid_changelog_yields_no_model(tmp_path, monkeypatch):
    """A file that exists but fails to parse must NOT produce a live model.

    Regression test: an empty Changelog bound to the real path let GUI
    save/validate/release overwrite the user's changelog with a bare header.
    """

    from changelogmanager.gui.state import AppState

    monkeypatch.chdir(tmp_path)
    original = (
        "# Changelog\n\n## [Unreleased]\n\n### Added\n\n"
        "- Top-level entry\n- 1. a numbered list entry (invalid)\n"
    )
    (tmp_path / "CHANGELOG.md").write_text(original, encoding="UTF-8")
    with patch("changelogmanager.gui.state.auto_detect_config", return_value=None):
        state = AppState()

    assert state.changelog is None
    assert state.load_error is not None
    # The error must include the individual diagnostics, not just a count.
    assert "Numbered lists are not permitted" in state.load_error
    # And nothing may have touched the file.
    assert (tmp_path / "CHANGELOG.md").read_text(encoding="UTF-8") == original


def test_appstate_reload_called_again(tmp_path, monkeypatch):
    from changelogmanager.gui.state import AppState

    monkeypatch.chdir(tmp_path)
    notified = []
    with patch("changelogmanager.gui.state.auto_detect_config", return_value=None):
        state = AppState()
    state.add_listener(lambda: notified.append(1))
    state.reload()
    assert notified == [1]


def test_appstate_raw_text_returns_empty_for_missing(tmp_path, monkeypatch):
    from changelogmanager.gui.state import AppState

    monkeypatch.chdir(tmp_path)
    with patch("changelogmanager.gui.state.auto_detect_config", return_value=None):
        state = AppState()
    assert state.raw_text() == ""


def test_appstate_raw_text_returns_content(tmp_path, monkeypatch):
    from changelogmanager.gui.state import AppState

    monkeypatch.chdir(tmp_path)
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# Changelog\n", encoding="UTF-8")
    with patch("changelogmanager.gui.state.auto_detect_config", return_value=None):
        state = AppState()
    assert "Changelog" in state.raw_text()


def test_appstate_notify_calls_all_listeners(tmp_path, monkeypatch):
    from changelogmanager.gui.state import AppState

    monkeypatch.chdir(tmp_path)
    calls: list[str] = []
    with patch("changelogmanager.gui.state.auto_detect_config", return_value=None):
        state = AppState()
    state.add_listener(lambda: calls.append("a"))
    state.add_listener(lambda: calls.append("b"))
    state.notify()
    assert calls == ["a", "b"]


# ---------------------------------------------------------------------------
# run_cli
# ---------------------------------------------------------------------------


def test_run_cli_help_exits_zero(tmp_path, monkeypatch):
    from changelogmanager.gui.cli_runner import run_cli

    monkeypatch.chdir(tmp_path)
    code, output = run_cli(["--help"])
    assert code == 0
    assert output  # some help text


def test_run_cli_captures_stdout(tmp_path, monkeypatch):
    from changelogmanager.gui.cli_runner import run_cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n", encoding="UTF-8"
    )
    code, output = run_cli(["--input-file", "CHANGELOG.md", "validate"])
    # validate exits 0 on a minimal valid changelog.
    assert code == 0


def test_run_cli_unknown_command_nonzero(tmp_path, monkeypatch):
    from changelogmanager.gui.cli_runner import run_cli

    monkeypatch.chdir(tmp_path)
    code, _output = run_cli(["this-command-does-not-exist"])
    assert code != 0


def test_run_cli_exception_in_handler_returns_1(monkeypatch):
    """An exception raised inside the CLI handler is caught and returns exit 1."""
    from changelogmanager.gui import cli_runner

    def exploding_main(_argv):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_runner, "cli_main", exploding_main)
    code, output = cli_runner.run_cli(["anything"])
    assert code == 1
    assert "boom" in output  # traceback captured to output


# ---------------------------------------------------------------------------
# StatusBar widget
# ---------------------------------------------------------------------------


def test_status_bar_initial_text(root):
    from changelogmanager.gui.widgets import StatusBar

    bar = StatusBar(root)
    assert bar.var.get() == "Ready"


def test_status_bar_set_updates_var(root):
    from changelogmanager.gui.widgets import StatusBar

    bar = StatusBar(root)
    bar.set("All systems go")
    assert bar.var.get() == "All systems go"


def test_status_bar_set_overwrites_previous(root):
    from changelogmanager.gui.widgets import StatusBar

    bar = StatusBar(root)
    bar.set("First")
    bar.set("Second")
    assert bar.var.get() == "Second"


# ---------------------------------------------------------------------------
# CommandList widget
# ---------------------------------------------------------------------------


def test_command_list_add_returns_button(root):
    from changelogmanager.gui.widgets import CommandList

    cl = CommandList(root, title="Actions")
    called = []
    btn = cl.add("Do it", lambda: called.append(True))
    assert isinstance(btn, tk.ttk.Button)
    btn.invoke()
    assert called == [True]


def test_command_list_multiple_buttons(root):
    from changelogmanager.gui.widgets import CommandList

    cl = CommandList(root)
    results: list[str] = []
    cl.add("A", lambda: results.append("A"))
    cl.add("B", lambda: results.append("B"))
    children = cl.winfo_children()
    assert len(children) == 2


# ---------------------------------------------------------------------------
# ScrollableFrame widget
# ---------------------------------------------------------------------------


def test_scrollable_frame_body_is_frame(root):
    from changelogmanager.gui.widgets import ScrollableFrame

    sf = ScrollableFrame(root)
    assert isinstance(sf.body, tk.ttk.Frame)


def test_scrollable_frame_clear_removes_children(root):
    from changelogmanager.gui.widgets import ScrollableFrame

    sf = ScrollableFrame(root)
    # Add some children to the body.
    tk.Label(sf.body, text="x").pack()
    tk.Label(sf.body, text="y").pack()
    sf.update_idletasks()
    sf.clear()
    sf.update_idletasks()
    assert sf.body.winfo_children() == []


# ---------------------------------------------------------------------------
# Tooltip -- basic construction
# ---------------------------------------------------------------------------


def test_tooltip_attaches_without_error(root):
    from changelogmanager.gui.widgets import Tooltip, add_tooltip

    label = tk.Label(root, text="hover me")
    label.pack()
    tip = add_tooltip(label, "A helpful hint")
    assert isinstance(tip, Tooltip)
    # No show/hide events driven here -- just verify the binding was created.
    assert tip.text == "A helpful hint"


def test_tooltip_empty_text_does_not_crash(root):
    from changelogmanager.gui.widgets import add_tooltip

    label = tk.Label(root, text="x")
    label.pack()
    tip = add_tooltip(label, "")
    # Manually trigger _show; it should no-op on empty text.
    tip._show()  # pylint: disable=protected-access
    assert tip._tip is None  # pylint: disable=protected-access
