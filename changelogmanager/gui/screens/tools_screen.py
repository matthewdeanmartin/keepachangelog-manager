# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Tools / Export screen.

A catch-all for the smaller CLI commands that don't warrant their own screen:
``version`` queries, ``to-json`` / ``to-html`` exports, ``skill export``, and a
read-only ``credentials check``. Storing tokens (``credentials set``) is a TTY /
keyring operation and is intentionally left to the CLI — only ``check`` is
surfaced here so users can see whether tokens are configured.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk

from changelogmanager.gui.cli_runner import run_cli
from changelogmanager.gui.screens.base import Screen


class ToolsScreen(Screen):  # pylint: disable=too-many-ancestors,too-many-instance-attributes
    """Version queries, exports, skill export, and credential status."""

    title = "Tools / Export"

    def build_body(self) -> None:
        self.commands.add("Get version", self.get_version)
        self.commands.add("Export JSON", self.export_json)
        self.commands.add("Export HTML", self.export_html)
        self.commands.add("Export skill", self.export_skill)
        self.commands.add("Check credentials", self.check_credentials)

        version_box = ttk.LabelFrame(self.work_area, text="Version")
        version_box.pack(fill=tk.X, pady=(0, 6))
        vrow = ttk.Frame(version_box)
        vrow.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(vrow, text="Reference:").pack(side=tk.LEFT)
        self.reference_var = tk.StringVar(value="current")
        ttk.Combobox(
            vrow,
            textvariable=self.reference_var,
            values=["previous", "current", "future"],
            width=12,
            state="readonly",
        ).pack(side=tk.LEFT, padx=4)

        export_box = ttk.LabelFrame(self.work_area, text="Export")
        export_box.pack(fill=tk.X, pady=(0, 6))
        jrow = ttk.Frame(export_box)
        jrow.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(jrow, text="JSON file:", width=12, anchor="w").pack(side=tk.LEFT)
        self.json_file_var = tk.StringVar(value="CHANGELOG.json")
        ttk.Entry(jrow, textvariable=self.json_file_var, width=30).pack(
            side=tk.LEFT, padx=4
        )
        hrow = ttk.Frame(export_box)
        hrow.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(hrow, text="HTML file:", width=12, anchor="w").pack(side=tk.LEFT)
        self.html_file_var = tk.StringVar(value="CHANGELOG.html")
        ttk.Entry(hrow, textvariable=self.html_file_var, width=30).pack(
            side=tk.LEFT, padx=4
        )

        skill_box = ttk.LabelFrame(self.work_area, text="Skill export")
        skill_box.pack(fill=tk.X, pady=(0, 6))
        srow = ttk.Frame(skill_box)
        srow.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(srow, text="Destination dir (blank = prompt):").pack(side=tk.LEFT)
        self.skill_path_var = tk.StringVar()
        ttk.Entry(srow, textvariable=self.skill_path_var, width=28).pack(
            side=tk.LEFT, padx=4
        )

        out_frame = ttk.LabelFrame(self.work_area, text="Output")
        out_frame.pack(fill=tk.BOTH, expand=True)
        self.output = scrolledtext.ScrolledText(out_frame, wrap=tk.WORD, height=12)
        self.output.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    # ------------------------------------------------------------------
    def base_argv(self, *, with_input: bool = True) -> list[str]:
        argv: list[str] = []
        if self.app_state.config_path:
            argv += ["--config", self.app_state.config_path]
        argv += ["--error-format", self.app_state.error_format]
        if with_input:
            argv += ["--input-file", self.app_state.input_file]
        return argv

    def run(self, argv: list[str]) -> None:
        self.output.insert(tk.END, f"$ changelogmanager {' '.join(argv)}\n")
        self.output.see(tk.END)
        self.output.update_idletasks()
        code, text = run_cli(argv)
        self.output.insert(tk.END, text + f"\n[exit {code}]\n\n")
        self.output.see(tk.END)
        self.status(f"command finished (exit {code})")

    # ------------------------------------------------------------------
    def get_version(self) -> None:
        argv = self.base_argv() + ["version", "--reference", self.reference_var.get()]
        self.run(argv)

    def export_json(self) -> None:
        argv = self.base_argv() + ["to-json"]
        name = self.json_file_var.get().strip()
        if name:
            argv += ["--file-name", name]
        if self.app_state.dry_run:
            argv.append("--dry-run")
        self.run(argv)

    def export_html(self) -> None:
        argv = self.base_argv() + ["to-html"]
        name = self.html_file_var.get().strip()
        if name:
            argv += ["--file-name", name]
        if self.app_state.dry_run:
            argv.append("--dry-run")
        self.run(argv)

    def export_skill(self) -> None:
        argv = self.base_argv(with_input=False) + ["skill", "export"]
        path = self.skill_path_var.get().strip()
        if path:
            argv += ["--path", path]
        if self.app_state.dry_run:
            argv.append("--dry-run")
        self.run(argv)

    def check_credentials(self) -> None:
        argv = self.base_argv(with_input=False) + ["credentials", "check"]
        self.run(argv)
