# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Extended unit tests for task_fragments.py — covering paths not exercised by
the primary ``test_task_fragments.py`` test module.

Focuses on:
* ``next_ticket_id`` and ``scaffold_fragment``
* ``render_tasks_md`` rich mode (status groupings, body expansion)
* ``_shift_headings`` via the rich render path
* ``_extract_epilogue`` corner-cases
* ``discover_tickets_dir`` resolution logic
* ``TaskFragment.to_task_item`` bridge
* ``lint_fragments`` helper
* ``changelog_entries`` edge-cases
* heading-shift through fence blocks
* Empty / minimal fragment assembly
"""

from __future__ import annotations

from pathlib import Path

import pytest

from changelogmanager.task_fragments import (
    EPILOGUE_SENTINEL,
    TaskFragment,
    assemble_tasks_file,
    changelog_entries,
    discover_tickets_dir,
    lint_fragments,
    next_ticket_id,
    parse_fragment_file,
    parse_fragment_text,
    read_fragments,
    render_fragment,
    render_tasks_md,
    scaffold_fragment,
    split_head_body,
)

# ---------------------------------------------------------------------------
# next_ticket_id
# ---------------------------------------------------------------------------


def test_next_ticket_id_empty_dir(tmp_path):
    tickets = tmp_path / "tickets"
    tickets.mkdir()
    assert next_ticket_id(tickets) == "0001"


def test_next_ticket_id_absent_dir(tmp_path):
    # Non-existent directory -> starts at 0001.
    assert next_ticket_id(tmp_path / "nope") == "0001"


def test_next_ticket_id_with_existing_files(tmp_path):
    tickets = tmp_path / "tickets"
    tickets.mkdir()
    (tickets / "0003-foo.md").write_text("", encoding="UTF-8")
    (tickets / "0007-bar.md").write_text("", encoding="UTF-8")
    # Next after 7 -> 8.
    assert next_ticket_id(tickets) == "0008"


def test_next_ticket_id_ignores_non_numeric_stems(tmp_path):
    tickets = tmp_path / "tickets"
    tickets.mkdir()
    (tickets / "README.md").write_text("", encoding="UTF-8")
    (tickets / "abc.md").write_text("", encoding="UTF-8")
    assert next_ticket_id(tickets) == "0001"


# ---------------------------------------------------------------------------
# scaffold_fragment
# ---------------------------------------------------------------------------


def test_scaffold_fragment_creates_file(tmp_path):
    tickets = tmp_path / "tickets"
    path = scaffold_fragment(tickets, "Add login screen", category="added")
    assert path.is_file()
    assert "0001" in path.name
    text = path.read_text(encoding="UTF-8")
    assert "Add login screen" in text
    assert "**Category:** added" in text
    assert "**Status:** proposed" in text


def test_scaffold_fragment_auto_increments(tmp_path):
    tickets = tmp_path / "tickets"
    first = scaffold_fragment(tickets, "First", category="fixed")
    second = scaffold_fragment(tickets, "Second", category="added")
    assert first.name != second.name
    first_id = int(first.name[:4])
    second_id = int(second.name[:4])
    assert second_id == first_id + 1


def test_scaffold_fragment_round_trips(tmp_path):
    tickets = tmp_path / "tickets"
    path = scaffold_fragment(tickets, "My task", category="changed")
    frag = parse_fragment_file(path)
    assert frag.title == "My task"
    assert frag.category == "changed"
    assert frag.status == "proposed"


# ---------------------------------------------------------------------------
# discover_tickets_dir
# ---------------------------------------------------------------------------


def test_discover_tickets_dir_explicit():
    from pathlib import PurePosixPath

    result = discover_tickets_dir(explicit="/some/path")
    # Compare using Path objects (handles Windows backslash normalisation).
    assert result == Path("/some/path")


def test_discover_tickets_dir_uses_existing_tickets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tickets").mkdir()
    result = discover_tickets_dir()
    assert result == Path("tickets")


def test_discover_tickets_dir_fallback_when_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Neither candidate exists -> falls back to the first candidate name.
    result = discover_tickets_dir()
    assert result == Path("tickets")


# ---------------------------------------------------------------------------
# parse_fragment_file edge-cases
# ---------------------------------------------------------------------------


def test_parse_fragment_file_missing_produces_lint(tmp_path):
    missing = tmp_path / "0001-ghost.md"
    frag = parse_fragment_file(missing)
    assert frag.task_id == "0001-ghost"
    assert any("not found" in w for w in frag.lint)


def test_parse_fragment_file_real_file(tmp_path):
    path = tmp_path / "0042-hello.md"
    path.write_text(
        "# 0042-hello — Hello world\n\n- **Category:** added\n", encoding="UTF-8"
    )
    frag = parse_fragment_file(path)
    assert frag.task_id == "0042-hello"
    assert frag.title == "Hello world"
    assert frag.lint == []


# ---------------------------------------------------------------------------
# TaskFragment.checked property
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,expected",
    [
        ("done", True),
        ("DONE", True),
        (" done ", True),
        ("proposed", False),
        ("in-progress", False),
        ("wontfix", False),
    ],
)
def test_checked_property(status, expected):
    frag = TaskFragment(task_id="t", title="T", status=status)
    assert frag.checked is expected


# ---------------------------------------------------------------------------
# TaskFragment.to_task_item bridge
# ---------------------------------------------------------------------------


def test_to_task_item_added_done(tmp_path):
    frag = parse_fragment_text(
        "# x — X\n- **Category:** added\n- **Status:** done\n", stem="x"
    )
    frag.source_file = tmp_path / "x.md"
    item = frag.to_task_item()
    assert item.change_type == "added"
    assert item.text == "X"
    assert item.checked is True


def test_to_task_item_done_date_from_custom():
    frag = parse_fragment_text(
        "# x — X\n- **Category:** fixed\n- **Status:** done\n- **Done:** 2026-01-15\n",
        stem="x",
    )
    item = frag.to_task_item()
    assert item.done_date == "2026-01-15"


def test_to_task_item_uncategorized_still_works():
    frag = parse_fragment_text("# x — X\n", stem="x")
    item = frag.to_task_item()
    # uncategorized -> canonical_change_type returns None
    assert item.change_type is None


# ---------------------------------------------------------------------------
# lint_fragments helper
# ---------------------------------------------------------------------------


def test_lint_fragments_empty():
    assert lint_fragments([]) == []


def test_lint_fragments_includes_source_path(tmp_path):
    path = tmp_path / "0001-bad.md"
    path.write_text("just prose\n", encoding="UTF-8")
    frag = parse_fragment_file(path)
    messages = lint_fragments([frag])
    assert messages  # at least one warning
    assert all(str(path) in m for m in messages)


def test_lint_fragments_multiple_warnings_per_fragment():
    # No H1, no category -> two warnings minimum.
    frag = parse_fragment_text("just prose\n", stem="x")
    messages = lint_fragments([frag])
    assert len(messages) >= 2


# ---------------------------------------------------------------------------
# split_head_body -- tilde fence variant
# ---------------------------------------------------------------------------


def test_divider_inside_tilde_fence_does_not_split():
    text = "# x — X\n\n- **Category:** added\n\n~~~\n---\n~~~\n\n---\n\nreal body\n"
    head, body = split_head_body(text)
    assert "real body" in body
    assert "~~~" in head


# ---------------------------------------------------------------------------
# render_tasks_md -- rich mode
# ---------------------------------------------------------------------------


def test_render_tasks_md_rich_has_status_headings():
    frags = [
        parse_fragment_text(
            "# a — Alpha\n- **Category:** added\n- **Status:** in-progress\n", stem="a"
        ),
        parse_fragment_text(
            "# b — Beta\n- **Category:** fixed\n- **Status:** done\n", stem="b"
        ),
    ]
    output = render_tasks_md(frags, rich=True)
    assert "## In-Progress" in output
    assert "## Done" in output
    assert "Alpha" in output
    assert "Beta" in output


def test_render_tasks_md_rich_shows_body():
    frag = parse_fragment_text(
        "# c — C\n- **Category:** added\n- **Status:** proposed\n\n---\n\n"
        "## Detail\n\nSome detail text.\n",
        stem="c",
    )
    output = render_tasks_md([frag], rich=True)
    assert "Detail" in output
    assert "Some detail text." in output


def test_render_tasks_md_rich_no_fragments():
    output = render_tasks_md([], rich=True)
    # Must still contain the assembled header and epilogue sentinel.
    assert "Generated from" in output
    assert EPILOGUE_SENTINEL in output


def test_render_tasks_md_flat_status_collapse():
    """Flat mode collapses statuses; same category from different statuses merges."""
    frags = [
        parse_fragment_text(
            "# p — Proposed\n- **Category:** added\n- **Status:** proposed\n", stem="p"
        ),
        parse_fragment_text(
            "# d — Done\n- **Category:** added\n- **Status:** done\n", stem="d"
        ),
    ]
    output = render_tasks_md(frags, rich=False)
    # Both under a single ## New Features section (the CATEGORIES title for "added").
    assert output.count("## New Features") == 1
    assert "Proposed" in output
    assert "Done" in output


# ---------------------------------------------------------------------------
# _shift_headings (tested via rich render body)
# ---------------------------------------------------------------------------


def test_shift_headings_via_rich_render_adjusts_depth():
    """H2 inside a body should become H4 after a +2 shift in rich mode."""
    frag = parse_fragment_text(
        "# h — H\n- **Category:** added\n- **Status:** proposed\n\n---\n\n"
        "## Sub-heading\n\nContent.\n",
        stem="h",
    )
    output = render_tasks_md([frag], rich=True)
    # The H2 in the body is shifted by +2 -> should appear as ####.
    assert "#### Sub-heading" in output


def test_shift_headings_does_not_shift_inside_fence():
    """Headings inside fenced code blocks must not be shifted."""
    frag = parse_fragment_text(
        "# f — F\n- **Category:** added\n- **Status:** proposed\n\n---\n\n"
        "```\n## Not a heading\n```\n\n## Real heading\n",
        stem="f",
    )
    output = render_tasks_md([frag], rich=True)
    # The fenced content must not be turned into ####.
    assert "#### Not a heading" not in output
    # The real heading outside the fence gets shifted.
    assert "#### Real heading" in output


# ---------------------------------------------------------------------------
# Epilogue preservation edge-cases
# ---------------------------------------------------------------------------


def test_epilogue_absent_adds_sentinel_only():
    output = render_tasks_md([], rich=False, existing=None)
    assert EPILOGUE_SENTINEL in output


def test_epilogue_is_preserved_on_rebuild(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tickets = tmp_path / "tickets"
    tickets.mkdir()
    (tickets / "0001-a.md").write_text(
        "# 0001-a — A\n- **Category:** added\n", encoding="UTF-8"
    )
    out = tmp_path / "TASKS.md"
    assemble_tasks_file(tickets, out)
    current = out.read_text(encoding="UTF-8")
    current += "\nMy custom epilogue note.\n"
    out.write_text(current, encoding="UTF-8")
    # Second assemble must preserve the epilogue.
    assemble_tasks_file(tickets, out)
    final = out.read_text(encoding="UTF-8")
    assert "My custom epilogue note." in final


def test_epilogue_with_sentinel_only_preserved_empty():
    existing = f"# Tasks\n\n{EPILOGUE_SENTINEL}\n"
    output = render_tasks_md([], rich=False, existing=existing)
    # Sentinel present, no body -> no extra content after sentinel.
    sentinel_pos = output.index(EPILOGUE_SENTINEL)
    after = output[sentinel_pos + len(EPILOGUE_SENTINEL) :].strip()
    assert after == ""


# ---------------------------------------------------------------------------
# changelog_entries -- edge-cases
# ---------------------------------------------------------------------------


def test_changelog_entries_multiple_done_shipping():
    frags = [
        parse_fragment_text(
            "# a — A\n- **Category:** added\n- **Status:** done\n", stem="a"
        ),
        parse_fragment_text(
            "# b — B\n- **Category:** security\n- **Status:** done\n", stem="b"
        ),
    ]
    entries = changelog_entries(frags)
    assert ("added", "A") in entries
    assert ("security", "B") in entries


def test_changelog_entries_wontfix_excluded():
    frag = parse_fragment_text(
        "# w — W\n- **Category:** added\n- **Status:** wontfix\n", stem="w"
    )
    assert changelog_entries([frag]) == []


def test_changelog_entries_non_shipping_done_excluded():
    for cat in ("internal", "chore", "docs", "test", "spike"):
        frag = parse_fragment_text(
            f"# x — X\n- **Category:** {cat}\n- **Status:** done\n", stem="x"
        )
        assert changelog_entries([frag]) == [], f"expected empty for category={cat!r}"


# ---------------------------------------------------------------------------
# render_fragment -- minimal / maximal coverage
# ---------------------------------------------------------------------------


def test_render_fragment_no_optional_fields():
    frag = TaskFragment(task_id="0001", title="A title", category="added")
    rendered = render_fragment(frag)
    assert "0001" in rendered
    assert "A title" in rendered
    assert "**Category:** added" in rendered
    assert "**Status:** proposed" in rendered
    # No optional sections.
    assert "Tracker" not in rendered
    assert "Labels" not in rendered
    assert "Assignees" not in rendered
    assert "Milestone" not in rendered


def test_render_fragment_all_optional_fields():
    frag = TaskFragment(
        task_id="0099",
        title="Full",
        category="fixed",
        status="in-progress",
        tracker="github#99",
        labels=["ux", "backend"],
        assignees=["alice", "bob"],
        milestone="2.0.0",
        custom={"Story Points": "8"},
        body_md="A body paragraph.\n",
    )
    rendered = render_fragment(frag)
    assert "**Tracker:** github#99" in rendered
    assert "**Labels:** ux, backend" in rendered
    assert "**Assignees:** @alice, @bob" in rendered
    assert "**Milestone:** 2.0.0" in rendered
    assert "**Story Points:** 8" in rendered
    assert "A body paragraph." in rendered
    assert "---" in rendered


def test_render_fragment_body_is_separated_by_divider():
    frag = TaskFragment(
        task_id="0002", title="T", category="added", body_md="Body text.\n"
    )
    rendered = render_fragment(frag)
    divider_pos = rendered.index("---")
    body_pos = rendered.index("Body text.")
    assert divider_pos < body_pos


# ---------------------------------------------------------------------------
# read_fragments -- sorting and count
# ---------------------------------------------------------------------------


def test_read_fragments_sorted_by_filename(tmp_path):
    tickets = tmp_path / "tickets"
    tickets.mkdir()
    for name in ("0003-c.md", "0001-a.md", "0002-b.md"):
        (tickets / name).write_text(
            f"# {name[:-3]} — Title\n- **Category:** added\n", encoding="UTF-8"
        )
    frags = read_fragments(tickets)
    ids = [f.task_id for f in frags]
    assert ids == sorted(ids)


def test_read_fragments_empty_dir(tmp_path):
    tickets = tmp_path / "tickets"
    tickets.mkdir()
    assert read_fragments(tickets) == []


def test_read_fragments_nonexistent_dir(tmp_path):
    assert read_fragments(tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# assemble_tasks_file -- dry_run and no-op rebuild
# ---------------------------------------------------------------------------


def test_assemble_dry_run_content_still_returned(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tickets = tmp_path / "tickets"
    tickets.mkdir()
    (tickets / "0001-a.md").write_text(
        "# 0001-a — Alpha\n- **Category:** added\n", encoding="UTF-8"
    )
    out = tmp_path / "TASKS.md"
    rendered, lint = assemble_tasks_file(tickets, out, dry_run=True)
    # dry_run: file not written.
    assert not out.exists()
    # But rendered text is still populated.
    assert "Alpha" in rendered
    assert isinstance(lint, list)


def test_assemble_noop_when_identical(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tickets = tmp_path / "tickets"
    tickets.mkdir()
    (tickets / "0001-a.md").write_text(
        "# 0001-a — Alpha\n- **Category:** added\n", encoding="UTF-8"
    )
    out = tmp_path / "TASKS.md"
    first, _ = assemble_tasks_file(tickets, out)
    mtime_after_first = out.stat().st_mtime
    # Second call should not touch the file if content is identical.
    _, _ = assemble_tasks_file(tickets, out)
    assert out.stat().st_mtime == mtime_after_first
    assert out.read_text(encoding="UTF-8") == first


# ---------------------------------------------------------------------------
# Heading-shift cap at 6
# ---------------------------------------------------------------------------


def test_heading_shift_caps_at_h6():
    """A heading already at depth 5 shifted by +2 must cap at H6."""
    frag = parse_fragment_text(
        "# deep — Deep\n- **Category:** added\n- **Status:** proposed\n\n---\n\n"
        "##### Level 5 heading\n",
        stem="deep",
    )
    output = render_tasks_md([frag], rich=True)
    # No 7-hash heading must appear.
    assert "####### " not in output
    # The heading should appear as ###### (capped at 6).
    assert "###### Level 5 heading" in output
