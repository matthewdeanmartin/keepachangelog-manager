# 0002-assembler — Assemble fragments into `TASKS.md`

- **Category:** added
- **Status:** proposed
- **Tracker:** github#2
- **Labels:** tasks, codegen

---

## Goal

Add `changelogmanager tasks assemble`: walk `tickets/`, group by Status →
Category, render `TASKS.md`, preserve the hand-written epilogue.

## Acceptance criteria

- [ ] Ignores `tickets/_*.md` and `tickets/README*`; dir configurable via
      `[tasks].tickets_directory` (default `tickets/`).
- [ ] Grouping uses `CATEGORIES` order, then non-shipping, then unknown last.
- [ ] **Default output is the flat `spec/tasks.md` schema** so `tasks promote`
      keeps working unchanged; `--rich` emits grouped summary + nested body.
- [ ] `done` status → `- [x]` with `<!-- done: YYYY-MM-DD -->`.
- [ ] Output is **stable**: a no-op rebuild is a byte-identical no-op diff.
- [ ] Epilogue after the final sentinel `---` is carried forward.
- [ ] `--dry-run` writes nothing.

## Notes

Depends on [[0001-fragment-parser]]. Render the rich body by shifting heading
depth so a fragment's `##` becomes `####` under its task. Mirror the
`fragments collect` code path/idioms where practical.
