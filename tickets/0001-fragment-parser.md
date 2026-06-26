# 0001-fragment-parser — Task fragment parser (rigid head + free body)

- **Category:** added
- **Status:** proposed
- **Tracker:** github#1
- **Labels:** tasks, parser
- **Assignees:** @matthew
- **Milestone:** 6.2.0

---

## Goal

Add a `TaskFragment` parser that splits a `tickets/*.md` file on the **first**
column-0 `---` outside a fenced code block, parsing the rigid head and keeping the
body verbatim. Make `TaskFragment` a superset of the existing `TaskItem`
(`changelogmanager/tasks.py`).

## Acceptance criteria

- [ ] H1 `# <id> — <summary>` yields `task_id` + `title`; `task_id` cross-checked
      against filename stem (lint warning, not error).
- [ ] `- **Key:** value` bullet list parsed order-insensitively.
- [ ] Known keys → typed fields; **unknown keys → `custom`** (casing + order kept).
- [ ] `Category` is the only required field; unusable head → `uncategorized`
      fragment + lint warnings, **never raises**.
- [ ] Body after divider captured verbatim into `body_md`.
- [ ] `---` inside a head code fence does not end the head.
- [ ] `TaskFragment.to_task_item()` degrades to the current `TaskItem` shape.

## Notes

Reuse `canonical_change_type()` for category normalization (already tolerant of
plurals/title-case). Stdlib only. Fuzz with garbage input; assert it never throws.
Tests under `uv run pytest` using the `isolate_cwd` fixture per `AGENTS.md`.
