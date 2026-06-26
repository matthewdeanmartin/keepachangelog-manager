# `tickets/` — task fragments

Each file here is **one task fragment**: rigid structured markdown on top, a
`---` divider, then freeform markdown on the bottom. `changelogmanager tasks
assemble` concatenates every fragment into the generated `TASKS.md` at the repo
root.

- **Do edit** fragment files here.
- **Do not edit** the structured (top) part of `TASKS.md` — it's generated.
- Files starting with `_` and this `README` are ignored by the assembler.

Format and rules: see
[`spec/TASK_FRAGMENTS_AND_UI.md`](../spec/TASK_FRAGMENTS_AND_UI.md). Related:
[`spec/tasks.md`](../spec/tasks.md) (flat `TASKS.md`),
[`spec/fragments.md`](../spec/fragments.md) (changelog fragments).

```sh
uv run changelogmanager tasks new "Short summary" --category added
uv run changelogmanager tasks assemble
uv run changelogmanager tasks fragments lint
```
