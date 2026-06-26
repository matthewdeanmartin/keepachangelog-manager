# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""TASKS.md screen.

Drives the ``tasks`` CLI flows (list / add / check / uncheck / validate /
promote) in-process via the CLI runner. The list view re-runs ``tasks list`` and
parses the human-readable ``<line>: [x] change_type: text`` lines so each task
gets inline Check / Uncheck buttons.
"""

from __future__ import annotations

import re
import tkinter as tk
from functools import partial
from tkinter import scrolledtext, ttk

from changelogmanager.change_types import TYPES_OF_CHANGE
from changelogmanager.gui.cli_runner import run_cli
from changelogmanager.gui.screens.base import Screen
from changelogmanager.gui.widgets import add_tooltip
from changelogmanager.tasks import default_task_file_name

# Matches a `tasks list` output row: "12: [x] fixed: Some text".
_TASK_LINE = re.compile(r"^\s*(\d+):\s*\[(.)\]\s*(\S+):\s*(.*)$")


class TasksScreen(
    Screen
):  # pylint: disable=too-many-ancestors,too-many-instance-attributes
    """Manage a lightweight TASKS.md file."""

    title = "Tasks"

    #: This screen acts on TASKS.md, not the changelog: the top panel shows the
    #: primary Tasks-file picker instead of the Changelog picker.
    uses_tasks_file = True

    def build_body(self) -> None:
        self.commands.add("Refresh", self.refresh_list)
        self.commands.add("Validate", self.validate)
        self.commands.add("Promote", self.promote)

        # The tasks file lives in the top-panel Workspace picker (controller
        # state), so it reads as the "primary TASKS.md" — same treatment the
        # Changelog picker gets.
        self.tasks_file_var = self.controller.tasks_file_var

        opts = ttk.LabelFrame(self.work_area, text="Promote options")
        opts.pack(fill=tk.X, pady=(0, 6))
        row = ttk.Frame(opts)
        row.pack(fill=tk.X, padx=4, pady=2)
        self.keep_var = tk.BooleanVar(value=False)
        keep_check = ttk.Checkbutton(
            row, text="Keep on promote", variable=self.keep_var
        )
        keep_check.pack(side=tk.LEFT, padx=8)
        add_tooltip(
            keep_check,
            "Leave promoted tasks in TASKS.md after copying them into "
            "[Unreleased]. Off: completed tasks are removed once promoted.",
        )

        # Parsed task list with inline check/uncheck buttons.
        list_frame = ttk.LabelFrame(self.work_area, text="Tasks")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.list_body = ttk.Frame(list_frame)
        self.list_body.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

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
        entry.bind("<Return>", lambda _e: self.add_task())
        ttk.Button(add_row, text="Add task", command=self.add_task).pack(side=tk.LEFT)

        out_frame = ttk.LabelFrame(self.work_area, text="Output")
        out_frame.pack(fill=tk.BOTH, expand=True)
        self.output = scrolledtext.ScrolledText(out_frame, wrap=tk.WORD, height=8)
        self.output.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def on_show(self) -> None:
        # Keep the prefilled tasks file honest: if it's still empty (e.g. a
        # config change cleared it), fall back to the resolved default.
        if not self.tasks_file_var.get().strip():
            self.tasks_file_var.set(default_task_file_name())
        self.refresh_list()

    # ------------------------------------------------------------------
    def base_argv(self) -> list[str]:
        argv: list[str] = []
        if self.app_state.config_path:
            argv += ["--config", self.app_state.config_path]
            # Pass the active component so the CLI resolves the component's
            # tasks_file when the picker is left blank (flag still wins below).
            argv += ["--component", self.app_state.component]
        argv += ["--error-format", self.app_state.error_format]
        argv += ["--input-file", self.app_state.input_file]
        return argv

    def tasks_file_args(self) -> list[str]:
        value = self.tasks_file_var.get().strip()
        return ["--tasks-file", value] if value else []

    def run(self, argv: list[str], *, reload: bool = False) -> tuple[int, str]:
        self.output.insert(tk.END, f"$ changelogmanager {' '.join(argv)}\n")
        self.output.see(tk.END)
        self.output.update_idletasks()
        code, text = run_cli(argv)
        self.output.insert(tk.END, text + f"\n[exit {code}]\n\n")
        self.output.see(tk.END)
        self.status(f"tasks finished (exit {code})")
        if reload:
            self.controller.reload()
        return code, text

    # ------------------------------------------------------------------
    def refresh_list(self) -> None:
        for child in self.list_body.winfo_children():
            child.destroy()
        argv = self.base_argv() + ["tasks", "list"] + self.tasks_file_args()
        code, text = run_cli(argv)
        if code != 0:
            ttk.Label(
                self.list_body,
                text=text.strip().splitlines()[0] if text.strip() else "list failed",
                foreground="#a00",
            ).pack(anchor="w")
            return
        rows = [m for m in (_TASK_LINE.match(line) for line in text.splitlines()) if m]
        if not rows:
            ttk.Label(self.list_body, text="(no tasks)").pack(anchor="w")
            return
        for match in rows:
            line_no, mark, change_type, body = match.groups()
            checked = mark.strip().lower() == "x"
            row = ttk.Frame(self.list_body)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(
                row,
                text=f"[{'x' if checked else ' '}] {change_type}: {body}",
                wraplength=620,
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)
            verb = "Uncheck" if checked else "Check"
            ttk.Button(
                row,
                text=verb,
                width=8,
                command=partial(self.toggle, line_no, checked),
            ).pack(side=tk.LEFT, padx=4)

    def toggle(self, line_no: str, checked: bool) -> None:
        sub = "uncheck" if checked else "check"
        argv = self.base_argv() + ["tasks", sub, line_no] + self.tasks_file_args()
        self.run(argv)
        self.refresh_list()

    def add_task(self) -> None:
        message = self.add_message_var.get().strip()
        if not message:
            self.status("Enter a task message before adding.")
            return
        argv = (
            self.base_argv()
            + ["tasks", "add", self.add_type_var.get(), message]
            + self.tasks_file_args()
        )
        self.run(argv)
        self.add_message_var.set("")
        self.refresh_list()

    def validate(self) -> None:
        argv = self.base_argv() + ["tasks", "validate"] + self.tasks_file_args()
        self.run(argv)

    def promote(self) -> None:
        argv = self.base_argv() + ["tasks", "promote"] + self.tasks_file_args()
        if self.keep_var.get():
            argv.append("--keep")
        if self.app_state.dry_run:
            argv.append("--dry-run")
        self.run(argv, reload=not self.app_state.dry_run)
        self.refresh_list()
