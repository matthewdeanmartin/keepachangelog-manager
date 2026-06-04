# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Top-level GUI controller: menu bar, screen switching, and status bar."""

from __future__ import annotations

import tkinter as tk
from functools import partial
from tkinter import filedialog, ttk

from changelogmanager.gui.screens.backfill import BackfillScreen
from changelogmanager.gui.screens.base import Screen
from changelogmanager.gui.screens.components import ComponentsScreen
from changelogmanager.gui.screens.config_window import open_config_window
from changelogmanager.gui.screens.edit import EditScreen
from changelogmanager.gui.screens.releases import ReleasesScreen
from changelogmanager.gui.state import AppState, running_in_ci
from changelogmanager.gui.widgets import StatusBar
from changelogmanager.runtime_logging import get_logger

logger = get_logger(__name__)

SCREEN_CLASSES: tuple[type[Screen], ...] = (
    EditScreen,
    BackfillScreen,
    ReleasesScreen,
    ComponentsScreen,
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
        ttk.Label(row, text="Changelog:").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.input_file_var, width=38).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(row, text="Browse…", command=self.browse_input_file).pack(
            side=tk.LEFT
        )
        ttk.Label(row, text="Config:").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Entry(row, textvariable=self.config_var, width=26).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(row, text="Browse…", command=self.browse_config_file).pack(
            side=tk.LEFT
        )

        row2 = ttk.Frame(top)
        row2.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(row2, text="Component:").pack(side=tk.LEFT)
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
        logger.info("Switched to screen %s", title)
        screen.on_show()

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
