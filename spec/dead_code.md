# Dead Code Report

Generated 2026-06-05. Tools: **vulture 2.16** and **dead 2.1.0** (Facebook).

## How to run

```bash
uv run vulture changelogmanager --min-confidence 60
uv run dead
```

Both tools are in the `dev` dependency group in `pyproject.toml`.
A `[tool.vulture]` config section has been added to `pyproject.toml` (see below).

---

## Summary

| Finding | File | Line | Tool | Confidence | Verdict |
|---------|------|------|------|------------|---------|
| `github_release()` never called from production code | `services.py` | 787 | both | high | **Dead** — CLI duplicates the logic directly |
| `github_pull_request()` never called from production code | `services.py` | 831 | both | high | **Dead** — CLI duplicates the logic directly |
| `gitlab_release()` never called from production code | `services.py` | 867 | both | high | **Dead** — CLI duplicates the logic directly |
| `get_pypi_options()` never read anywhere | `config.py` | 306 | both | high | **Dead** |
| `TextFormat.BLUE` enum member never used | `llvm_diagnostics/utils.py` | 18 | both | high | **Dead** — only `RED`, `BOLD`, `LIGHT_GREEN`, `CYAN` are used |
| `bumped_versions` field on `ReleaseResult` | `services.py` | 86 | vulture | medium | **Dead** — set in constructor but never read by any caller |
| `bumped_files` field on `ReleaseResult` | `services.py` | 88/133 | vulture | medium | **Dead** — assigned in `release_changelog()` but no caller reads it |
| `semantic_version()` in vendored keepachangelog | `vendor/keepachangelog/__init__.py` | 58 | both | medium | Likely dead — only tested via the dict key `"semantic_version"`, not this function |
| `get_versioning_label()` | `config.py` | 332 | vulture | low | False positive — imported and tested in `tests/test_basic/test_change_types_and_config.py:13` |
| `plan_tag_backfill()` | `backfill.py` | 668 | vulture | low | False positive — called directly in `tests/test_basic/test_backfill.py`; internal API |
| `INITIAL_VERSION` | `changelog.py` | 40 | vulture | low | False positive — imported by multiple test files |
| `diagnostics_messages_from_file()` | `llvm_diagnostics/parser.py` | 19 | vulture | low | False positive — called in `tests/test_llvm_diagnostics/test_parser.py` and `test_basic/test_llvm_diagnostics.py` |
| `add_listener()` on `ChangelogState` | `gui/state.py` | 61 | vulture | low | False positive — called in `tests/test_basic/test_gui.py:62` |
| `__getattr__` on `cli/__init__.py` | `cli/__init__.py` | 84 | vulture | low | False positive — module-level `__getattr__` is a Python protocol, not called directly |
| `COAUTHOR_RE` | `scripts/rewrite_history.py` | 41 | dead | — | Script-local; not part of the package |

---

## High-confidence dead code (worth removing)

### 1. Three service functions that the CLI bypasses (`services.py:787–905`)

`github_release()`, `github_pull_request()`, and `gitlab_release()` are fully implemented service-layer functions that return typed dataclass results (`GitHubReleaseResult`, `GitHubPRResult`, `GitLabReleaseResult`). However, `cli/commands.py:554` (`command_github_release`) and `cli/commands.py:704` (`command_gitlab_release`) duplicate all of the same GitHub/GitLab API calls inline rather than delegating to these functions. As a result the three service functions — and their return-type dataclasses — are unreachable from any production call site.

**Options:**
- Delete the three functions and dataclasses from `services.py` (the CLI already has the logic).
- Or refactor the CLI commands to call the service functions (cleaner architecture, easier to test).

### 2. `get_pypi_options()` in `config.py:306`

No import, no call anywhere in the codebase. Safe to delete.

### 3. `TextFormat.BLUE` in `llvm_diagnostics/utils.py:18`

The `TextFormat` enum has five members; only `RED`, `BOLD`, `LIGHT_GREEN`, and `CYAN` appear in formatting calls. `BLUE` was likely added for future use. Because this file is vendored from `llvm_diagnostics 3.0.1`, consider leaving it or tracking the upstream.

---

## Medium-confidence (inspect before removing)

### 4. `bumped_versions` and `bumped_files` on `ReleaseResult` (`services.py:86–133`)

`ReleaseResult.bumped_versions` is set in the constructor but no caller ever reads `.bumped_versions` on the returned result. `bumped_files` is assigned inside `release_changelog()` but again no caller checks it. The CLI command at `commands.py:399` builds its own `bumped_strs` list from the `bump_version_files()` return value directly.

These fields were added as part of the version-bump feature but the CLI layer never wired up reading them from `ReleaseResult`. Either remove them and let the CLI continue doing its own bookkeeping, or fix the CLI to consume the result.

### 5. `vendor/keepachangelog/__init__.py:58` — `semantic_version()` function

The vendored `semantic_version()` helper parses a version string and returns a dict with `{"major": …, "minor": …, "patch": …}`. Tests reference the dict key `"semantic_version"` in changelog output, but that key is produced by `Changelog.get()`, not by calling this function directly. The function is not imported or called anywhere outside the vendor module itself.

---

## False positives (leave alone)

| Symbol | Why it's a false positive |
|--------|--------------------------|
| `get_versioning_label` | Imported by test at `test_change_types_and_config.py:13` |
| `plan_tag_backfill` | Called by tests at `test_backfill.py:94,190`; internal API |
| `INITIAL_VERSION` | Imported by 4 test files |
| `diagnostics_messages_from_file` | Called in 2 test files |
| `add_listener` | Called in `test_gui.py:62` |
| `cli/__init__.py:__getattr__` | Module-level `__getattr__` is a Python protocol |
| `COAUTHOR_RE` (scripts/) | Outside the package; tooling-only script |

---

## Test-only dead code (minor)

Vulture also found several issues inside the test suite itself. These are not package bugs but are worth a cleanup pass:

| Location | Issue |
|----------|-------|
| `tests/test_basic/test_changelog_reader.py:44` | `path_or_lines` assigned but unused (100% confidence) |
| `tests/test_basic/test_fill_gaps.py:322` | `cur` and `prev` tuple-unpacked but neither used (100% confidence) |
| `tests/test_credentials.py:18` | Unsatisfiable ternary condition (100% confidence vulture) |
| `tests/tests_bug_search_suite/test_changelog_core.py:25,33,45` | Module-level fixture strings `MINIMAL_RELEASED`, `WITH_UNRELEASED`, `MULTI_VERSION` unused |
| `tests/tests_bug_search_suite/test_cli_integration.py:33` | `EMPTY_UNRELEASED` unused |
| `tests/tests_bug_search_suite/test_formatting.py:115` | `import importlib` unused (90% confidence) |

---

## Tool configuration added

A `[tool.vulture]` section was added to `pyproject.toml`:

```toml
[tool.vulture]
min_confidence = 60
paths = ["changelogmanager"]
ignore_names = ["__getattr__"]
```

`dead` has no pyproject configuration; it auto-discovers Python files from the current directory.
