# Vendored jiggle-version subset

Source: https://github.com/matthewdeanmartin/jiggle_version
Copied from: **jiggle-version 2.1.1** (PyPI), MIT licensed (see `LICENSE`).

This is a minimal, dependency-free copy of the only jiggle-version surface
`changelogmanager.version_bumper` uses:

| Public symbol | Vendored module |
|---|---|
| `find_source_files(project_root, ignore_paths=None)` | `discover.py` |
| `update_pyproject_toml(file_path, new_version)` | `update.py` |
| `update_python_file(file_path, new_version)` | `update.py` |

## What was changed vs upstream

The two functions that pulled in third-party dependencies were reimplemented so
this copy needs **only the standard library**:

- **`discover.py` — dropped `pathspec`.** Upstream walked the tree honoring
  `.gitignore` via `pathspec.GitWildMatchPattern` (upstream `gitignore.py`).
  That whole module was cut. Ignoring is reduced to the static
  `DEFAULT_IGNORE_DIRS` set (`.git`, `.tox`, `.venv`, `__pycache__`), which is
  all `bump_version_files` needs — it only ever targets specific filenames
  (`pyproject.toml`, `_version.py`, `__about__.py`, package `__init__.py`) and
  the caller skips the pyproject path and non-`.py` files. The list of searched
  filenames is unchanged, so results match upstream for a normal layout.

- **`update.py` — dropped `tomlkit`.** Upstream's `update_pyproject_toml` parsed
  and re-dumped the document with `tomlkit` to preserve formatting. The vendored
  copy does a section-aware line rewrite that replaces only the value on the
  `version = ...` line under `[project]` (then `[tool.setuptools]`), leaving
  every other byte untouched — so formatting is preserved without the dependency.
  `update_python_file` is copied verbatim (pure `re`).

## What was NOT copied

Everything else from jiggle-version: the CLI/`__main__`, `auto.py`, `bump.py`,
`config.py`, `git.py`, `gitignore.py`, `pypi.py`, `schemes.py`, the `parsers/`
and `utils/` packages, and `update_setup_cfg` (never called by this project).

## Updating

To pull a newer upstream version, diff `discover.py` / `update.py` against the
new release, re-apply the two dependency-removing changes above, and bump the
version noted at the top of this file.
