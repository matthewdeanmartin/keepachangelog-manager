# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Initialize / Backfill screen.

Drives the create / config-init / backfill / from-commits CLI flows in-process and
shows their output. These are batch/seed operations, so they reuse the CLI runner
rather than the live editor model.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk

from changelogmanager.gui.cli_runner import run_cli
from changelogmanager.gui.screens.base import Screen


class BackfillScreen(
    Screen
):  # pylint: disable=too-many-instance-attributes,too-many-ancestors
    """Create a changelog and seed it from history."""

    title = "Initialize / Backfill"

    def build_body(self) -> None:
        self.commands.add("Create changelog", self.create)
        self.commands.add("Config init…", self.config_init)
        self.commands.add("Backfill", self.backfill)
        self.commands.add("From commits", self.from_commits)

        form = ttk.LabelFrame(self.work_area, text="Backfill / from-commits options")
        form.pack(fill=tk.X, pady=(0, 6))

        self.source_var = tk.StringVar(value="all")
        self.strategy_var = tk.StringVar(value="conservative")
        self.commit_schema_var = tk.StringVar(value="auto")
        self.since_var = tk.StringVar()
        self.until_var = tk.StringVar()
        self.missing_only_var = tk.BooleanVar(value=True)
        self.include_unreleased_var = tk.BooleanVar(value=False)
        self.all_history_var = tk.BooleanVar(value=False)

        self.combo(
            form,
            "Source:",
            self.source_var,
            ["tags", "github-releases", "github-prs", "pypi", "commits", "all"],
        )
        self.combo(
            form, "Strategy:", self.strategy_var, ["conservative", "merge", "replace"]
        )
        self.combo(
            form,
            "Commit schema:",
            self.commit_schema_var,
            ["auto", "conventional", "gitmoji", "keepachangelog"],
        )

        row = ttk.Frame(form)
        row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(row, text="Since:").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.since_var, width=16).pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text="Until:").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Entry(row, textvariable=self.until_var, width=16).pack(side=tk.LEFT, padx=4)

        checks = ttk.Frame(form)
        checks.pack(fill=tk.X, padx=4, pady=2)
        ttk.Checkbutton(
            checks, text="Missing only", variable=self.missing_only_var
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(
            checks, text="Include [Unreleased]", variable=self.include_unreleased_var
        ).pack(side=tk.LEFT, padx=8)
        ttk.Checkbutton(
            checks, text="All history (from-commits)", variable=self.all_history_var
        ).pack(side=tk.LEFT, padx=8)

        out_frame = ttk.LabelFrame(self.work_area, text="Output")
        out_frame.pack(fill=tk.BOTH, expand=True)
        self.output = scrolledtext.ScrolledText(out_frame, wrap=tk.WORD, height=14)
        self.output.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def combo(self, parent, label, var, values) -> None:  # type: ignore[no-untyped-def]
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(row, text=label, width=14, anchor="w").pack(side=tk.LEFT)
        ttk.Combobox(
            row, textvariable=var, values=values, width=18, state="readonly"
        ).pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    def base_argv(self) -> list[str]:
        argv: list[str] = []
        if self.app_state.config_path:
            argv += ["--config", self.app_state.config_path]
        if self.app_state.component:
            argv += ["--component", self.app_state.component]
        argv += ["--error-format", self.app_state.error_format]
        argv += ["--input-file", self.app_state.input_file]
        return argv

    def run(self, argv: list[str]) -> None:
        self.output.insert(tk.END, f"$ changelogmanager {' '.join(argv)}\n")
        self.output.see(tk.END)
        self.output.update_idletasks()
        code, text = run_cli(argv)
        self.output.insert(tk.END, text + f"\n[exit {code}]\n\n")
        self.output.see(tk.END)
        self.status(f"{argv[-1] if argv else 'command'} finished (exit {code})")
        self.controller.reload()

    def create(self) -> None:
        argv = self.base_argv() + ["create"]
        if self.app_state.dry_run:
            argv.append("--dry-run")
        self.run(argv)

    def config_init(self) -> None:
        # config init is interactive (inquirer); point users at the Config window.
        self.status("Use Config ▸ Settings… for interactive configuration.")
        self.controller.open_config()

    def backfill(self) -> None:
        argv = self.base_argv() + ["backfill", "--source", self.source_var.get()]
        argv += ["--strategy", self.strategy_var.get()]
        argv += ["--commit-schema", self.commit_schema_var.get()]
        if self.since_var.get().strip():
            argv += ["--since", self.since_var.get().strip()]
        if self.until_var.get().strip():
            argv += ["--until", self.until_var.get().strip()]
        argv.append(
            "--missing-only" if self.missing_only_var.get() else "--no-missing-only"
        )
        if self.include_unreleased_var.get():
            argv.append("--include-unreleased")
        if self.app_state.dry_run:
            argv.append("--dry-run")
        self.run(argv)

    def from_commits(self) -> None:
        argv = self.base_argv() + [
            "from-commits",
            "--commit-schema",
            self.commit_schema_var.get(),
        ]
        if self.since_var.get().strip():
            argv += ["--since", self.since_var.get().strip()]
        if self.all_history_var.get():
            argv.append("--all-history")
        if self.app_state.dry_run:
            argv.append("--dry-run")
        self.run(argv)
