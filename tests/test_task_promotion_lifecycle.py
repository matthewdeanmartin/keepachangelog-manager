from pathlib import Path

import pytest

from changelogmanager import cli
from changelogmanager.task_fragments import TaskFragment, render_fragment


@pytest.mark.parametrize("keep", [False, True])
def test_promoted_ticket_does_not_return_after_release_and_reassembly(keep):
    Path("tickets").mkdir()
    ticket = Path("tickets/0001-demo.md")
    ticket.write_text(
        render_fragment(
            TaskFragment(
                task_id="0001-demo", title="Fix links", category="fixed", status="done"
            )
        ),
        encoding="utf-8",
    )
    Path("CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n", encoding="utf-8"
    )
    assert cli.main(["tasks", "assemble"]) == 0
    original = Path("TASKS.md").read_text(encoding="utf-8")
    assert cli.main(["tasks", "promote", "--dry-run"]) == 0
    assert Path("TASKS.md").read_text(encoding="utf-8") == original
    assert cli.main(["tasks", "promote", *(["--keep"] if keep else [])]) == 0
    assert "Fix links" in Path("CHANGELOG.md").read_text(encoding="utf-8")
    assert cli.main(["release", "--override-version", "1.0.0", "--yes"]) == 0
    # Even --keep must not re-promote without rebuilding first.
    assert cli.main(["tasks", "promote", "--keep"]) == 0
    assert cli.main(["tasks", "assemble"]) == 0
    assert "Fix links" not in Path("TASKS.md").read_text(encoding="utf-8")
    assert cli.main(["tasks", "promote"]) == 0
    assert Path("CHANGELOG.md").read_text(encoding="utf-8").count("Fix links") == 1
    # The original ticket remains intact for historical reference.
    assert "**Status:** done" in ticket.read_text(encoding="utf-8")
    # A genuinely different ticket with the same wording can ship again.
    Path("tickets/0002-demo.md").write_text(
        render_fragment(
            TaskFragment(
                task_id="0002-demo", title="Fix links", category="fixed", status="done"
            )
        ),
        encoding="utf-8",
    )
    assert cli.main(["tasks", "assemble"]) == 0
    assert cli.main(["tasks", "promote"]) == 0
    assert Path("CHANGELOG.md").read_text(encoding="utf-8").count("Fix links") == 2


def test_checking_generated_task_preserves_identity_and_promotion_epilogue():
    from changelogmanager.task_fragments import render_tasks_md
    from changelogmanager.tasks import (
        parse_task_file,
        record_promoted_fragments,
        set_task_checked,
    )

    fragment = TaskFragment(task_id="one", title="Fix links", category="fixed")
    path = Path("TASKS.md")
    path.write_text(
        render_tasks_md([fragment]) + "\nKeep this note.\n", encoding="utf-8"
    )
    before = parse_task_file(path)[0]
    checked = set_task_checked(path, "Fix links", checked=True)
    assert checked.fragment_key == before.fragment_key
    assert checked.done_date
    assert checked.text == "Fix links"
    record_promoted_fragments(path, [checked], {checked.line})
    rebuilt = render_tasks_md([fragment], existing=path.read_text(encoding="utf-8"))
    assert "Keep this note." in rebuilt
    assert "Fix links" not in rebuilt
    assert render_tasks_md([fragment], existing=rebuilt) == rebuilt
