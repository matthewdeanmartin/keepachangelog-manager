# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog fragments screen.

Drives the ``fragments`` CLI flows (list / add / validate / collect) in-process.
Fragments are per-change files dropped under ``changelog.d`` that ``collect``
folds into ``[Unreleased]``; after a real collect the shared model is reloaded so
the Edit screen reflects the new entries.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk

from changelogmanager.change_types import TYPES_OF_CHANGE
from changelogmanager.gui.cli_runner import run_cli
from changelogmanager.gui.screens.base import Screen


class FragmentsScreen(
    Screen
):  # pylint: disable=too-many-ancestors,too-many-instance-attributes
    """Manage changelog fragment files."""

    title = "Fragments"

    def build_body(self) -> None:
        self.commands.add("Refresh", self.refresh_list)
        self.commands.add("Validate", self.validate)
        self.commands.add("Collect", self.collect)

        opts = ttk.LabelFrame(self.work_area, text="Fragments options")
        opts.pack(fill=tk.X, pady=(0, 6))
        row = ttk.Frame(opts)
        row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(row, text="Fragment dir (blank = auto):").pack(side=tk.LEFT)
        self.fragment_dir_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.fragment_dir_var, width=28).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(row, text="Consume:").pack(side=tk.LEFT, padx=(8, 0))
        self.consume_var = tk.StringVar(value="archive")
        ttk.Combobox(
            row,
            textvariable=self.consume_var,
            values=["archive", "delete", "keep"],
            width=10,
            state="readonly",
        ).pack(side=tk.LEFT, padx=4)

        list_frame = ttk.LabelFrame(self.work_area, text="Pending fragments")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.list_view = scrolledtext.ScrolledText(
            list_frame, wrap=tk.WORD, height=8, state=tk.DISABLED
        )
        self.list_view.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        add_row = ttk.Frame(self.work_area)
        add_row.pack(fill=tk.X, pady=2)
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
        entry.bind("<Return>", lambda _e: self.add_fragment())
        ttk.Label(add_row, text="Slug:").pack(side=tk.LEFT)
        self.slug_var = tk.StringVar()
        ttk.Entry(add_row, textvariable=self.slug_var, width=12).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(add_row, text="Add fragment", command=self.add_fragment).pack(
            side=tk.LEFT
        )

        out_frame = ttk.LabelFrame(self.work_area, text="Output")
        out_frame.pack(fill=tk.BOTH, expand=True)
        self.output = scrolledtext.ScrolledText(out_frame, wrap=tk.WORD, height=8)
        self.output.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def on_show(self) -> None:
        self.refresh_list()

    # ------------------------------------------------------------------
    def base_argv(self) -> list[str]:
        argv: list[str] = []
        if self.app_state.config_path:
            argv += ["--config", self.app_state.config_path]
        argv += ["--error-format", self.app_state.error_format]
        argv += ["--input-file", self.app_state.input_file]
        return argv

    def fragment_dir_args(self) -> list[str]:
        value = self.fragment_dir_var.get().strip()
        return ["--fragment-dir", value] if value else []

    def run(self, argv: list[str], *, reload: bool = False) -> tuple[int, str]:
        self.output.insert(tk.END, f"$ changelogmanager {' '.join(argv)}\n")
        self.output.see(tk.END)
        self.output.update_idletasks()
        code, text = run_cli(argv)
        self.output.insert(tk.END, text + f"\n[exit {code}]\n\n")
        self.output.see(tk.END)
        self.status(f"fragments finished (exit {code})")
        if reload:
            self.controller.reload()
        return code, text

    # ------------------------------------------------------------------
    def refresh_list(self) -> None:
        argv = self.base_argv() + ["fragments", "list"] + self.fragment_dir_args()
        _code, text = run_cli(argv)
        self.list_view.configure(state=tk.NORMAL)
        self.list_view.delete("1.0", tk.END)
        self.list_view.insert("1.0", text.strip() or "(no fragments)")
        self.list_view.configure(state=tk.DISABLED)

    def add_fragment(self) -> None:
        message = self.add_message_var.get().strip()
        if not message:
            self.status("Enter a fragment message before adding.")
            return
        argv = self.base_argv() + [
            "fragments",
            "add",
            self.add_type_var.get(),
            message,
        ]
        slug = self.slug_var.get().strip()
        if slug:
            argv += ["--slug", slug]
        argv += self.fragment_dir_args()
        self.run(argv)
        self.add_message_var.set("")
        self.slug_var.set("")
        self.refresh_list()

    def validate(self) -> None:
        argv = self.base_argv() + ["fragments", "validate"] + self.fragment_dir_args()
        self.run(argv)

    def collect(self) -> None:
        argv = self.base_argv() + ["fragments", "collect"] + self.fragment_dir_args()
        argv += ["--consume", self.consume_var.get()]
        if self.app_state.dry_run:
            argv.append("--dry-run")
        self.run(argv, reload=not self.app_state.dry_run)
        self.refresh_list()
