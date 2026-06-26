# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Commit-lint screen.

Drives ``lint-commits`` (read-only audit of past commit subjects against the
Keep a Changelog commit schema) and ``rewrite-messages`` (plan-only subject
rewrites over the unpushed range). Both are read-only here: ``rewrite-messages
--apply`` is intentionally not implemented in the CLI, so the GUI offers only the
plan path.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk

from changelogmanager.change_types import TYPES_OF_CHANGE
from changelogmanager.gui.cli_runner import run_cli
from changelogmanager.gui.screens.base import Screen

_SCHEMAS = ["auto", "conventional", "gitmoji", "keepachangelog"]


class LintScreen(
    Screen
):  # pylint: disable=too-many-ancestors,too-many-instance-attributes
    """Audit commit messages and plan rewrites."""

    title = "Commit Lint"
    # Operates purely on git history; never reads/writes the workspace changelog.
    uses_changelog = False

    def build_body(self) -> None:
        self.commands.add("Lint commits", self.lint_commits)
        self.commands.add("Plan rewrites", self.plan_rewrites)

        shared = ttk.LabelFrame(self.work_area, text="Commit range")
        shared.pack(fill=tk.X, pady=(0, 6))
        row = ttk.Frame(shared)
        row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(row, text="Since:").pack(side=tk.LEFT)
        self.since_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.since_var, width=14).pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text="Until:").pack(side=tk.LEFT, padx=(8, 0))
        self.until_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.until_var, width=14).pack(side=tk.LEFT, padx=4)
        self.all_history_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="All history", variable=self.all_history_var).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Label(row, text="Schema:").pack(side=tk.LEFT, padx=(8, 0))
        self.schema_var = tk.StringVar(value="auto")
        ttk.Combobox(
            row,
            textvariable=self.schema_var,
            values=_SCHEMAS,
            width=14,
            state="readonly",
        ).pack(side=tk.LEFT, padx=4)

        lint = ttk.LabelFrame(self.work_area, text="lint-commits options")
        lint.pack(fill=tk.X, pady=(0, 6))
        lrow = ttk.Frame(lint)
        lrow.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(lrow, text="Show:").pack(side=tk.LEFT)
        self.show_var = tk.StringVar(value="fail")
        ttk.Combobox(
            lrow,
            textvariable=self.show_var,
            values=["fail", "skip", "pass", "all"],
            width=8,
            state="readonly",
        ).pack(side=tk.LEFT, padx=4)
        self.strict_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(lrow, text="Strict (exit 1)", variable=self.strict_var).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Label(lrow, text="Max commits:").pack(side=tk.LEFT, padx=(8, 0))
        self.max_commits_var = tk.StringVar()
        ttk.Entry(lrow, textvariable=self.max_commits_var, width=8).pack(
            side=tk.LEFT, padx=4
        )

        rewrite = ttk.LabelFrame(self.work_area, text="rewrite-messages options")
        rewrite.pack(fill=tk.X, pady=(0, 6))
        rrow = ttk.Frame(rewrite)
        rrow.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(rrow, text="Auto-prefix:").pack(side=tk.LEFT)
        self.auto_prefix_var = tk.StringVar(value="")
        ttk.Combobox(
            rrow,
            textvariable=self.auto_prefix_var,
            values=["", *TYPES_OF_CHANGE],
            width=12,
            state="readonly",
        ).pack(side=tk.LEFT, padx=4)
        ttk.Label(rrow, text="Plan out file:").pack(side=tk.LEFT, padx=(8, 0))
        self.plan_out_var = tk.StringVar()
        ttk.Entry(rrow, textvariable=self.plan_out_var, width=22).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(
            rewrite,
            text="Apply is not implemented in the CLI; this plans only (read-only).",
            foreground="#444",
        ).pack(anchor="w", padx=4, pady=(0, 2))

        out_frame = ttk.LabelFrame(self.work_area, text="Output")
        out_frame.pack(fill=tk.BOTH, expand=True)
        self.output = scrolledtext.ScrolledText(out_frame, wrap=tk.WORD, height=12)
        self.output.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    # ------------------------------------------------------------------
    def base_argv(self) -> list[str]:
        argv: list[str] = []
        if self.app_state.config_path:
            argv += ["--config", self.app_state.config_path]
        argv += ["--error-format", self.app_state.error_format]
        return argv

    def range_args(self) -> list[str]:
        argv: list[str] = []
        if self.since_var.get().strip():
            argv += ["--since", self.since_var.get().strip()]
        if self.until_var.get().strip():
            argv += ["--until", self.until_var.get().strip()]
        if self.all_history_var.get():
            argv.append("--all-history")
        argv += ["--commit-schema", self.schema_var.get()]
        return argv

    def run(self, argv: list[str]) -> None:
        self.output.insert(tk.END, f"$ changelogmanager {' '.join(argv)}\n")
        self.output.see(tk.END)
        self.output.update_idletasks()
        code, text = run_cli(argv)
        self.output.insert(tk.END, text + f"\n[exit {code}]\n\n")
        self.output.see(tk.END)
        self.status(f"{argv[len(self.base_argv())]} finished (exit {code})")

    def lint_commits(self) -> None:
        argv = self.base_argv() + ["lint-commits"] + self.range_args()
        argv += ["--show", self.show_var.get()]
        if self.strict_var.get():
            argv.append("--strict")
        max_commits = self.max_commits_var.get().strip()
        if max_commits:
            argv += ["--max-commits", max_commits]
        self.run(argv)

    def plan_rewrites(self) -> None:
        # rewrite-messages is scoped to unpushed commits and shares only the
        # schema flag (not since/until/all-history).
        argv = self.base_argv() + [
            "rewrite-messages",
            "--commit-schema",
            self.schema_var.get(),
        ]
        if self.auto_prefix_var.get():
            argv += ["--auto-prefix", self.auto_prefix_var.get()]
        if self.plan_out_var.get().strip():
            argv += ["--plan-out", self.plan_out_var.get().strip()]
        self.run(argv)
