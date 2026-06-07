# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Markdown task file support."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import CATEGORIES, TYPES_OF_CHANGE

TASK_FILE_CANDIDATES = ("TASKS.md", ".changelogmanager/TASKS.md")
DONE_RE = re.compile(r"\s*<!--\s*done:\s*(\d{4}-\d{2}-\d{2})\s*-->\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TASK_RE = re.compile(r"^(\s*)-\s+\[([ xX])\]\s+(.*?)\s*$")


@dataclass(frozen=True)
class TaskItem:
    change_type: str | None
    text: str
    checked: bool
    done_date: str | None
    source_file: Path
    line: int
    raw_line: str


def canonical_change_type(value: str) -> str | None:
    normalized = value.strip().lower()
    if normalized in CATEGORIES:
        return normalized
    singular = normalized[:-1] if normalized.endswith("s") else normalized
    if singular in CATEGORIES:
        return singular
    for key, category in CATEGORIES.items():
        if normalized == category.title.lower():
            return key
    return None


def discover_task_file(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    for candidate in TASK_FILE_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return path
    return Path(TASK_FILE_CANDIDATES[0])


def strip_done_metadata(text: str) -> tuple[str, str | None]:
    match = DONE_RE.search(text)
    if not match:
        return text.strip(), None
    return text[: match.start()].strip(), match.group(1)


def parse_task_file(path: Path) -> list[TaskItem]:
    if not path.is_file():
        return []
    current_type: str | None = None
    tasks: list[TaskItem] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="UTF-8").splitlines(), start=1
    ):
        heading_match = HEADING_RE.match(raw_line)
        if heading_match:
            current_type = canonical_change_type(heading_match.group(2))
            continue
        task_match = TASK_RE.match(raw_line)
        if not task_match:
            continue
        text, done_date = strip_done_metadata(task_match.group(3))
        tasks.append(
            TaskItem(
                change_type=current_type,
                text=text,
                checked=task_match.group(2).lower() == "x",
                done_date=done_date,
                source_file=path,
                line=line_number,
                raw_line=raw_line,
            )
        )
    return tasks


def ensure_task_file(path: Path) -> None:
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Tasks\n\n", encoding="UTF-8")


def add_task(path: Path, change_type: str, text: str) -> None:
    if change_type not in TYPES_OF_CHANGE:
        raise logging.Error(
            file_path=str(path), message=f"Unknown change type '{change_type}'"
        )
    if not text.strip():
        raise logging.Error(file_path=str(path), message="Task text must not be empty")

    ensure_task_file(path)
    lines = path.read_text(encoding="UTF-8").splitlines()
    heading = f"## {change_type.title()}"
    insert_at = None
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match and canonical_change_type(match.group(2)) == change_type:
            insert_at = index + 1
            while insert_at < len(lines) and not HEADING_RE.match(lines[insert_at]):
                insert_at += 1
            break
    if insert_at is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([heading, ""])
        insert_at = len(lines)

    lines.insert(insert_at, f"- [ ] {text.strip()}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="UTF-8")


def resolve_task_index(tasks: list[TaskItem], selector: str) -> int:
    if selector.isdigit():
        line = int(selector)
        for index, task in enumerate(tasks):
            if task.line == line:
                return index
        raise logging.Error(message=f"No task found on line {line}")
    matches = [index for index, task in enumerate(tasks) if task.text == selector]
    if not matches:
        raise logging.Error(message=f"No task found matching {selector!r}")
    if len(matches) > 1:
        raise logging.Error(
            message=f"Task selector {selector!r} matched multiple tasks"
        )
    return matches[0]


def set_task_checked(
    path: Path, selector: str, *, checked: bool, done_date_source: str = "today"
) -> TaskItem:
    lines = path.read_text(encoding="UTF-8").splitlines()
    tasks = parse_task_file(path)
    task = tasks[resolve_task_index(tasks, selector)]
    line_index = task.line - 1
    task_match = TASK_RE.match(lines[line_index])
    if not task_match:
        raise logging.Error(
            file_path=str(path), message=f"Line {task.line} is not a task"
        )

    text, _done = strip_done_metadata(task_match.group(3))
    marker = "x" if checked else " "
    suffix = ""
    if checked and done_date_source == "today":
        suffix = f" <!-- done: {date.today().isoformat()} -->"
    lines[line_index] = f"{task_match.group(1)}- [{marker}] {text}{suffix}"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="UTF-8")
    return parse_task_file(path)[
        resolve_task_index(parse_task_file(path), str(task.line))
    ]


def validate_tasks(tasks: list[TaskItem], path: Path) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str | None, str]] = set()
    for task in tasks:
        if task.change_type is None:
            errors.append(
                f"{path}:{task.line}: task is not under a known change-type heading"
            )
        if not task.text:
            errors.append(f"{path}:{task.line}: task text must not be empty")
        if task.done_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", task.done_date):
            errors.append(f"{path}:{task.line}: done date must be YYYY-MM-DD")
        key = (task.change_type, task.text)
        if key in seen:
            errors.append(f"{path}:{task.line}: duplicate task text")
        seen.add(key)
    return errors


def completed_entries(tasks: list[TaskItem]) -> list[tuple[str, str, int]]:
    return [
        (task.change_type, task.text, task.line)
        for task in tasks
        if task.checked and task.change_type is not None and task.text
    ]


def remove_completed_tasks(path: Path, promoted_lines: set[int]) -> None:
    lines = path.read_text(encoding="UTF-8").splitlines()
    kept = [
        line
        for line_number, line in enumerate(lines, start=1)
        if line_number not in promoted_lines
    ]
    path.write_text("\n".join(kept).rstrip() + "\n", encoding="UTF-8")
