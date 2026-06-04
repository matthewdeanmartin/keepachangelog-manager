# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""The Edit screen: a live, per-entry editor bound to the Changelog model.

Entry add/edit/remove/reorder operate on the **[Unreleased]** section through the
:class:`~changelogmanager.changelog.Changelog` mutation API (the model's mutation
surface is Unreleased-scoped). Released sections are shown read-only below.

The prologue and diff-link references live outside the entry dict: the renderer
derives the link references from per-version ``metadata['url']`` and emits a fixed
preamble. The prologue box is therefore editable free text that is spliced over the
standard preamble on save; the diff-links box is a read-only view of the derived
references.
"""

from __future__ import annotations

import tkinter as tk
from functools import partial
from pathlib import Path
from tkinter import messagebox, ttk

from changelogmanager.change_types import TYPES_OF_CHANGE, UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.gui.screens.base import Screen
from changelogmanager.gui.widgets import ScrollableFrame
from changelogmanager.runtime_logging import get_logger
from changelogmanager.vendor.keepachangelog import PREAMBLE

logger = get_logger(__name__)


class EditScreen(
    Screen
):  # pylint: disable=too-many-instance-attributes,too-many-ancestors
    """Full editor for the [Unreleased] section plus read-only history."""

    title = "Edit"

    def build_body(self) -> None:
        self.commands.add("Reload", self.controller.reload)
        self.commands.add("Save", self.save)
        self.commands.add("Validate", self.validate)
        self.commands.add("Release…", self.release)

        # Top: prologue.
        prologue_frame = ttk.LabelFrame(self.work_area, text="Prologue (header)")
        prologue_frame.pack(fill=tk.X, pady=(0, 4))
        self.prologue = tk.Text(prologue_frame, height=4, wrap=tk.WORD)
        self.prologue.pack(fill=tk.X, padx=4, pady=4)

        # Center: scrollable per-section editor.
        center = ttk.LabelFrame(self.work_area, text="[Unreleased] entries")
        center.pack(fill=tk.BOTH, expand=True)
        self.sections = ScrollableFrame(center)
        self.sections.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # An "add entry" row.
        add_row = ttk.Frame(self.work_area)
        add_row.pack(fill=tk.X, pady=4)
        ttk.Label(add_row, text="Add:").pack(side=tk.LEFT)
        self.add_type_var = tk.StringVar(value=TYPES_OF_CHANGE[0])
        ttk.Combobox(
            add_row,
            textvariable=self.add_type_var,
            values=TYPES_OF_CHANGE,
            width=12,
            state="readonly",
        ).pack(side=tk.LEFT, padx=4)
        self.add_message_var = tk.StringVar()
        entry = ttk.Entry(add_row, textvariable=self.add_message_var)
        entry.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        entry.bind("<Return>", lambda _e: self.add_entry())
        ttk.Button(add_row, text="Add entry", command=self.add_entry).pack(side=tk.LEFT)

        # Bottom: derived diff-link references (read-only).
        links_frame = ttk.LabelFrame(self.work_area, text="Diff links (derived)")
        links_frame.pack(fill=tk.X, pady=(4, 0))
        self.links = tk.Text(links_frame, height=4, wrap=tk.NONE, state=tk.DISABLED)
        self.links.pack(fill=tk.X, padx=4, pady=4)

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        """Rebuilds the editor widgets from the shared model."""

        changelog = self.app_state.changelog
        self.set_text(self.prologue, self.current_prologue(), editable=True)
        self.set_text(self.links, self.derived_links(), editable=False)

        self.sections.clear()
        if changelog is None:
            ttk.Label(self.sections.body, text="(no changelog loaded)").pack(anchor="w")
            return
        if self.app_state.load_error:
            ttk.Label(
                self.sections.body,
                text=f"Load issue: {self.app_state.load_error}",
                foreground="red",
            ).pack(anchor="w", padx=4, pady=4)

        entries = changelog.list_unreleased()
        by_type: dict[str, list[tuple[int, str]]] = {}
        for change_type, index, message in entries:
            by_type.setdefault(change_type, []).append((index, message))

        if not entries:
            ttk.Label(
                self.sections.body,
                text="No [Unreleased] entries. Add one above.",
            ).pack(anchor="w", padx=4, pady=4)

        for change_type in TYPES_OF_CHANGE:
            rows = by_type.get(change_type)
            if not rows:
                continue
            self.build_section(change_type, rows)

        self.build_history(changelog)

    def build_section(self, change_type: str, rows: list[tuple[int, str]]) -> None:
        frame = ttk.LabelFrame(self.sections.body, text=change_type.capitalize())
        frame.pack(fill=tk.X, padx=4, pady=4)
        count = len(rows)
        for position, (index, message) in enumerate(rows):
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, padx=2, pady=1)
            var = tk.StringVar(value=message)
            ttk.Entry(row, textvariable=var).pack(
                side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4)
            )
            ttk.Button(
                row,
                text="Save",
                width=5,
                command=partial(self.edit_entry_from, change_type, index, var),
            ).pack(side=tk.LEFT)
            up = ttk.Button(
                row,
                text="↑",
                width=2,
                command=partial(self.move_entry, change_type, index, -1),
            )
            up.pack(side=tk.LEFT, padx=(4, 0))
            if position == 0:
                up.state(["disabled"])
            down = ttk.Button(
                row,
                text="↓",
                width=2,
                command=partial(self.move_entry, change_type, index, 1),
            )
            down.pack(side=tk.LEFT)
            if position == count - 1:
                down.state(["disabled"])
            ttk.Button(
                row,
                text="✕",
                width=2,
                command=partial(self.remove_entry, change_type, index),
            ).pack(side=tk.LEFT, padx=(4, 0))

    def build_history(self, changelog: Changelog) -> None:
        data = changelog.get()
        released = [v for v in data if v != UNRELEASED_ENTRY]
        if not released:
            return
        history = ttk.LabelFrame(self.sections.body, text="Released (read-only)")
        history.pack(fill=tk.X, padx=4, pady=(10, 4))
        for version in released:
            release = data[version]
            metadata = release.get("metadata", {}) if isinstance(release, dict) else {}
            date = metadata.get("release_date")
            heading = version + (f" — {date}" if date else "")
            ttk.Label(history, text=heading, font=("", 9, "bold")).pack(
                anchor="w", padx=4, pady=(4, 0)
            )
            for change_type in TYPES_OF_CHANGE:
                items = release.get(change_type) if isinstance(release, dict) else None
                if not items:
                    continue
                for item in items:
                    ttk.Label(
                        history, text=f"  [{change_type}] {item}", wraplength=700
                    ).pack(anchor="w", padx=8)

    # ------------------------------------------------------------------
    # Model mutations
    # ------------------------------------------------------------------
    def require_changelog(self) -> Changelog | None:
        changelog = self.app_state.changelog
        if changelog is None:
            messagebox.showerror("No changelog", "No changelog is loaded.")
        return changelog

    def add_entry(self) -> None:
        changelog = self.require_changelog()
        if changelog is None:
            return
        message = self.add_message_var.get().strip()
        if not message:
            self.status("Enter a message before adding.")
            return
        changelog.add(change_type=self.add_type_var.get(), message=message)
        self.add_message_var.set("")
        self.status(f"Added [{self.add_type_var.get()}] entry (unsaved).")
        self.refresh()

    def edit_entry_from(self, change_type: str, index: int, var: tk.StringVar) -> None:
        """Saves the edited entry, reading the row's current text at click time."""

        self.edit_entry(change_type, index, var.get())

    def edit_entry(self, change_type: str, index: int, message: str) -> None:
        changelog = self.require_changelog()
        if changelog is None:
            return
        message = message.strip()
        if not message:
            self.status("Entry message cannot be empty.")
            return
        try:
            changelog.edit(change_type=change_type, index=index, new_message=message)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.status(f"Edit failed: {getattr(exc, 'message', exc)}")
            return
        self.status("Entry updated (unsaved).")
        self.refresh()

    def remove_entry(self, change_type: str, index: int) -> None:
        changelog = self.require_changelog()
        if changelog is None:
            return
        try:
            removed = changelog.remove(change_type=change_type, index=index)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.status(f"Remove failed: {getattr(exc, 'message', exc)}")
            return
        self.status(f"Removed: {removed} (unsaved).")
        self.refresh()

    def move_entry(self, change_type: str, index: int, delta: int) -> None:
        """Reorders an entry within its change-type bucket in the live model."""

        changelog = self.require_changelog()
        if changelog is None:
            return
        data = changelog.get()
        bucket = data.get(UNRELEASED_ENTRY, {}).get(change_type)
        if not isinstance(bucket, list):
            return
        target = index + delta
        if target < 0 or target >= len(bucket):
            return
        bucket[index], bucket[target] = bucket[target], bucket[index]
        self.status("Reordered (unsaved).")
        self.refresh()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self) -> None:
        changelog = self.require_changelog()
        if changelog is None:
            return
        try:
            text = changelog.render()
            text = self.apply_prologue(text)
            Path(changelog.get_file_path()).write_text(text, encoding="utf-8")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            messagebox.showerror("Save failed", str(getattr(exc, "message", exc)))
            self.status(f"Save failed: {getattr(exc, 'message', exc)}")
            return
        self.status(f"Saved {changelog.get_file_path()}")
        self.refresh()

    def validate(self) -> None:
        """Re-reads the file through the reader and reports diagnostics."""

        self.save()
        from changelogmanager.gui.cli_runner import (
            run_cli,
        )  # pylint: disable=import-outside-toplevel

        argv: list[str] = []
        if self.app_state.config_path:
            argv += ["--config", self.app_state.config_path]
        argv += ["--error-format", self.app_state.error_format]
        argv += ["--input-file", self.app_state.input_file, "validate"]
        code, output = run_cli(argv)
        if code == 0:
            self.status("Validation passed.")
        else:
            first_line = output.strip().splitlines()[0] if output.strip() else "failed"
            self.status(f"Validation failed: {first_line}")
        if output.strip():
            messagebox.showinfo("Validate", output.strip())

    def release(self) -> None:
        changelog = self.require_changelog()
        if changelog is None:
            return
        if not changelog.has_unreleased():
            messagebox.showinfo("Release", "No [Unreleased] entries to release.")
            return
        try:
            future = str(changelog.suggest_future_version())
        except Exception as exc:  # pylint: disable=broad-exception-caught
            future = "?"
            logger.warning("Could not suggest version: %s", exc)
        if not messagebox.askyesno(
            "Release", f"Promote [Unreleased] to {future} and save?"
        ):
            return
        try:
            changelog.release(None)
            text = self.apply_prologue(changelog.render())
            Path(changelog.get_file_path()).write_text(text, encoding="utf-8")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            messagebox.showerror("Release failed", str(getattr(exc, "message", exc)))
            return
        self.status(f"Released {future}")
        self.controller.reload()

    # ------------------------------------------------------------------
    # Prologue / links helpers
    # ------------------------------------------------------------------
    def current_prologue(self) -> str:
        """Returns the prologue: the model's preamble, or the on-disk header."""

        raw = self.app_state.raw_text()
        marker = raw.find("\n## ")
        if marker != -1:
            return raw[:marker].strip("\n")
        changelog = self.app_state.changelog
        if changelog is not None:
            rendered = changelog.render()
            marker = rendered.find("\n## ")
            if marker != -1:
                return rendered[:marker].strip("\n")
        return PREAMBLE.strip("\n")

    def apply_prologue(self, rendered: str) -> str:
        """Splices the (possibly edited) prologue ahead of the rendered body."""

        prologue = self.prologue.get("1.0", tk.END).rstrip("\n")
        marker = rendered.find("\n## ")
        body = rendered[marker:] if marker != -1 else "\n" + rendered.lstrip("\n")
        return prologue + body if body.startswith("\n") else prologue + "\n" + body

    def derived_links(self) -> str:
        changelog = self.app_state.changelog
        if changelog is None:
            return ""
        rendered = changelog.render()
        return "\n".join(
            line
            for line in rendered.splitlines()
            if line.startswith("[") and "]: " in line
        )

    @staticmethod
    def set_text(widget: tk.Text, value: str, *, editable: bool) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value)
        if not editable:
            widget.configure(state=tk.DISABLED)
