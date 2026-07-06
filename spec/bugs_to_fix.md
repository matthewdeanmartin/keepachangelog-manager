# Bugs to fix (backlog for a future session)

## `canonical_change_type` singularization is naive

`changelogmanager/tasks.py::canonical_change_type` (and its port,
`katl_co/server/src/katl_core/categories.py::canonical_category`) singularizes
by blindly stripping a trailing `s`:

- `"fixes"` → `"fixe"` → **None** (expected: `"fixed"`)
- `"fixeds"` → `"fixed"` (accepted, but nobody writes that)

Aliases like "fixes", "changes", "additions" fall through to `None` /
uncategorized. Fix by adding an explicit alias table (fixes→fixed,
adds/additions→added, changes→changed, deprecations→deprecated,
removals→removed) instead of mechanical de-pluralization.

When fixing, update **both** copies and their tests: the contract tests in
`katl_co/server/tests/test_katl_core.py` currently pin the buggy behavior
(documented there as source-faithful) and must be changed in the same PR.
