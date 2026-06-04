# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""GitHub / GitLab Releases screen.

Outside CI the Dry-run box defaults checked (a real release is destructive and
usually belongs in a pipeline), and a copyable sample CI snippet is shown so the
user can wire the real call into their own GitHub Actions / GitLab CI config.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import scrolledtext, ttk

from changelogmanager.gui.cli_runner import run_cli
from changelogmanager.gui.screens.base import Screen
from changelogmanager.gui.state import running_in_ci
from changelogmanager.gui.yaml_samples import SAMPLES


class ReleasesScreen(
    Screen
):  # pylint: disable=too-many-instance-attributes,too-many-ancestors
    """Drive github-release / github-pr / gitlab-release."""

    title = "Releases"

    def build_body(self) -> None:
        self.command = "github-release"
        self.commands.add("GitHub release", lambda: self.select("github-release"))
        self.commands.add("GitHub PR", lambda: self.select("github-pr"))
        self.commands.add("GitLab release", lambda: self.select("gitlab-release"))

        banner = (
            "CI detected — live calls enabled."
            if running_in_ci()
            else (
                "Local mode — dry-run is on by default. Copy the sample CI snippet to "
                "run real releases from your pipeline."
            )
        )
        ttk.Label(self.work_area, text=banner, wraplength=820, foreground="#444").pack(
            anchor="w", pady=(0, 6)
        )

        form = ttk.LabelFrame(self.work_area, text="Release parameters")
        form.pack(fill=tk.X, pady=(0, 6))

        self.repo_var = tk.StringVar(value=os.environ.get("GITHUB_REPOSITORY", ""))
        self.token_var = tk.StringVar(value=os.environ.get("GITHUB_TOKEN", ""))
        self.draft_var = tk.BooleanVar(value=True)
        self.project_var = tk.StringVar(value=os.environ.get("CI_PROJECT_ID", ""))
        self.gitlab_token_var = tk.StringVar(value=os.environ.get("GITLAB_TOKEN", ""))
        self.head_var = tk.StringVar()
        self.base_var = tk.StringVar(value="main")

        self.field(form, "Repository (owner/repo):", self.repo_var)
        self.field(form, "GitHub token:", self.token_var, secret=True)
        ttk.Checkbutton(
            form, text="Draft (uncheck to publish)", variable=self.draft_var
        ).pack(anchor="w", padx=4)
        self.field(form, "PR head branch:", self.head_var)
        self.field(form, "PR base branch:", self.base_var)
        self.field(form, "GitLab project (id or group/project):", self.project_var)
        self.field(form, "GitLab token:", self.gitlab_token_var, secret=True)

        run_row = ttk.Frame(self.work_area)
        run_row.pack(fill=tk.X, pady=2)
        ttk.Button(
            run_row, text="Run selected command", command=self.run_selected
        ).pack(side=tk.LEFT)
        self.selected_var = tk.StringVar(value="github-release")
        ttk.Label(run_row, textvariable=self.selected_var).pack(side=tk.LEFT, padx=8)

        panes = ttk.Panedwindow(self.work_area, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        out_frame = ttk.LabelFrame(panes, text="Output")
        self.output = scrolledtext.ScrolledText(out_frame, wrap=tk.WORD, width=50)
        self.output.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        panes.add(out_frame, weight=1)

        sample_frame = ttk.LabelFrame(panes, text="Sample CI snippet")
        toolbar = ttk.Frame(sample_frame)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="Copy", command=self.copy_sample).pack(
            side=tk.RIGHT, padx=4, pady=2
        )
        self.sample = scrolledtext.ScrolledText(sample_frame, wrap=tk.NONE, width=50)
        self.sample.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        panes.add(sample_frame, weight=1)

        self.select("github-release")

    def field(self, parent, label, var, *, secret=False) -> None:  # type: ignore[no-untyped-def]
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(row, text=label, width=30, anchor="w").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=var, width=36, show="*" if secret else "").pack(
            side=tk.LEFT, padx=4
        )

    # ------------------------------------------------------------------
    def select(self, command: str) -> None:
        self.selected_var.set(f"Selected: {command}")
        self.command = command  # pylint: disable=attribute-defined-outside-init
        self.sample.delete("1.0", tk.END)
        self.sample.insert("1.0", SAMPLES.get(command, ""))

    def copy_sample(self) -> None:
        text = self.sample.get("1.0", tk.END).rstrip("\n")
        self.controller.root.clipboard_clear()
        self.controller.root.clipboard_append(text)
        self.status("Sample CI snippet copied to clipboard.")

    def run_selected(self) -> None:
        command = getattr(self, "command", "github-release")
        argv: list[str] = []
        if self.app_state.config_path:
            argv += ["--config", self.app_state.config_path]
        argv += ["--error-format", self.app_state.error_format]
        argv += ["--input-file", self.app_state.input_file, command]

        if command == "github-release":
            if self.repo_var.get().strip():
                argv += ["--repository", self.repo_var.get().strip()]
            if self.token_var.get().strip():
                argv += ["--github-token", self.token_var.get().strip()]
            argv.append("--draft" if self.draft_var.get() else "--release")
        elif command == "github-pr":
            if self.repo_var.get().strip():
                argv += ["--repository", self.repo_var.get().strip()]
            if self.head_var.get().strip():
                argv += ["--head", self.head_var.get().strip()]
            if self.base_var.get().strip():
                argv += ["--base", self.base_var.get().strip()]
            if self.token_var.get().strip():
                argv += ["--github-token", self.token_var.get().strip()]
        elif command == "gitlab-release":
            if self.project_var.get().strip():
                argv += ["--project", self.project_var.get().strip()]
            if self.gitlab_token_var.get().strip():
                argv += ["--gitlab-token", self.gitlab_token_var.get().strip()]

        if self.app_state.dry_run:
            argv.append("--dry-run")

        self.output.insert(
            tk.END, f"$ changelogmanager {' '.join(self.redact(argv))}\n"
        )
        self.output.see(tk.END)
        self.output.update_idletasks()
        code, text = run_cli(argv)
        self.output.insert(tk.END, text + f"\n[exit {code}]\n\n")
        self.output.see(tk.END)
        self.status(f"{command} finished (exit {code})")

    @staticmethod
    def redact(argv: list[str]) -> list[str]:
        redacted = list(argv)
        for flag in ("--github-token", "--gitlab-token"):
            if flag in redacted:
                idx = redacted.index(flag)
                if idx + 1 < len(redacted):
                    redacted[idx + 1] = "***"
        return redacted
