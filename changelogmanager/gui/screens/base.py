# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Base class for full-window screens managed by the AppController."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from changelogmanager.gui.state import AppState
from changelogmanager.gui.widgets import CommandList

if TYPE_CHECKING:  # pragma: no cover - typing only
    from changelogmanager.gui.app import AppController


class Screen(ttk.Frame):  # pylint: disable=too-many-ancestors
    """A screen owns a left command list and a central work area.

    Subclasses implement :meth:`build_body` to populate ``self.work_area`` and
    add buttons to ``self.commands``. :meth:`on_show` runs every time the screen
    becomes visible (e.g. to refresh from the shared model).
    """

    #: Title shown in the Screens menu and as the screen heading.
    title: str = "Screen"

    #: Whether this screen operates on the workspace changelog file. When False,
    #: the top-panel "Changelog" file picker is hidden (it doesn't apply here).
    uses_changelog: bool = True

    def __init__(self, parent: tk.Misc, controller: AppController) -> None:
        super().__init__(parent)
        self.controller = controller
        # Named app_state (not "state") to avoid shadowing tk.Widget.state().
        self.app_state: AppState = controller.state

        self.commands = CommandList(self)
        self.commands.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)

        self.work_area = ttk.Frame(self)
        self.work_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.build_body()

    # ------------------------------------------------------------------
    def build_body(self) -> None:
        """Populates ``self.commands`` and ``self.work_area``. Override."""

    def on_show(self) -> None:
        """Called whenever this screen is brought to the front. Override."""

    # ------------------------------------------------------------------
    def status(self, message: str) -> None:
        """Pushes a message to the shared status bar."""

        self.controller.set_status(message)
