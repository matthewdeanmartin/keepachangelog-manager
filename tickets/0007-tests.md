# 0007-tests — Tests for the fragment system

- **Category:** test
- **Status:** proposed
- **Tracker:** github#7
- **Labels:** tasks, tests

---

This is a **non-shipping** category (`test`) on purpose: a real task that must
appear in `TASKS.md` but must **not** show up in `CHANGELOG.md`. It's the canary
for [[0003-non-shipping-categories]].

## Acceptance criteria

- [ ] Total-parsing fuzz (hypothesis): random/garbage bytes never raise.
- [ ] Round-trip: title, known fields, custom fields, body survive
      parse → render → parse.
- [ ] Assembler determinism: two runs, byte-identical output.
- [ ] Bridge: `assemble` default output parses via the existing `tasks.py`
      `TaskItem` parser and `tasks promote` is unchanged.
- [ ] `--changelog` excludes every non-shipping category and non-`done` fragment.
- [ ] `---` inside a head code fence does not split.

## Notes

`uv run pytest`, autouse `isolate_cwd` fixture, `tmp_path` — never touch the
repo's real `CHANGELOG.md` (per `AGENTS.md`).
