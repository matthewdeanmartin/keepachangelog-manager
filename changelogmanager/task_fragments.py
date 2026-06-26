# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Task fragments: rich, per-ticket task files assembled into ``TASKS.md``.

A *task fragment* is one ticket in ``tickets/``, written as **rigid structured
markdown on top** (a small fixed DOM: an H1 title plus a ``- **Key:** value``
bullet list) and **freeform markdown on the bottom**, separated by the first
column-0 ``---`` that is not inside a fenced code block.

This module is intentionally dependency-free (stdlib only) and *totally
parsing*: any text file is a valid fragment. The worst case is an
``uncategorized`` fragment whose body is the whole file and whose head fields
are empty, carrying lint warnings — it never raises on content.

See ``spec/TASK_FRAGMENTS_AND_UI.md``. The format reuses the Keep a Changelog
categories from :mod:`changelogmanager.change_types` and adds non-shipping
categories plus arbitrary custom fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from changelogmanager.change_types import ALL_CATEGORIES
from changelogmanager.tasks import TaskItem, canonical_change_type

# A metadata bullet in the head: ``- **Key:** value``. The colon may live inside
# the bold markers (``**Key:**``) or just after them (``**Key**:``); both parse.
# The value may be empty.
META_RE = re.compile(
    r"^\s*[-*]\s+\*\*(?P<key>[^*]+?)\s*:?\s*\*\*\s*:?\s*(?P<value>.*?)\s*$"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})")
DIVIDER_RE = re.compile(r"^---+\s*$")

# Default discovery order for the tickets directory.
TICKETS_DIR_CANDIDATES = ("tickets", ".changelogmanager/tickets")

# Known head keys (besides the H1 title). Anything else becomes a custom field.
KNOWN_KEYS = {
    "category": "category",
    "status": "status",
    "tracker": "tracker",
    "labels": "labels",
    "assignees": "assignees",
    "milestone": "milestone",
}

KNOWN_STATUSES = (
    "proposed",
    "accepted",
    "in-progress",
    "blocked",
    "done",
    "wontfix",
)


@dataclass
class TaskFragment:
    """One parsed task fragment.

    A superset of :class:`changelogmanager.tasks.TaskItem`: a fragment with only
    a title and a category degrades to a single ``- [ ]`` line via
    :meth:`to_task_item`.
    """

    task_id: str
    title: str
    category: str = "uncategorized"
    status: str = "proposed"
    tracker: str | None = None
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    milestone: str | None = None
    custom: dict[str, str] = field(default_factory=dict)
    body_md: str = ""
    source_file: Path | None = None
    lint: list[str] = field(default_factory=list)

    @property
    def checked(self) -> bool:
        """A fragment is "done" exactly when its status says so."""

        return self.status.strip().lower() == "done"

    def to_task_item(self) -> TaskItem:
        """Bridge to the flat ``TASKS.md`` model used by ``tasks promote``."""

        change_type = canonical_change_type(self.category)
        return TaskItem(
            change_type=change_type,
            text=self.title,
            checked=self.checked,
            done_date=self.custom.get("Done") or self.custom.get("Done Date") or None,
            source_file=self.source_file or Path(self.task_id),
            line=0,
            raw_line="",
        )


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def split_head_body(text: str) -> tuple[str, str]:
    """Split fragment text into (head, body) on the first real ``---`` divider.

    A ``---`` inside a fenced code block does **not** count, so a head can carry
    example code that contains horizontal rules.
    """

    lines = text.splitlines()
    fence: str | None = None
    for index, line in enumerate(lines):
        fence_match = FENCE_RE.match(line)
        if fence_match:
            token = fence_match.group(2)[0]
            if fence is None:
                fence = token
            elif token == fence:
                fence = None
            continue
        if fence is None and DIVIDER_RE.match(line):
            head = "\n".join(lines[:index])
            body = "\n".join(lines[index + 1 :])
            return head, body
    # No divider: the whole file is the head (a freeform note with no body).
    return text, ""


def _parse_title(head_lines: list[str], stem: str) -> tuple[str, str, list[str]]:
    """Return (task_id, title) from the first H1, plus lint warnings.

    Convention is ``# <id> — <summary>``. If the id prefix matches the filename
    stem we strip it from the title; a mismatch is a lint warning, not an error.
    """

    lint: list[str] = []
    for line in head_lines:
        heading = HEADING_RE.match(line)
        if heading and len(heading.group(1)) == 1:
            raw = heading.group(2).strip()
            # Try to peel a leading "<id> — " / "<id> - " / "<id>: " prefix.
            match = re.match(r"^(?P<id>\S+)\s*[—:\-]\s+(?P<rest>.+)$", raw)
            if match:
                head_id = match.group("id")
                title = match.group("rest").strip()
                if stem and head_id != stem:
                    lint.append(
                        f"H1 id {head_id!r} does not match filename stem {stem!r}"
                    )
                return head_id, title, lint
            return stem, raw, lint
    lint.append("no H1 title found; using filename stem as title")
    return stem, stem, lint


def parse_fragment_text(
    text: str, *, stem: str = "", source_file: Path | None = None
) -> TaskFragment:
    """Parse fragment text. Total: never raises on content."""

    head, body = split_head_body(text)
    head_lines = head.splitlines()

    task_id, title, lint = _parse_title(head_lines, stem)

    fragment = TaskFragment(
        task_id=task_id, title=title, body_md=body, source_file=source_file
    )
    fragment.lint.extend(lint)

    in_fence = False
    saw_category = False
    for line in head_lines:
        fence_match = FENCE_RE.match(line)
        if fence_match:
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        meta = META_RE.match(line)
        if not meta:
            continue
        key = meta.group("key").strip()
        value = meta.group("value").strip()
        lowered = key.lower()
        if lowered in KNOWN_KEYS:
            _assign_known(fragment, lowered, value)
            if lowered == "category":
                saw_category = True
        else:
            # Unknown keys are preserved verbatim (casing + insertion order).
            fragment.custom[key] = value

    if not saw_category:
        fragment.lint.append("no Category field; treated as 'uncategorized'")
    elif fragment.category not in ALL_CATEGORIES and not canonical_change_type(
        fragment.category
    ):
        fragment.lint.append(
            f"unknown category {fragment.category!r}; treated as non-shipping"
        )

    if fragment.status not in KNOWN_STATUSES:
        fragment.lint.append(
            f"unknown status {fragment.status!r}; expected one of "
            f"{', '.join(KNOWN_STATUSES)}"
        )

    return fragment


def _assign_known(fragment: TaskFragment, key: str, value: str) -> None:
    if key == "category":
        fragment.category = value.strip().lower() or "uncategorized"
    elif key == "status":
        fragment.status = value.strip().lower() or "proposed"
    elif key == "tracker":
        fragment.tracker = value or None
    elif key == "labels":
        fragment.labels = _split_csv(value)
    elif key == "assignees":
        fragment.assignees = [item.lstrip("@") for item in _split_csv(value)]
    elif key == "milestone":
        fragment.milestone = value or None


def parse_fragment_file(path: Path) -> TaskFragment:
    """Parse a fragment from disk. Missing files yield an empty fragment."""

    if not path.is_file():
        fragment = TaskFragment(task_id=path.stem, title=path.stem, source_file=path)
        fragment.lint.append(f"{path}: file not found")
        return fragment
    text = path.read_text(encoding="UTF-8")
    return parse_fragment_text(text, stem=path.stem, source_file=path)


def _is_ignored(path: Path) -> bool:
    name = path.name
    return name.startswith("_") or name.lower().startswith("readme")


def discover_tickets_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    for candidate in TICKETS_DIR_CANDIDATES:
        path = Path(candidate)
        if path.is_dir():
            return path
    return Path(TICKETS_DIR_CANDIDATES[0])


def read_fragments(tickets_dir: Path) -> list[TaskFragment]:
    """Parse every fragment in ``tickets_dir``, sorted by filename."""

    if not tickets_dir.is_dir():
        return []
    fragments: list[TaskFragment] = []
    for path in sorted(tickets_dir.glob("*.md")):
        if _is_ignored(path):
            continue
        fragments.append(parse_fragment_file(path))
    return fragments


def render_fragment(fragment: TaskFragment) -> str:
    """Render a fragment back to its on-disk form (lossless round-trip).

    Preserves the title, every known field that is set, every custom field
    (casing + insertion order), and the body verbatim.
    """

    head: list[str] = [f"# {fragment.task_id} — {fragment.title}", ""]
    head.append(f"- **Category:** {fragment.category}")
    head.append(f"- **Status:** {fragment.status}")
    if fragment.tracker:
        head.append(f"- **Tracker:** {fragment.tracker}")
    if fragment.labels:
        head.append(f"- **Labels:** {', '.join(fragment.labels)}")
    if fragment.assignees:
        assignees = ", ".join(f"@{name}" for name in fragment.assignees)
        head.append(f"- **Assignees:** {assignees}")
    if fragment.milestone:
        head.append(f"- **Milestone:** {fragment.milestone}")
    for key, value in fragment.custom.items():
        head.append(f"- **{key}:** {value}")

    rendered = "\n".join(head) + "\n"
    body = fragment.body_md.strip("\n")
    if body:
        rendered += "\n---\n\n" + body + "\n"
    return rendered


def lint_fragments(fragments: list[TaskFragment]) -> list[str]:
    """Flatten per-fragment lint warnings into ``path: message`` lines."""

    messages: list[str] = []
    for fragment in fragments:
        where = str(fragment.source_file or fragment.task_id)
        for warning in fragment.lint:
            messages.append(f"{where}: {warning}")
    return messages


# ----------------------------------------------------------------------
# assembly into TASKS.md
# ----------------------------------------------------------------------

# Top-level grouping order for the assembled TASKS.md. "blocked" gets its own
# group for visibility; unknown statuses sort last under their own heading.
STATUS_ORDER = ("in-progress", "blocked", "proposed", "accepted", "done", "wontfix")

# Sentinel marking the start of a hand-maintained epilogue in TASKS.md. Content
# after the last such line is preserved verbatim across rebuilds.
EPILOGUE_SENTINEL = "<!-- task-fragments:epilogue -->"

ASSEMBLED_HEADER = (
    "# Tasks\n"
    "\n"
    "> Generated from `tickets/` by `changelogmanager tasks assemble`.\n"
    "> Do not edit the structured sections by hand — edit the fragment in\n"
    "> `tickets/` and re-run the assembler.\n"
)


def _category_sort_key(category: str) -> tuple[int, str]:
    keys = list(ALL_CATEGORIES.keys())
    if category in keys:
        return (keys.index(category), category)
    return (len(keys), category)


def _status_sort_key(status: str) -> tuple[int, str]:
    if status in STATUS_ORDER:
        return (STATUS_ORDER.index(status), status)
    return (len(STATUS_ORDER), status)


def _heading_for(category: str) -> str:
    known = ALL_CATEGORIES.get(category)
    if known:
        return known.title
    canonical = canonical_change_type(category)
    if canonical and canonical in ALL_CATEGORIES:
        return ALL_CATEGORIES[canonical].title
    return category.title() if category else "Uncategorized"


def _grouped(
    fragments: list[TaskFragment],
) -> list[tuple[str, list[tuple[str, list[TaskFragment]]]]]:
    """Group fragments by status, then category, in deterministic order."""

    by_status: dict[str, dict[str, list[TaskFragment]]] = {}
    for fragment in fragments:
        status = fragment.status or "proposed"
        category = fragment.category or "uncategorized"
        by_status.setdefault(status, {}).setdefault(category, []).append(fragment)

    grouped: list[tuple[str, list[tuple[str, list[TaskFragment]]]]] = []
    for status in sorted(by_status, key=_status_sort_key):
        cats = by_status[status]
        cat_list: list[tuple[str, list[TaskFragment]]] = []
        for category in sorted(cats, key=_category_sort_key):
            items = sorted(cats[category], key=lambda frag: frag.task_id)
            cat_list.append((category, items))
        grouped.append((status, cat_list))
    return grouped


def _shift_headings(body: str, by: int) -> str:
    """Increase the depth of every ATX heading in ``body`` by ``by`` levels."""

    out: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        match = HEADING_RE.match(line) if not in_fence else None
        if match:
            depth = min(len(match.group(1)) + by, 6)
            out.append("#" * depth + " " + match.group(2))
        else:
            out.append(line)
    return "\n".join(out)


def _extract_epilogue(existing: str | None) -> str:
    if not existing or EPILOGUE_SENTINEL not in existing:
        return ""
    _, _, tail = existing.rpartition(EPILOGUE_SENTINEL)
    return tail.strip("\n")


def render_tasks_md(
    fragments: list[TaskFragment],
    *,
    rich: bool = False,
    existing: str | None = None,
) -> str:
    """Render the assembled ``TASKS.md``.

    Default output is the flat ``spec/tasks.md`` schema (KAC ``##`` headings with
    ``- [ ]`` / ``- [x]`` items) so ``tasks promote`` keeps working unchanged.
    ``rich=True`` adds a Status grouping plus the depth-shifted free body.
    """

    grouped = _grouped(fragments)
    lines: list[str] = [ASSEMBLED_HEADER.rstrip("\n"), ""]

    if rich:
        for status, categories in grouped:
            lines.append(f"## {status.title()}")
            lines.append("")
            for category, items in categories:
                lines.append(f"### {_heading_for(category)}")
                lines.append("")
                for fragment in items:
                    lines.extend(_render_rich_item(fragment))
                    lines.append("")
    else:
        # Flat schema: one "## <Category>" section, "- [ ]"/"- [x]" per task.
        # Collapse across statuses so the file stays promote-compatible.
        by_category: dict[str, list[TaskFragment]] = {}
        for fragment in fragments:
            by_category.setdefault(fragment.category or "uncategorized", []).append(
                fragment
            )
        for category in sorted(by_category, key=_category_sort_key):
            lines.append(f"## {_heading_for(category)}")
            lines.append("")
            for fragment in sorted(by_category[category], key=lambda f: f.task_id):
                lines.append(_render_flat_item(fragment))
            lines.append("")

    body = "\n".join(lines).rstrip() + "\n"

    epilogue = _extract_epilogue(existing)
    body += f"\n{EPILOGUE_SENTINEL}\n"
    if epilogue:
        body += "\n" + epilogue + "\n"
    return body


def _render_flat_item(fragment: TaskFragment) -> str:
    marker = "x" if fragment.checked else " "
    done = fragment.custom.get("Done") or fragment.custom.get("Done Date")
    suffix = f" <!-- done: {done} -->" if (fragment.checked and done) else ""
    return f"- [{marker}] {fragment.title}{suffix}"


def _render_rich_item(fragment: TaskFragment) -> list[str]:
    marker = "x" if fragment.checked else " "
    meta: list[str] = [f"[{fragment.task_id}]"]
    if fragment.tracker:
        meta.append(fragment.tracker)
    if fragment.assignees:
        meta.append(" ".join(f"@{name}" for name in fragment.assignees))
    summary = f"- [{marker}] **{fragment.title}** — {' · '.join(meta)}"
    out = [summary]
    body = fragment.body_md.strip("\n")
    if body:
        shifted = _shift_headings(body, by=2)
        out.append("")
        for line in shifted.splitlines():
            out.append(f"  {line}" if line else "")
    return out


def assemble_tasks_file(
    tickets_dir: Path,
    output_path: Path,
    *,
    rich: bool = False,
    dry_run: bool = False,
) -> tuple[str, list[str]]:
    """Assemble ``tickets_dir`` into ``output_path``.

    Returns ``(rendered_text, lint_messages)``. Writing is skipped on
    ``dry_run`` or when the output is byte-identical (a no-op rebuild).
    """

    fragments = read_fragments(tickets_dir)
    existing = (
        output_path.read_text(encoding="UTF-8") if output_path.is_file() else None
    )
    rendered = render_tasks_md(fragments, rich=rich, existing=existing)
    lint = lint_fragments(fragments)
    if not dry_run and rendered != existing:
        output_path.write_text(rendered, encoding="UTF-8")
    return rendered, lint


def changelog_entries(
    fragments: list[TaskFragment],
) -> list[tuple[str, str]]:
    """``(change_type, text)`` pairs eligible for a released changelog.

    Only ``done`` fragments whose category ships are returned; non-shipping and
    unknown categories are excluded.
    """

    from changelogmanager.change_types import ships_to_changelog  # noqa: PLC0415

    entries: list[tuple[str, str]] = []
    for fragment in fragments:
        if not fragment.checked:
            continue
        change_type = canonical_change_type(fragment.category)
        if change_type and ships_to_changelog(change_type):
            entries.append((change_type, fragment.title))
    return entries


def next_ticket_id(tickets_dir: Path) -> str:
    """Next zero-padded numeric ticket id (``0001``, ``0002``, …)."""

    highest = 0
    if tickets_dir.is_dir():
        for path in tickets_dir.glob("*.md"):
            match = re.match(r"^(\d+)", path.stem)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"{highest + 1:04d}"


def scaffold_fragment(
    tickets_dir: Path, summary: str, *, category: str = "added"
) -> Path:
    """Create ``tickets/NNNN-<slug>.md`` with a valid empty head."""

    from changelogmanager.fragments import slugify  # noqa: PLC0415

    ticket_id = next_ticket_id(tickets_dir)
    slug = slugify(summary)
    path = tickets_dir / f"{ticket_id}-{slug}.md"
    fragment = TaskFragment(
        task_id=f"{ticket_id}-{slug}",
        title=summary.strip(),
        category=category.strip().lower(),
        status="proposed",
    )
    tickets_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(render_fragment(fragment), encoding="UTF-8")
    return path
