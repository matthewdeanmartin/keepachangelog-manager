# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Small reusable Tk widgets shared across screens."""

from __future__ import annotations

import contextlib
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk


class StatusBar(ttk.Frame):  # pylint: disable=too-many-ancestors
    """A one-line status bar pinned to the bottom of the window."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, relief=tk.SUNKEN)
        self.var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.var, anchor="w").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=2
        )

    def set(self, message: str) -> None:
        """Replaces the status line text."""

        self.var.set(message)
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


class Tooltip:
    """A lightweight hover tooltip for any Tk widget.

    Shows ``text`` in a borderless top-level after the pointer rests on the
    widget for ``delay`` ms. Used to explain labels (e.g. "Component") and
    options (e.g. "Keep on promote") without cluttering the layout.
    """

    def __init__(self, widget: tk.Widget, text: str, *, delay: int = 500) -> None:
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: object = None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _show(self) -> None:
        if self._tip is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        except tk.TclError:  # pragma: no cover - widget gone
            return
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        ttk.Label(
            self._tip,
            text=self.text,
            justify=tk.LEFT,
            relief=tk.SOLID,
            borderwidth=1,
            padding=(6, 3),
            background="#ffffe0",
        ).pack()

    def _hide(self, _event: object = None) -> None:
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None

    def _cancel(self) -> None:
        if self._after_id is not None:
            with contextlib.suppress(tk.TclError):  # root may be gone
                self.widget.after_cancel(self._after_id)
            self._after_id = None


def add_tooltip(widget: tk.Widget, text: str, *, delay: int = 500) -> Tooltip:
    """Attach a :class:`Tooltip` to ``widget`` and return it."""

    return Tooltip(widget, text, delay=delay)


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
