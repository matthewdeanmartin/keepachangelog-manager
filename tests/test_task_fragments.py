# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Tests for the task-fragment system (rigid head + free body -> TASKS.md)."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from changelogmanager import cli
from changelogmanager.change_types import ships_to_changelog
from changelogmanager.task_fragments import (
    assemble_tasks_file,
    changelog_entries,
    parse_fragment_text,
    read_fragments,
    render_fragment,
    render_tasks_md,
    split_head_body,
)
from changelogmanager.tasks import parse_task_file
from changelogmanager.tracker_profiles import fragment_to_issue, issue_to_fragment

SAMPLE = """\
# 0042-network-config — Add a Network Config dialog

- **Category:** added
- **Status:** in-progress
- **Tracker:** github#128
- **Labels:** ui, networking
- **Assignees:** @matthew
- **Milestone:** 6.2.0
- **Story Points:** 5

---

## Goal

Do the thing with `---` inside prose, even.
"""


# ----------------------------------------------------------------------
# parsing
# ----------------------------------------------------------------------


def test_parse_head_fields_and_custom():
    frag = parse_fragment_text(SAMPLE, stem="0042-network-config")
    assert frag.task_id == "0042-network-config"
    assert frag.title == "Add a Network Config dialog"
    assert frag.category == "added"
    assert frag.status == "in-progress"
    assert frag.tracker == "github#128"
    assert frag.labels == ["ui", "networking"]
    assert frag.assignees == ["matthew"]
    assert frag.milestone == "6.2.0"
    # unknown key preserved verbatim in custom
    assert frag.custom == {"Story Points": "5"}
    assert frag.body_md.strip().startswith("## Goal")
    assert frag.lint == []


def test_category_only_is_required_others_optional():
    frag = parse_fragment_text("# x — X\n\n- **Category:** fixed\n", stem="x")
    assert frag.category == "fixed"
    assert frag.lint == []


def test_missing_category_is_lint_not_error():
    frag = parse_fragment_text("# x — X\n\njust prose\n", stem="x")
    assert frag.category == "uncategorized"
    assert any("Category" in message for message in frag.lint)


def test_unknown_category_is_kept_and_warned():
    frag = parse_fragment_text("# x — X\n- **Category:** compliance\n", stem="x")
    assert frag.category == "compliance"
    assert any("unknown category" in message for message in frag.lint)


def test_divider_inside_code_fence_does_not_split():
    text = "# x — X\n\n- **Category:** added\n\n```\n---\n```\n\n---\n\nreal body\n"
    head, body = split_head_body(text)
    assert "real body" in body
    assert "```" in head
    frag = parse_fragment_text(text, stem="x")
    assert frag.category == "added"
    assert frag.body_md.strip() == "real body"


def test_no_divider_means_no_body():
    head, body = split_head_body("# x — X\n- **Category:** added\n")
    assert body == ""
    assert "Category" in head


# ----------------------------------------------------------------------
# lossless round-trip
# ----------------------------------------------------------------------


def test_round_trip_preserves_known_and_custom_fields():
    frag = parse_fragment_text(SAMPLE, stem="0042-network-config")
    again = parse_fragment_text(render_fragment(frag), stem="0042-network-config")
    assert again.title == frag.title
    assert again.category == frag.category
    assert again.status == frag.status
    assert again.tracker == frag.tracker
    assert again.labels == frag.labels
    assert again.assignees == frag.assignees
    assert again.milestone == frag.milestone
    assert again.custom == frag.custom
    assert again.body_md.strip() == frag.body_md.strip()


@given(
    st.lists(
        st.tuples(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll"), max_codepoint=122
                ),
                min_size=1,
                max_size=12,
            ),
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), max_codepoint=122
                ),
                max_size=20,
            ),
        ),
        max_size=6,
        unique_by=lambda pair: pair[0],
    )
)
def test_custom_fields_round_trip(pairs):
    # Exclude keys that collide with known head keys.
    known = {"category", "status", "tracker", "labels", "assignees", "milestone"}
    pairs = [(k, v) for k, v in pairs if k.lower() not in known]
    lines = ["# z — Z", "", "- **Category:** added"]
    for key, value in pairs:
        lines.append(f"- **{key}:** {value}")
    frag = parse_fragment_text("\n".join(lines) + "\n", stem="z")
    again = parse_fragment_text(render_fragment(frag), stem="z")
    assert again.custom == dict(pairs)


# ----------------------------------------------------------------------
# total parsing (never raises)
# ----------------------------------------------------------------------


@given(st.text(max_size=400))
def test_total_parsing_never_raises(text):
    frag = parse_fragment_text(text, stem="fuzz")
    # Always produces a usable fragment.
    assert frag.task_id
    assert isinstance(frag.lint, list)


@given(st.binary(max_size=200))
def test_total_parsing_on_bytes_decoded(blob):
    text = blob.decode("utf-8", errors="replace")
    parse_fragment_text(text, stem="fuzz")  # must not raise


# ----------------------------------------------------------------------
# assembler
# ----------------------------------------------------------------------


def _write(tickets: Path, name: str, content: str) -> None:
    tickets.mkdir(parents=True, exist_ok=True)
    (tickets / name).write_text(content, encoding="UTF-8")


def test_assemble_flat_output_parses_as_taskitems(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tickets = tmp_path / "tickets"
    _write(tickets, "0001-a.md", "# 0001-a — Alpha\n- **Category:** added\n")
    _write(
        tickets,
        "0002-b.md",
        "# 0002-b — Beta\n- **Category:** fixed\n- **Status:** done\n",
    )
    out = tmp_path / "TASKS.md"
    rendered, lint = assemble_tasks_file(tickets, out)
    assert lint == []
    # The flat output must be consumable by the existing TaskItem parser.
    items = parse_task_file(out)
    texts = {(item.change_type, item.text, item.checked) for item in items}
    assert ("added", "Alpha", False) in texts
    assert ("fixed", "Beta", True) in texts


def test_assemble_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tickets = tmp_path / "tickets"
    _write(tickets, "0001-a.md", "# 0001-a — Alpha\n- **Category:** added\n")
    _write(tickets, "0002-b.md", "# 0002-b — Beta\n- **Category:** fixed\n")
    out = tmp_path / "TASKS.md"
    first, _ = assemble_tasks_file(tickets, out)
    second, _ = assemble_tasks_file(tickets, out)
    assert first == second


def test_assemble_preserves_epilogue(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tickets = tmp_path / "tickets"
    _write(tickets, "0001-a.md", "# 0001-a — Alpha\n- **Category:** added\n")
    out = tmp_path / "TASKS.md"
    assemble_tasks_file(tickets, out)
    text = out.read_text(encoding="UTF-8")
    text += "\nHand-written epilogue note.\n"
    out.write_text(text, encoding="UTF-8")
    assemble_tasks_file(tickets, out)
    assert "Hand-written epilogue note." in out.read_text(encoding="UTF-8")


def test_readme_and_underscore_files_ignored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tickets = tmp_path / "tickets"
    _write(tickets, "README.md", "# readme\n")
    _write(tickets, "_template.md", "# template\n")
    _write(tickets, "0001-a.md", "# 0001-a — Alpha\n- **Category:** added\n")
    frags = read_fragments(tickets)
    assert [f.task_id for f in frags] == ["0001-a"]


# ----------------------------------------------------------------------
# non-shipping categories
# ----------------------------------------------------------------------


def test_changelog_entries_excludes_non_shipping_and_unfinished():
    frags = [
        parse_fragment_text(
            "# a — A\n- **Category:** added\n- **Status:** done\n", stem="a"
        ),
        parse_fragment_text(
            "# b — B\n- **Category:** internal\n- **Status:** done\n", stem="b"
        ),
        parse_fragment_text(
            "# c — C\n- **Category:** test\n- **Status:** done\n", stem="c"
        ),
        parse_fragment_text(
            "# d — D\n- **Category:** added\n- **Status:** proposed\n", stem="d"
        ),
        parse_fragment_text(
            "# e — E\n- **Category:** custom\n- **Status:** done\n", stem="e"
        ),
    ]
    assert changelog_entries(frags) == [("added", "A")]


def test_ships_to_changelog_flags():
    assert ships_to_changelog("added") is True
    assert ships_to_changelog("security") is True
    assert ships_to_changelog("internal") is False
    assert ships_to_changelog("test") is False
    assert ships_to_changelog("nonsense") is False
    assert ships_to_changelog(None) is False


# ----------------------------------------------------------------------
# tracker profiles
# ----------------------------------------------------------------------


def test_github_profile_maps_state_and_drops_gitlab_weight():
    frag = parse_fragment_text(
        "# e — E\n- **Category:** added\n- **Status:** done\n"
        "- **Labels:** ui\n- **Assignees:** @m\n- **Weight:** 5\n\n---\n\nbody\n",
        stem="e",
    )
    payload = fragment_to_issue(frag, "github")
    assert payload["state"] == "closed"
    assert payload["state_reason"] == "completed"
    assert payload["labels"] == ["ui"]
    assert payload["assignees"] == ["m"]
    assert "weight" not in payload  # GitLab-only; stays in custom under GitHub


def test_gitlab_profile_maps_weight():
    frag = parse_fragment_text(
        "# e — E\n- **Category:** added\n- **Status:** done\n- **Weight:** 5\n",
        stem="e",
    )
    payload = fragment_to_issue(frag, "gitlab")
    assert payload["weight"] == 5
    assert payload["state"] == "closed"


def test_issue_to_fragment_round_trips_github():
    issue = {
        "number": 7,
        "title": "T",
        "body": "desc",
        "state": "closed",
        "state_reason": "not_planned",
        "labels": [{"name": "bug"}],
        "assignees": [{"login": "x"}],
        "milestone": {"title": "1.0"},
    }
    frag = issue_to_fragment(issue, task_id="0007", profile="github")
    assert frag.status == "wontfix"
    assert frag.tracker == "github#7"
    assert frag.labels == ["bug"]
    assert frag.assignees == ["x"]
    assert frag.milestone == "1.0"


# ----------------------------------------------------------------------
# CLI end-to-end
# ----------------------------------------------------------------------


def test_cli_new_then_assemble(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["tasks", "new", "Add a thing", "--category", "added"]) == 0
    created = list((tmp_path / "tickets").glob("*.md"))
    assert len(created) == 1
    assert cli.main(["tasks", "assemble"]) == 0
    text = (tmp_path / "TASKS.md").read_text(encoding="UTF-8")
    assert "Add a thing" in text


def test_cli_fragments_lint_strict_exit_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tickets = tmp_path / "tickets"
    _write(tickets, "0001-bad.md", "no head at all, just prose\n")
    # Non-strict: warnings reported but exit 0.
    assert cli.main(["tasks", "fragments", "lint"]) == 0
    # Strict: non-zero exit when warnings exist.
    assert cli.main(["tasks", "fragments", "lint", "--strict"]) != 0


def test_cli_assemble_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tickets = tmp_path / "tickets"
    _write(tickets, "0001-a.md", "# 0001-a — Alpha\n- **Category:** added\n")
    assert cli.main(["tasks", "assemble", "--dry-run"]) == 0
    assert not (tmp_path / "TASKS.md").exists()
