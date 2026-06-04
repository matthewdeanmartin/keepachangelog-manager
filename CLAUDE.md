# keepachangelog-manager — Agent Notes

## Running Python / tests — always use `uv run`
This project is managed with **uv**. Always run Python tools through `uv run` so they
execute inside the project's locked virtualenv (which has dev deps like `hypothesis`):

```bash
uv run pytest                      # run the test suite
uv run python -m changelogmanager  # run the CLI
uv run changelogmanager --help     # console script
uv sync --frozen                   # install/refresh the locked env
```

Do **not** call the system `python` or `pytest` directly — it may be the wrong
interpreter or be missing dependencies.

## Tests must never touch the repo's own CHANGELOG.md
This project dogfoods itself: there is a `[tool.changelogmanager]` table in
`pyproject.toml` and a real `CHANGELOG.md` at the repo root. Because of this, a CLI
invocation that resolves a *relative* changelog path against the current working
directory can clobber the repo's own changelog.

Guards in place:
- `tests/conftest.py` has an autouse `isolate_cwd` fixture that `chdir`s every test
  into a fresh temp directory, so relative paths and ambient config can't reach the
  repo. New tests should use `tmp_path` / relative paths and rely on this isolation —
  never hardcode an absolute repo path or a path derived from `__file__`.
- The bash smoke scripts in `scripts/basic_*.sh` run CLI commands; keep their file
  operations confined to their `build/` temp dirs.

If you see junk versions (e.g. "Removed thing", "Feature 1") appear in `CHANGELOG.md`
after a test run, a test or script leaked into the repo's changelog — investigate the
working directory / `--input-file` resolution rather than just reverting the file.
