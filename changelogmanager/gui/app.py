# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Top-level GUI controller: menu bar, screen switching, and status bar."""

from __future__ import annotations

import tkinter as tk
from functools import partial
from tkinter import filedialog, messagebox, simpledialog, ttk

from changelogmanager.config import (
    add_component_to_config,
    default_config_path_for_format,
    get_component_from_config,
    get_component_tasks_file,
    get_components_from_config,
)
from changelogmanager.gui.screens.backfill import BackfillScreen
from changelogmanager.gui.screens.base import Screen
from changelogmanager.gui.screens.components import ComponentsScreen
from changelogmanager.gui.screens.config_window import open_config_window
from changelogmanager.gui.screens.edit import EditScreen
from changelogmanager.gui.screens.fragments_screen import FragmentsScreen
from changelogmanager.gui.screens.lint_screen import LintScreen
from changelogmanager.gui.screens.releases import ReleasesScreen
from changelogmanager.gui.screens.tasks_screen import TasksScreen
from changelogmanager.gui.screens.tools_screen import ToolsScreen
from changelogmanager.gui.state import AppState, running_in_ci
from changelogmanager.gui.widgets import StatusBar, add_tooltip
from changelogmanager.runtime_logging import get_logger
from changelogmanager.tasks import default_task_file_name

logger = get_logger(__name__)

SCREEN_CLASSES: tuple[type[Screen], ...] = (
    EditScreen,
    TasksScreen,
    FragmentsScreen,
    BackfillScreen,
    LintScreen,
    ReleasesScreen,
    ComponentsScreen,
    ToolsScreen,
)


class AppController:  # pylint: disable=too-many-instance-attributes
    """Owns the root window and orchestrates screens and shared state."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Changelog Manager")
        self.root.geometry("1180x780")

        self.state = AppState()

        # Shared input controls (also exposed via the File menu).
        self.input_file_var = tk.StringVar(value=self.state.input_file)
        self.config_var = tk.StringVar(value=self.state.config_path or "")
        self.component_var = tk.StringVar(value=self.state.component)
        self.error_format_var = tk.StringVar(value=self.state.error_format)
        self.dry_run_var = tk.BooleanVar(value=self.state.dry_run)
        # Primary tasks file, prefilled with the file that would be used right now
        # (no more "blank = auto"). The Tasks screen reads this shared var.
        self.tasks_file_var = tk.StringVar(value=default_task_file_name())

        self.screens: dict[str, Screen] = {}
        self.current: Screen | None = None

        self.build_menu()
        self.build_top_panel()

        self.container = ttk.Frame(self.root)
        self.container.pack(fill=tk.BOTH, expand=True)

        self.status_bar = StatusBar(self.root)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        for screen_class in SCREEN_CLASSES:
            screen = screen_class(self.container, self)
            self.screens[screen_class.title] = screen

        self.show_screen(EditScreen.title)
        mode = "CI" if running_in_ci() else "local"
        self.set_status(
            f"Loaded {self.state.input_file}"
            + (f" — {self.state.load_error}" if self.state.load_error else "")
            + f" ({mode} mode)"
        )

    # ------------------------------------------------------------------
    # Menu / top panel
    # ------------------------------------------------------------------
    def build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open changelog…", command=self.browse_input_file)
        file_menu.add_command(label="Open config…", command=self.browse_config_file)
        file_menu.add_command(label="Reload", command=self.reload)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        screens_menu = tk.Menu(menubar, tearoff=0)
        for screen_class in SCREEN_CLASSES:
            screens_menu.add_command(
                label=screen_class.title,
                command=partial(self.show_screen, screen_class.title),
            )
        menubar.add_cascade(label="Screens", menu=screens_menu)

        config_menu = tk.Menu(menubar, tearoff=0)
        config_menu.add_command(label="Settings…", command=self.open_config)
        menubar.add_cascade(label="Config", menu=config_menu)

        self.root.config(menu=menubar)

    def build_top_panel(self) -> None:
        top = ttk.LabelFrame(self.root, text="Workspace")
        top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=6)

        row = ttk.Frame(top)
        row.pack(fill=tk.X, padx=4, pady=2)
        # The changelog file picker is grouped so it can be hidden on screens
        # that don't operate on a workspace changelog (Tasks, Fragments, etc.).
        self.changelog_picker = ttk.Frame(row)
        self.changelog_picker.pack(side=tk.LEFT)
        ttk.Label(self.changelog_picker, text="Changelog:").pack(side=tk.LEFT)
        ttk.Entry(
            self.changelog_picker, textvariable=self.input_file_var, width=38
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            self.changelog_picker, text="Browse…", command=self.browse_input_file
        ).pack(side=tk.LEFT)

        # Primary tasks file picker — occupies the same slot as the changelog
        # picker but is shown only on screens that work on TASKS.md (Tasks).
        self.tasks_file_picker = ttk.Frame(row)
        tasks_label = ttk.Label(self.tasks_file_picker, text="Tasks file:")
        tasks_label.pack(side=tk.LEFT)
        add_tooltip(
            tasks_label,
            "The primary TASKS.md this workspace acts on (prefilled with the "
            "first existing of TASKS.md, .changelogmanager/TASKS.md).",
        )
        ttk.Entry(
            self.tasks_file_picker, textvariable=self.tasks_file_var, width=38
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            self.tasks_file_picker, text="Browse…", command=self.browse_tasks_file
        ).pack(side=tk.LEFT)

        self._config_label = ttk.Label(row, text="Config:")
        self._config_label.pack(side=tk.LEFT, padx=(12, 0))
        ttk.Entry(row, textvariable=self.config_var, width=26).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(row, text="Browse…", command=self.browse_config_file).pack(
            side=tk.LEFT
        )

        row2 = ttk.Frame(top)
        row2.pack(fill=tk.X, padx=4, pady=2)
        component_label = ttk.Label(row2, text="Component:")
        component_label.pack(side=tk.LEFT)
        add_tooltip(
            component_label,
            "Which configured component (sub-project) to act on. Components map "
            "names to separate CHANGELOG.md files in config; 'default' is the "
            "top-level changelog. Pick one from the dropdown or add a new one.",
        )
        # Editable combobox: lists configured component names but still allows a
        # free-typed name (e.g. when no config file exists yet).
        self.component_combo = ttk.Combobox(
            row2, textvariable=self.component_var, width=16, values=()
        )
        self.component_combo.pack(side=tk.LEFT, padx=4)
        self.component_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self.on_component_selected()
        )
        new_component_button = ttk.Button(
            row2, text="New…", width=6, command=self.add_component
        )
        new_component_button.pack(side=tk.LEFT)
        add_tooltip(
            new_component_button,
            "Add a new component (name + changelog file) to the config file and "
            "select it.",
        )
        self.refresh_component_choices()
        error_format_label = ttk.Label(row2, text="Error format:")
        error_format_label.pack(side=tk.LEFT, padx=(12, 0))
        add_tooltip(
            error_format_label,
            "How diagnostics are printed: 'llvm' for human-readable file:line "
            "messages, 'github' for GitHub Actions inline annotations.",
        )
        ttk.Combobox(
            row2,
            textvariable=self.error_format_var,
            values=["llvm", "github"],
            width=8,
            state="readonly",
        ).pack(side=tk.LEFT, padx=4)
        dry_run_check = ttk.Checkbutton(row2, text="Dry run", variable=self.dry_run_var)
        dry_run_check.pack(side=tk.LEFT, padx=12)
        add_tooltip(
            dry_run_check,
            "Preview destructive actions (release, backfill, promote) without "
            "writing files or calling GitHub/GitLab.",
        )
        ttk.Button(row2, text="Reload", command=self.reload).pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    # State sync
    # ------------------------------------------------------------------
    def sync_state_from_vars(self) -> None:
        """Pushes the shared top-panel controls into AppState."""

        self.state.input_file = self.input_file_var.get().strip() or "CHANGELOG.md"
        self.state.config_path = self.config_var.get().strip() or None
        self.state.component = self.component_var.get().strip() or "default"
        self.state.error_format = self.error_format_var.get() or "llvm"
        self.state.dry_run = bool(self.dry_run_var.get())

    def reload(self) -> None:
        """Re-reads the changelog from disk and refreshes the active screen."""

        self.sync_state_from_vars()
        self.state.reload()
        if getattr(self, "component_combo", None) is not None:
            self.refresh_component_choices()
        if self.state.load_error:
            self.set_status(f"{self.state.input_file}: {self.state.load_error}")
        else:
            self.set_status(f"Reloaded {self.state.input_file}")
        if self.current is not None:
            self.current.on_show()

    # ------------------------------------------------------------------
    # Screen switching
    # ------------------------------------------------------------------
    def show_screen(self, title: str) -> None:
        """Brings the named screen to the front."""

        screen = self.screens[title]
        if self.current is screen:
            screen.on_show()
            return
        if self.current is not None:
            self.current.pack_forget()
        screen.pack(fill=tk.BOTH, expand=True)
        self.current = screen
        self._apply_picker_visibility(screen)
        logger.info("Switched to screen %s", title)
        screen.on_show()

    def _apply_picker_visibility(self, screen: Screen) -> None:
        """Show the primary-file picker that applies to the current screen.

        The Changelog and Tasks-file pickers share the same top-panel slot; at
        most one is shown. A screen opts into the tasks picker with
        ``uses_tasks_file = True``; otherwise the changelog picker is shown for
        screens with ``uses_changelog = True``.
        """

        changelog_picker = getattr(self, "changelog_picker", None)
        tasks_picker = getattr(self, "tasks_file_picker", None)
        if changelog_picker is None or tasks_picker is None:
            return

        wants_tasks = getattr(screen, "uses_tasks_file", False)
        wants_changelog = getattr(screen, "uses_changelog", True) and not wants_tasks

        changelog_picker.pack_forget()
        tasks_picker.pack_forget()
        if wants_changelog:
            changelog_picker.pack(side=tk.LEFT, before=self._config_label)
        elif wants_tasks:
            tasks_picker.pack(side=tk.LEFT, before=self._config_label)

    def set_status(self, message: str) -> None:
        """Updates the bottom status bar."""

        self.status_bar.set(message)

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------
    def browse_input_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select changelog file",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        )
        if path:
            self.input_file_var.set(path)
            self.reload()

    def browse_tasks_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select tasks file",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        )
        if path:
            self.tasks_file_var.set(path)
            if self.current is not None:
                self.current.on_show()

    def browse_config_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select config file",
            filetypes=[
                ("TOML", "*.toml"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.config_var.set(path)
            self.reload()

    def open_config(self) -> None:
        self.sync_state_from_vars()
        open_config_window(self)

    # ------------------------------------------------------------------
    # Component dropdown
    # ------------------------------------------------------------------
    def configured_component_names(self) -> list[str]:
        """Returns component names declared in the current config (may be empty)."""

        config_path = self.config_var.get().strip() or self.state.config_path
        if not config_path:
            return []
        try:
            components = get_components_from_config(config_path)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("Could not list components: %s", exc)
            return []
        return [str(c.get("name")) for c in components if c.get("name")]

    def refresh_component_choices(self) -> None:
        """Repopulates the component dropdown from config, preserving the value."""

        names = self.configured_component_names()
        current = self.component_var.get().strip()
        if current and current not in names:
            names = [*names, current]
        self.component_combo.configure(values=tuple(names))

    def on_component_selected(self) -> None:
        """Point the Changelog and Tasks-file pickers at the selected component."""

        self.sync_state_from_vars()
        config_path = self.config_var.get().strip() or self.state.config_path
        name = self.component_var.get().strip()
        if not config_path or not name:
            return
        try:
            component = get_component_from_config(config_path, name)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.set_status(f"Component {name}: {exc}")
            return
        changelog = str(component.get("changelog") or "").strip()
        if changelog:
            self.input_file_var.set(changelog)
        # Per-component tasks file; fall back to the resolved default so the
        # Tasks-file picker is never left pointing at the previous component.
        tasks_file = get_component_tasks_file(config_path, name)
        self.tasks_file_var.set(tasks_file or default_task_file_name())
        self.reload()

    def add_component(self) -> None:
        """Prompts for a new component and writes it into the config file."""

        config_path = self.config_var.get().strip() or self.state.config_path
        if not config_path:
            # No config yet: offer to create the default standalone config.
            if not messagebox.askyesno(
                "No config file",
                "No config file is selected. Create 'changelogmanager.toml' "
                "to hold the new component?",
            ):
                return
            config_path = default_config_path_for_format("toml")

        name = simpledialog.askstring(
            "New component", "Component name:", parent=self.root
        )
        if not name or not name.strip():
            return
        changelog = simpledialog.askstring(
            "New component",
            f"Changelog file for '{name.strip()}':",
            parent=self.root,
            initialvalue="CHANGELOG.md",
        )
        if not changelog or not changelog.strip():
            return
        # Optional per-component tasks file. Blank = the component inherits the
        # global [tasks].file / default discovery, so an empty answer is fine.
        tasks_file = simpledialog.askstring(
            "New component",
            f"Tasks file for '{name.strip()}' (optional, blank = default):",
            parent=self.root,
            initialvalue="",
        )
        tasks_file = (tasks_file or "").strip() or None

        try:
            add_component_to_config(
                config_path,
                name.strip(),
                changelog.strip(),
                tasks_file=tasks_file,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            messagebox.showerror(
                "Add component failed", str(getattr(exc, "message", exc))
            )
            return

        self.config_var.set(config_path)
        self.component_var.set(name.strip())
        self.input_file_var.set(changelog.strip())
        if tasks_file:
            self.tasks_file_var.set(tasks_file)
        self.refresh_component_choices()
        self.reload()
        self.set_status(f"Added component '{name.strip()}' to {config_path}")
