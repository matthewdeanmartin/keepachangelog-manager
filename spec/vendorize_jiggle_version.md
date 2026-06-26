# Spec: Vendorize jiggle-version

## Status

Implemented. The vendored subset lives in
`changelogmanager/vendor/jiggle_version/`; the `[jiggle]` extra and the
`jiggle-version` dependency are gone. `find_source_files` and
`update_pyproject_toml` were reimplemented without `pathspec` / `tomlkit` (see
that directory's `UPSTREAM.md`), so the copy is standard-library only.

## Motivation

`--bump-versions` (and the GUI "Bump versions" checkbox) writes the released
version into `pyproject.toml` and any `__version__` strings. That work is done
by **jiggle-version**, currently an *optional* dependency:

```toml
[project.optional-dependencies]
jiggle = ["jiggle-version>=2.1.0,<3"]
```

Because it is optional, version bumping silently degrades unless the user (or
the CI job) remembers `[jiggle]`. The GitHub release workflow has to pass
`uv sync --frozen --extra jiggle`, the new `.gitlab-ci.yml` does the same, and
`bump_version_files` raises `logging.Error` when the import fails. That is a lot
of moving parts for what is, in practice, a tiny slice of jiggle-version's API.

Vendoring that slice makes `--bump-versions` work out of the box (no extra, no
CI flag, no "is it installed?" branch) and removes a `<3` upper-bound dependency
we have to track.

> **Out of scope:** `mdformat` is explicitly *not* a vendoring candidate. It is a
> large dependency with its own plugin ecosystem and parser; vendorizing it is
> too much. The `format` extra stays as-is. This spec covers jiggle-version only.

## Scope: what we actually use

The entire jiggle-version surface used by this project is three functions across
two modules (see `changelogmanager/version_bumper.py`):

```python
from jiggle_version.discover import find_source_files
from jiggle_version.update import update_pyproject_toml, update_python_file
```

| Symbol | Used for |
|---|---|
| `find_source_files(root) -> Iterable[Path]` | Locate `.py` files that may carry a `__version__` |
| `update_pyproject_toml(path, version)` | Rewrite `[project].version` (and `[tool.poetry].version` if present) |
| `update_python_file(path, version)` | Rewrite `__version__ = "..."` assignments |

Nothing else from jiggle-version is imported anywhere in the codebase
(`grep -rn jiggle changelogmanager/`). We do **not** need its CLI, its
`Commands` layer, its config/`.jiggle.ini` handling, its central-version logic,
or its SCM integration.

## Target layout

Follow the existing vendoring convention used for `keepachangelog` and
`llvm_diagnostics` (see `docs/vendored.md`):

```
changelogmanager/vendor/
  __init__.py                 # re-export the new subpackage alongside keepachangelog
  keepachangelog/             # existing
  jiggle_version/             # NEW — minimal vendored subset
    __init__.py               # public surface: find_source_files,
                              #   update_pyproject_toml, update_python_file
    discover.py               # trimmed find_source_files + its private helpers
    update.py                 # trimmed update_pyproject_toml / update_python_file
    LICENSE                   # upstream license text (jiggle-version is MIT)
    UPSTREAM.md               # source repo, version/commit pinned, what was cut
```

`changelogmanager/vendor/__init__.py` gains:

```python
from . import jiggle_version, keepachangelog
__all__ = ["jiggle_version", "keepachangelog"]
```

## Implementation steps

1. **Copy the minimal modules.** From jiggle-version `2.1.x`, copy only
   `discover.py` and `update.py` into `changelogmanager/vendor/jiggle_version/`.
   Strip imports/functions not reachable from the three public symbols. Inline
   any tiny private helper they depend on; delete the rest. Record what was cut
   in `UPSTREAM.md`.

2. **Rewrite imports for local use** (same adaptation we did for
   `llvm_diagnostics`): any intra-package `from jiggle_version.x import y`
   becomes a relative `from .x import y`. No reference to the installed
   `jiggle_version` package should remain in the vendored copy.

3. **Repoint `version_bumper.py`** at the vendored copy and drop the optional
   guard:

   ```python
   from changelogmanager.vendor.jiggle_version.discover import find_source_files
   from changelogmanager.vendor.jiggle_version.update import (
       update_pyproject_toml,
       update_python_file,
   )
   ```

   - Remove the `try/except ImportError` and `HAS_JIGGLE`.
   - `jiggle_available()` now always returns `True`. Keep the function (it is
     called from `services.py` and the GUI) so callers don't change, but it
     becomes a constant. Optionally deprecate it in a follow-up.
   - `bump_version_files` no longer raises the "jiggle-version is required"
     error. Drop that branch.

4. **Remove the optional dependency.**
   - Delete the `[jiggle]` extra from `pyproject.toml`.
   - Drop `jiggle-version` from the `dev`/`test` groups if it appears there.
   - `uv lock` to refresh `uv.lock`.

5. **Drop `--extra jiggle` from CI.**
   - `.github/workflows/release.yml`: `uv sync --frozen` (no `--extra jiggle`).
   - `.gitlab-ci.yml`: same — the `before_script` and the bump job stop needing
     the extra.

6. **Docs.** Add a `jiggle_version` row to the vendored-code table in
   `docs/vendored.md` (origin = upstream jiggle-version, location =
   `changelogmanager/vendor/jiggle_version/`). Note that version bumping is now
   built in. Update any README/CLI text that says `--bump-versions` "requires
   jiggle-version" (e.g. `cli/parser.py` help string for `--bump-versions`,
   `gui/screens/edit.py` checkbox label).

## Tests

- **Keep the existing behavior tests.** `bump_version_files` against a temp
  project should still bump `pyproject.toml` and a `pkg/__init__.py`
  `__version__`. These should now pass *without* installing the extra.
- **Add a vendored-import smoke test** mirroring the keepachangelog one: import
  `changelogmanager.vendor.jiggle_version` and assert the three public symbols
  are present and callable.
- **`jiggle_available()` returns True** unconditionally.
- Tests must continue to obey the `isolate_cwd` rule (operate inside
  `tmp_path`, never the repo root) so a bump never rewrites this repo's own
  `pyproject.toml`. See `CLAUDE.md`.

## Licensing

jiggle-version is MIT-licensed. Vendoring is permitted provided the license and
copyright are retained. Add the upstream `LICENSE` text under
`changelogmanager/vendor/jiggle_version/LICENSE` and a short attribution in
`UPSTREAM.md` (repo URL + the exact version/commit copied). The fork is
Apache-2.0, which is MIT-compatible for redistribution.

## Risks and notes

- **Upstream drift.** Once vendored, we don't get jiggle-version bug fixes
  automatically. Mitigation: the slice is tiny and stable; pin the copied
  version in `UPSTREAM.md` so a maintainer can diff against a newer release.
- **`find_source_files` breadth.** Upstream may walk the tree in a way that
  picks up unexpected files. Verify the trimmed copy only returns `.py` files
  and respects the same root the caller passes; `bump_version_files` already
  skips non-`.py` and the pyproject path itself.
- **No new runtime deps.** Confirm the copied modules rely only on the standard
  library (`pathlib`, `re`, `tomllib`/`tomli`). If they pull in anything else,
  that dependency must be evaluated before vendoring — and if it's heavy, that
  function is a candidate to reimplement rather than copy.
