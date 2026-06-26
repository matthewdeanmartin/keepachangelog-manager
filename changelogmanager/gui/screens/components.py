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
        self.commands.add("Add component", self.add_component)
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
            ttk.Label(
                self.listing_body,
                text=f"Could not read components: {exc}",
                foreground="#a00",
            ).pack(anchor="w")
            return
        if not components:
            ttk.Label(self.listing_body, text="(no components declared)").pack(
                anchor="w"
            )
            return
        ttk.Label(
            self.listing_body,
            text="Select a component to make it the active workspace component:",
        ).pack(anchor="w", pady=(0, 2))
        active = self.app_state.component
        for component in components:
            name = str(component.get("name", "?"))
            path = component.get("changelog", "?")
            tasks_file = component.get("tasks_file")
            marker = "●" if name == active else "○"
            label = f"{marker} {name} → {path}"
            if tasks_file:
                label += f"  (tasks: {tasks_file})"
            ttk.Button(
                self.listing_body,
                text=label,
                style="Toolbutton",
                command=lambda n=name: self.select_component(n),
            ).pack(anchor="w", fill=tk.X)

    def select_component(self, name: str) -> None:
        """Make ``name`` the active workspace component (drives the changelog)."""

        self.controller.component_var.set(name)
        # Reuse the controller's component->changelog wiring, then reflect it here.
        self.controller.on_component_selected()
        self.controller.refresh_component_choices()
        self.on_show()
        self.status(f"Active component: {name}")

    def add_component(self) -> None:
        """Add a component via the shared controller flow, then refresh the list."""

        self.controller.add_component()
        self.on_show()

    # ------------------------------------------------------------------
    def base_argv(self) -> list[str]:
        argv: list[str] = []
        if self.app_state.config_path:
            argv += ["--config", self.app_state.config_path]
        argv += ["--error-format", self.app_state.error_format]
        return argv

    def run(self, argv: list[str]) -> None:
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
        self.run(self.base_argv() + ["validate", "--all"])

    def validate_changed(self) -> None:
        self.run(self.base_argv() + ["validate", "--all", "--changed-only"])

    def from_commits_all(self) -> None:
        argv = self.base_argv() + ["from-commits", "--all"]
        if self.app_state.dry_run:
            argv.append("--dry-run")
        self.run(argv)
