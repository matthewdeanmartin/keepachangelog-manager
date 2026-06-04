# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Small reusable Tk widgets shared across screens."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk


class StatusBar(ttk.Frame):  # pylint: disable=too-many-ancestors
    """A one-line status bar pinned to the bottom of the window."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, relief=tk.SUNKEN)
        self._var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self._var, anchor="w").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=2
        )

    def set(self, message: str) -> None:
        """Replaces the status line text."""

        self._var.set(message)
        self.update_idletasks()


class CommandList(ttk.LabelFrame):  # pylint: disable=too-many-ancestors
    """The left-hand list of related commands for a screen."""

    def __init__(self, parent: tk.Misc, title: str = "Commands") -> None:
        super().__init__(parent, text=title)

    def add(self, label: str, command: Callable[[], None]) -> ttk.Button:
        """Adds a full-width command button and returns it."""

        button = ttk.Button(self, text=label, width=20, command=command)
        button.pack(padx=6, pady=3, anchor="w", fill=tk.X)
        return button


class ScrollableFrame(ttk.Frame):  # pylint: disable=too-many-ancestors
    """A vertically scrollable container; add children to ``.body``."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        self.body = ttk.Frame(canvas)

        self.body.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        window = canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(window, width=e.width),
        )
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def clear(self) -> None:
        """Destroys all child widgets in the scrollable body."""

        for child in self.body.winfo_children():
            child.destroy()
