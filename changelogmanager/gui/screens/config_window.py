# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Modal configuration editor.

Presents the same fields ``config init`` collects (versioning scheme, enforce
preamble, default component name/changelog) as a form instead of inquirer prompts,
and writes through the same helpers so the on-disk shape is identical.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

from changelogmanager.cli.prompts import component_defaults
from changelogmanager.config import (
    VERSIONING_SCHEMES,
    config_format_from_path,
    default_config_path_for_format,
    get_effective_configuration,
    write_configuration,
)
from changelogmanager.services import build_updated_config

if TYPE_CHECKING:  # pragma: no cover - typing only
    from changelogmanager.gui.app import AppController


def open_config_window(controller: AppController) -> None:
    """Opens the modal config editor against the controller's current config."""

    ConfigWindow(controller)


class ConfigWindow(tk.Toplevel):  # pylint: disable=too-many-instance-attributes
    """Toplevel form for editing changelogmanager configuration."""

    def __init__(self, controller: AppController) -> None:
        super().__init__(controller.root)
        self.controller = controller
        self.title("Configuration")
        self.transient(controller.root)
        self.grab_set()
        self.resizable(False, False)

        existing_path = controller.state.config_path
        if existing_path and not Path(existing_path).is_file():
            existing_path = None
        self._existing_path = existing_path
        config = get_effective_configuration(existing_path)
        name, changelog = component_defaults(config)

        scheme = str(
            config.get("project", {}).get("versioning", {}).get("scheme", "semver")
        )
        enforce = bool(
            config.get("project", {}).get("validation", {}).get("enforce_preamble", False)
        )

        labels = {data["label"]: key for key, data in VERSIONING_SCHEMES.items()}
        self._label_to_scheme = labels

        body = ttk.Frame(self, padding=10)
        body.pack(fill=tk.BOTH, expand=True)

        self.format_var = tk.StringVar(
            value="pyproject.toml" if (
                existing_path and config_format_from_path(existing_path) == "pyproject"
            ) else "changelogmanager.toml"
        )
        self.scheme_var = tk.StringVar(
            value=VERSIONING_SCHEMES.get(scheme, VERSIONING_SCHEMES["semver"])["label"]
        )
        self.enforce_var = tk.BooleanVar(value=enforce)
        self.name_var = tk.StringVar(value=name)
        self.changelog_var = tk.StringVar(value=changelog)

        self._row(body, "Config file:", ttk.Combobox(
            body, textvariable=self.format_var, state="readonly",
            values=["pyproject.toml", "changelogmanager.toml"], width=28,
        ))
        self._row(body, "Versioning scheme:", ttk.Combobox(
            body, textvariable=self.scheme_var, state="readonly",
            values=list(labels.keys()), width=28,
        ))
        self._row(body, "Enforce preamble:", ttk.Checkbutton(body, variable=self.enforce_var))
        self._row(body, "Default component:", ttk.Entry(body, textvariable=self.name_var, width=30))
        self._row(body, "Default changelog:", ttk.Entry(body, textvariable=self.changelog_var, width=30))

        buttons = ttk.Frame(body)
        buttons.grid(row=99, column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(buttons, text="Save", command=self._save).pack(side=tk.RIGHT)

        self._base_config = config

    def _row(self, parent, label, widget) -> None:  # type: ignore[no-untyped-def]
        index = getattr(self, "_next_row", 0)
        ttk.Label(parent, text=label).grid(row=index, column=0, sticky="w", pady=3, padx=(0, 8))
        widget.grid(row=index, column=1, sticky="w", pady=3)
        self._next_row = index + 1

    def _save(self) -> None:
        config_format = (
            "pyproject" if self.format_var.get() == "pyproject.toml" else "toml"
        )
        answers: dict[str, object] = {
            "config_format": config_format,
            "versioning_scheme": self._label_to_scheme[self.scheme_var.get()],
            "enforce_preamble": bool(self.enforce_var.get()),
            "component_name": self.name_var.get().strip() or "default",
            "changelog_path": self.changelog_var.get().strip() or "CHANGELOG.md",
            "prompted_components": True,
        }
        updated = build_updated_config(self._base_config, answers)

        if self._existing_path and config_format_from_path(self._existing_path) == config_format:
            target = self._existing_path
        else:
            target = default_config_path_for_format(config_format)

        try:
            write_configuration(str(target), updated)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            messagebox.showerror("Config save failed", str(getattr(exc, "message", exc)))
            return

        self.controller.config_var.set(str(target))
        self.controller.reload()
        self.controller.set_status(f"Saved config: {target}")
        self.destroy()
