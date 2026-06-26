# 0006-cli-and-gui — CLI commands & Tickets GUI surface

- **Category:** added
- **Status:** proposed
- **Tracker:** github#6
- **Labels:** tasks, cli, gui

---

## Goal

Extend the existing `tasks` command group and add a read-mostly **Tickets**
surface to the GUI.

## Acceptance criteria

- [ ] `tasks assemble` ([[0002-assembler]]), `tasks new "<summary>" [--category]`
      scaffolds `tickets/NNNN-<slug>.md` with a valid empty head.
- [ ] `tasks fragments lint` reports head problems; `--strict` exits non-zero.
- [ ] GUI: list `tickets/*.md` grouped by Status → Category, reusing existing
      `gui/screens` + `widgets.py` patterns.
- [ ] GUI selecting a ticket shows head-as-form above body-as-markdown (the
      rigid-top/free-bottom split); an **Assemble** button refreshes the existing
      `TASKS.md` view.

## Notes

Depends on [[0001-fragment-parser]], [[0002-assembler]],
[[0003-non-shipping-categories]]. Wire the console-script entry under the
existing `cli/` package; no new framework for the GUI.
