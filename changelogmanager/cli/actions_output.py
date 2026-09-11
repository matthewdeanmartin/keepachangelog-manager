"""Optional GitHub Actions step outputs without JSON extraction in shell."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import changelogmanager.llvm_diagnostics as logging


def output_file() -> Path:
    value = os.environ.get("GITHUB_OUTPUT")
    if not value or not Path(value).is_file():
        raise logging.Error(
            message="--github-output requires an existing GITHUB_OUTPUT file supplied by GitHub Actions"
        )
    return Path(value)


def write_outputs(path: Path, values: dict[str, Any]) -> None:
    lines = []
    for key in (
        "version",
        "branch",
        "component",
        "tag_name",
        "commit_sha",
        "pr_number",
        "html_url",
    ):
        value = values.get(key)
        if value is None:
            continue
        if "\n" in str(value) or "\r" in str(value):
            raise logging.Error(message=f"Invalid multiline GitHub output: {key}")
        lines.append(f"{key}={value}\n")
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("".join(lines))
