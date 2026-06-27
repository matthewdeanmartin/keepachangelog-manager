# Vendored code and forks

This page is for implementation details that matter when you are contributing,
debugging internals, or trying to understand the package layout.

## Project lineage

This repository is a fork of the original `keepachangelog-manager`, originally
written mostly by Kevin DeJong at TomTom International.

The published package in this fork is `keepachangelog-manager-fork`, while the
main CLI command remains `changelogmanager`.

## `keepachangelog` vs `keepachangelog-manager`

There are two related but different things in this repository:

| | `keepachangelog` | `keepachangelog-manager` |
|---|---|---|
| **Role** | Parser/serializer layer | User-facing CLI, GUI, validation, release, and automation layer |
| **Origin** | Vendored subset of [`Colin-b/keepachangelog`](https://github.com/Colin-b/keepachangelog) | This project |
| **Location** | `changelogmanager/vendor/keepachangelog/` | `changelogmanager/` |

`keepachangelog-manager` vendors only the small subset of upstream
`keepachangelog` that it needs for parsing and serialization.

## Other vendored code

This repository also vendors `llvm_diagnostics` under
`changelogmanager/llvm_diagnostics/` and adapts the import paths for local use.

That diagnostic layer is what powers the CLI's `llvm` and `github` error-format
output.

### `jiggle_version`

| | `jiggle_version` |
|---|---|
| **Role** | Bumps `pyproject.toml` / `__version__` strings for `release --bump-versions` |
| **Origin** | Vendored subset of [`matthewdeanmartin/jiggle_version`](https://github.com/matthewdeanmartin/jiggle_version) (MIT, from 2.1.1) |
| **Location** | `changelogmanager/vendor/jiggle_version/` |

Version bumping is now **built in** — there is no optional `[jiggle]` extra and no
runtime dependency to install. Only three functions are vendored
(`find_source_files`, `update_pyproject_toml`, `update_python_file`), and they were
reimplemented to use only the standard library: upstream's `pathspec`-based
`.gitignore` walk and `tomlkit`-based pyproject rewrite were dropped. See
`changelogmanager/vendor/jiggle_version/UPSTREAM.md` for exactly what was cut.
