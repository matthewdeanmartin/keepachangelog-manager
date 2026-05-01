# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Tkinter GUI surfacing the changelogmanager CLI features."""

from __future__ import annotations

import io
import os
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    _TK_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised only when tk is missing
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    filedialog = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    scrolledtext = None  # type: ignore[assignment]
    _TK_IMPORT_ERROR = exc

from changelogmanager.change_types import TYPES_OF_CHANGE
from changelogmanager.cli import VERSION_REFERENCES
from changelogmanager.cli import main as cli_main

HELP_TEXT: dict[str, str] = {
    "create": (
        "create\n\n"
        "Create a new (empty) CHANGELOG.md at the path given by\n"
        "'Input file'. Fails if the file already exists.\n\n"
        "Use '--dry-run' to preview without writing."
    ),
    "version": (
        "version\n\n"
        "Print a version derived from the changelog.\n\n"
        "  previous - the most recent released version\n"
        "  current  - the current top released version\n"
        "  future   - the suggested next version based on\n"
        "             entries currently in [Unreleased]\n\n"
        "Auto-runs with 'current' when this tab is activated."
    ),
    "validate": (
        "validate\n\n"
        "Validate the CHANGELOG.md for inconsistencies.\n"
        "Errors and warnings are reported using the chosen\n"
        "error format.\n\n"
        "Auto-runs when this tab is activated."
    ),
    "release": (
        "release\n\n"
        "Promote entries in [Unreleased] to a new version.\n"
        "Leave 'Override version' blank to auto-resolve based\n"
        "on change types.\n\n"
        "This modifies the file unless '--dry-run' is checked."
    ),
    "to-json": (
        "to-json\n\n"
        "Export the CHANGELOG.md to a JSON file (default\n"
        "CHANGELOG.json).\n\n"
        "Use '--dry-run' to render without writing."
    ),
    "add": (
        "add\n\n"
        "Add a new entry to [Unreleased]. Pick a change type\n"
        "and provide a message. Both are required from the\n"
        "GUI (no interactive prompting).\n\n"
        "This modifies the file unless '--dry-run' is checked."
    ),
    "github-release": (
        "github-release\n\n"
        "Delete existing draft GitHub releases and create a\n"
        "new one from the latest changelog entry.\n\n"
        "Repository (owner/repo) and a GitHub token are\n"
        "required. Defaults to draft state.\n\n"
        "DESTRUCTIVE: this calls the GitHub API. Prefer\n"
        "'--dry-run' first."
    ),
    "changelog": (
        "Changelog viewer\n\n"
        "Shows the contents of the file at 'Input file'.\n"
        "Click 'Reload' to refresh after edits."
    ),
}

# Commands that are safe to auto-run with their defaults when their tab activates.
AUTO_RUN_COMMANDS: frozenset[str] = frozenset({"version", "validate"})

# Order matters - drives both button order and tab order.
COMMANDS: tuple[str, ...] = (
    "create",
    "version",
    "validate",
    "release",
    "to-json",
    "add",
    "github-release",
)


def _run_cli(argv: list[str]) -> tuple[int, str]:
    """Invoke the CLI in-process, capturing stdout+stderr.

    Returns (exit_code, combined_output).
    """

    buffer = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(buffer):
        try:
            code = cli_main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
        except Exception:
            traceback.print_exc()
            code = 1
    return code, buffer.getvalue()


class ChangelogManagerGUI:
    """Top-level GUI controller."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Changelog Manager")
        self.root.geometry("1100x720")

        # Shared (top-panel) inputs
        self.input_file_var = tk.StringVar(value="CHANGELOG.md")
        self.config_var = tk.StringVar(value="")
        self.component_var = tk.StringVar(value="default")
        self.error_format_var = tk.StringVar(value="llvm")
        self.dry_run_var = tk.BooleanVar(value=False)

        # Per-command state
        self.version_ref_var = tk.StringVar(value="current")
        self.release_override_var = tk.StringVar(value="")
        self.to_json_file_var = tk.StringVar(value="CHANGELOG.json")
        self.add_type_var = tk.StringVar(value=TYPES_OF_CHANGE[0])
        self.add_message_var = tk.StringVar(value="")
        self.gh_repo_var = tk.StringVar(value="")
        self.gh_token_var = tk.StringVar(value=os.environ.get("GITHUB_TOKEN", ""))
        self.gh_draft_var = tk.BooleanVar(value=True)

        self._auto_run_done: set[str] = set()
        self._tab_frames: dict[str, ttk.Frame] = {}
        self._output_widgets: dict[str, scrolledtext.ScrolledText] = {}
        self._help_text_widget: tk.Text | None = None
        self._changelog_view: scrolledtext.ScrolledText | None = None
        self._current_command: str = COMMANDS[0]

        self._build_layout()
        self._show_help(self._current_command)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self._build_top_panel()

        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True)

        self._build_left_panel(body)
        self._build_center_panel(body)
        self._build_right_panel(body)

    def _build_top_panel(self) -> None:
        top = ttk.LabelFrame(self.root, text="Inputs")
        top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=6)

        row1 = ttk.Frame(top)
        row1.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(row1, text="Input file:").pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.input_file_var, width=40).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(row1, text="Browse…", command=self._browse_input_file).pack(
            side=tk.LEFT
        )
        ttk.Button(row1, text="Reload viewer", command=self._reload_changelog).pack(
            side=tk.LEFT, padx=8
        )

        row2 = ttk.Frame(top)
        row2.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(row2, text="Config:").pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.config_var, width=30).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(row2, text="Browse…", command=self._browse_config_file).pack(
            side=tk.LEFT
        )
        ttk.Label(row2, text="Component:").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Entry(row2, textvariable=self.component_var, width=16).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(row2, text="Error format:").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Combobox(
            row2,
            textvariable=self.error_format_var,
            values=["llvm", "github"],
            width=8,
            state="readonly",
        ).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(row2, text="Dry run", variable=self.dry_run_var).pack(
            side=tk.LEFT, padx=12
        )

    def _build_left_panel(self, parent: ttk.Frame) -> None:
        left = ttk.LabelFrame(parent, text="Commands")
        left.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)
        for command in COMMANDS:
            ttk.Button(
                left,
                text=command,
                width=18,
                command=lambda c=command: self._on_command_button(c),
            ).pack(padx=6, pady=3, anchor="w")

    def _build_center_panel(self, parent: ttk.Frame) -> None:
        center = ttk.Frame(parent)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=6)

        self.notebook = ttk.Notebook(center)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        for command in COMMANDS:
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=command)
            self._tab_frames[command] = frame
            self._build_command_tab(command, frame)

        # Changelog viewer tab
        cl_frame = ttk.Frame(self.notebook)
        self.notebook.add(cl_frame, text="changelog")
        self._tab_frames["changelog"] = cl_frame
        self._build_changelog_tab(cl_frame)

    def _build_command_tab(self, command: str, frame: ttk.Frame) -> None:
        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X, padx=6, pady=4)

        if command == "version":
            ttk.Label(controls, text="Reference:").pack(side=tk.LEFT)
            ttk.Combobox(
                controls,
                textvariable=self.version_ref_var,
                values=list(VERSION_REFERENCES),
                width=10,
                state="readonly",
            ).pack(side=tk.LEFT, padx=4)
        elif command == "release":
            ttk.Label(controls, text="Override version:").pack(side=tk.LEFT)
            ttk.Entry(controls, textvariable=self.release_override_var, width=20).pack(
                side=tk.LEFT, padx=4
            )
        elif command == "to-json":
            ttk.Label(controls, text="Output file:").pack(side=tk.LEFT)
            ttk.Entry(controls, textvariable=self.to_json_file_var, width=30).pack(
                side=tk.LEFT, padx=4
            )
        elif command == "add":
            ttk.Label(controls, text="Type:").pack(side=tk.LEFT)
            ttk.Combobox(
                controls,
                textvariable=self.add_type_var,
                values=TYPES_OF_CHANGE,
                width=12,
                state="readonly",
            ).pack(side=tk.LEFT, padx=4)
            ttk.Label(controls, text="Message:").pack(side=tk.LEFT, padx=(8, 0))
            ttk.Entry(controls, textvariable=self.add_message_var, width=50).pack(
                side=tk.LEFT, padx=4, fill=tk.X, expand=True
            )
        elif command == "github-release":
            ttk.Label(controls, text="Repo (owner/name):").pack(side=tk.LEFT)
            ttk.Entry(controls, textvariable=self.gh_repo_var, width=24).pack(
                side=tk.LEFT, padx=4
            )
            ttk.Label(controls, text="Token:").pack(side=tk.LEFT, padx=(8, 0))
            ttk.Entry(
                controls, textvariable=self.gh_token_var, width=24, show="*"
            ).pack(side=tk.LEFT, padx=4)
            ttk.Checkbutton(controls, text="Draft", variable=self.gh_draft_var).pack(
                side=tk.LEFT, padx=8
            )

        run_row = ttk.Frame(frame)
        run_row.pack(fill=tk.X, padx=6, pady=2)
        ttk.Button(
            run_row,
            text=f"Run {command}",
            command=lambda c=command: self._run_command(c),
        ).pack(side=tk.LEFT)
        ttk.Button(
            run_row,
            text="Clear output",
            command=lambda c=command: self._clear_output(c),
        ).pack(side=tk.LEFT, padx=6)

        output = scrolledtext.ScrolledText(frame, wrap=tk.WORD, height=20)
        output.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self._output_widgets[command] = output

    def _build_changelog_tab(self, frame: ttk.Frame) -> None:
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(toolbar, text="Reload", command=self._reload_changelog).pack(
            side=tk.LEFT
        )
        ttk.Label(toolbar, text="(read-only view of Input file)").pack(
            side=tk.LEFT, padx=8
        )

        self._changelog_view = scrolledtext.ScrolledText(frame, wrap=tk.WORD)
        self._changelog_view.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

    def _build_right_panel(self, parent: ttk.Frame) -> None:
        right = ttk.LabelFrame(parent, text="Help")
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=6, pady=6)
        self._help_text_widget = tk.Text(
            right, width=42, wrap=tk.WORD, state=tk.DISABLED
        )
        self._help_text_widget.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_command_button(self, command: str) -> None:
        self.notebook.select(self._tab_frames[command])

    def _on_tab_changed(self, _event: Any) -> None:
        tab_id = self.notebook.select()
        tab_text = self.notebook.tab(tab_id, "text")
        self._current_command = tab_text
        self._show_help(tab_text)

        if tab_text == "changelog":
            self._reload_changelog()
            return

        if tab_text in AUTO_RUN_COMMANDS and tab_text not in self._auto_run_done:
            self._auto_run_done.add(tab_text)
            self._run_command(tab_text)

    def _show_help(self, command: str) -> None:
        if self._help_text_widget is None:
            return
        text = HELP_TEXT.get(command, "")
        self._help_text_widget.configure(state=tk.NORMAL)
        self._help_text_widget.delete("1.0", tk.END)
        self._help_text_widget.insert("1.0", text)
        self._help_text_widget.configure(state=tk.DISABLED)

    def _browse_input_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select changelog file",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        )
        if path:
            self.input_file_var.set(path)
            self._reload_changelog()

    def _browse_config_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select config file",
            filetypes=[
                ("YAML", "*.yml *.yaml"),
                ("JSON", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.config_var.set(path)

    def _reload_changelog(self) -> None:
        if self._changelog_view is None:
            return
        path = self.input_file_var.get()
        self._changelog_view.delete("1.0", tk.END)
        try:
            with open(path, encoding="utf-8") as handle:
                self._changelog_view.insert("1.0", handle.read())
        except OSError as exc:
            self._changelog_view.insert("1.0", f"[unable to read {path}]\n{exc}\n")

    def _clear_output(self, command: str) -> None:
        widget = self._output_widgets.get(command)
        if widget is not None:
            widget.delete("1.0", tk.END)

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------
    def _build_argv(self, command: str) -> list[str] | None:
        argv: list[str] = []
        if self.config_var.get().strip():
            argv += ["--config", self.config_var.get().strip()]
        if self.component_var.get().strip():
            argv += ["--component", self.component_var.get().strip()]
        argv += ["--error-format", self.error_format_var.get() or "llvm"]
        if self.input_file_var.get().strip():
            argv += ["--input-file", self.input_file_var.get().strip()]

        argv.append(command)

        if command == "version":
            argv += ["--reference", self.version_ref_var.get() or "current"]
        elif command == "release":
            override = self.release_override_var.get().strip()
            if override:
                argv += ["--override-version", override]
        elif command == "to-json":
            file_name = self.to_json_file_var.get().strip() or "CHANGELOG.json"
            argv += ["--file-name", file_name]
        elif command == "add":
            message = self.add_message_var.get().strip()
            if not message:
                messagebox.showerror(
                    "Missing input",
                    "A message is required for the 'add' command.",
                )
                return None
            argv += [
                "--change-type",
                self.add_type_var.get() or TYPES_OF_CHANGE[0],
                "--message",
                message,
            ]
        elif command == "github-release":
            repo = self.gh_repo_var.get().strip()
            token = self.gh_token_var.get().strip()
            if not repo or not token:
                messagebox.showerror(
                    "Missing input",
                    "Repository and GitHub token are required for github-release.",
                )
                return None
            argv += ["--repository", repo, "--github-token", token]
            argv.append("--draft" if self.gh_draft_var.get() else "--release")

        if self.dry_run_var.get() and command != "version" and command != "validate":
            argv.append("--dry-run")

        return argv

    def _run_command(self, command: str) -> None:
        argv = self._build_argv(command)
        if argv is None:
            return

        widget = self._output_widgets[command]
        widget.insert(tk.END, f"$ changelogmanager {' '.join(argv)}\n")
        widget.see(tk.END)
        widget.update_idletasks()

        code, output = _run_cli(argv)
        widget.insert(tk.END, output)
        widget.insert(tk.END, f"\n[exit {code}]\n\n")
        widget.see(tk.END)

        # Refresh the viewer if a write may have occurred.
        if command in {"create", "release", "add"} and not self.dry_run_var.get():
            self._reload_changelog()


def run_gui() -> int:
    """Launch the Tkinter GUI. Returns a process exit code."""

    if _TK_IMPORT_ERROR is not None or tk is None:
        sys.stderr.write(
            "Error: tkinter is not available in this Python installation.\n"
            f"Details: {_TK_IMPORT_ERROR}\n"
            "Install a Python build that includes tkinter (e.g. on Debian/Ubuntu:\n"
            "  sudo apt-get install python3-tk\n"
            "on macOS with pyenv: install Python with tk support;\n"
            "on Windows: use the python.org installer with the 'tcl/tk' option).\n"
        )
        return 1

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        sys.stderr.write(
            "Error: failed to initialize a Tk display.\n"
            f"Details: {exc}\n"
            "If you are running in a headless environment, set up a display\n"
            "(e.g. Xvfb) or run the CLI commands directly.\n"
        )
        return 1

    ChangelogManagerGUI(root)
    root.mainloop()
    return 0


def add_gui_subcommand(subparsers: Any) -> None:
    """Register the 'gui' subcommand on an argparse subparsers object."""

    gui_parser = subparsers.add_parser("gui", help="Launch the Tkinter GUI")
    gui_parser.set_defaults(handler=_gui_handler, _is_gui=True)


def _gui_handler(_args: Any, _ctx: Any) -> None:
    """Argparse handler for the 'gui' subcommand."""

    # The handler is invoked via cli.main(), but we short-circuit before
    # changelog loading (see cli.main wiring) so this is only a fallback.
    sys.exit(run_gui())


# Allow running as `python -m changelogmanager.gui` for ad-hoc launches.
if __name__ == "__main__":  # pragma: no cover
    sys.exit(run_gui())
