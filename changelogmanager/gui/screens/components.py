# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Components / batch screen.

Batch operations across the multiple changelogs declared in the config file —
distinct from the single-changelog editor. Lists configured components and drives
the ``--all`` CLI flows.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk

from changelogmanager.config import get_components_from_config
from changelogmanager.gui.cli_runner import run_cli
from changelogmanager.gui.screens.base import Screen


class ComponentsScreen(Screen):  # pylint: disable=too-many-ancestors
    """Validate / seed every configured component at once."""

    title = "Components / Batch"

    def build_body(self) -> None:
        self.commands.add("Validate all", self.validate_all)
        self.commands.add("Validate changed", self.validate_changed)
        self.commands.add("From-commits all", self.from_commits_all)

        self.listing = ttk.LabelFrame(self.work_area, text="Configured components")
        self.listing.pack(fill=tk.X, pady=(0, 6))
        self.listing_body = ttk.Frame(self.listing)
        self.listing_body.pack(fill=tk.X, padx=4, pady=4)

        out_frame = ttk.LabelFrame(self.work_area, text="Output")
        out_frame.pack(fill=tk.BOTH, expand=True)
        self.output = scrolledtext.ScrolledText(out_frame, wrap=tk.WORD, height=14)
        self.output.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def on_show(self) -> None:
        for child in self.listing_body.winfo_children():
            child.destroy()
        if not self.app_state.config_path:
            ttk.Label(
                self.listing_body,
                text="No config file. Batch operations require a config with components.",
                foreground="#a00",
            ).pack(anchor="w")
            return
        try:
            components = get_components_from_config(self.app_state.config_path)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            ttk.Label(self.listing_body, text=f"Could not read components: {exc}",
                      foreground="#a00").pack(anchor="w")
            return
        if not components:
            ttk.Label(self.listing_body, text="(no components declared)").pack(anchor="w")
            return
        for component in components:
            name = component.get("name", "?")
            path = component.get("changelog", "?")
            ttk.Label(self.listing_body, text=f"• {name} → {path}").pack(anchor="w")

    # ------------------------------------------------------------------
    def _base_argv(self) -> list[str]:
        argv: list[str] = []
        if self.app_state.config_path:
            argv += ["--config", self.app_state.config_path]
        argv += ["--error-format", self.app_state.error_format]
        return argv

    def _run(self, argv: list[str]) -> None:
        if not self.app_state.config_path:
            self.status("Batch operations require a config file.")
            return
        self.output.insert(tk.END, f"$ changelogmanager {' '.join(argv)}\n")
        self.output.see(tk.END)
        self.output.update_idletasks()
        code, text = run_cli(argv)
        self.output.insert(tk.END, text + f"\n[exit {code}]\n\n")
        self.output.see(tk.END)
        self.status(f"Batch command finished (exit {code})")
        self.controller.reload()

    def validate_all(self) -> None:
        self._run(self._base_argv() + ["validate", "--all"])

    def validate_changed(self) -> None:
        self._run(self._base_argv() + ["validate", "--all", "--changed-only"])

    def from_commits_all(self) -> None:
        argv = self._base_argv() + ["from-commits", "--all"]
        if self.app_state.dry_run:
            argv.append("--dry-run")
        self._run(argv)
