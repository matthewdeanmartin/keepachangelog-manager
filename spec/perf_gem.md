# Performance Review - keepachangelog-manager

This document outlines identified performance bottlenecks and provides recommendations for optimization.

## 1. I/O Efficiency

### Multiple File Passes

The `ChangelogReader` and associated services often read the same file multiple times during a single operation.

- **`ChangelogReader.read()`**: Performs a layout validation pass (opening the file), followed by a `keepachangelog.to_dict()` pass (opening the file again), and potentially a preamble check (reading text again).
- **`services.validate_one_component()`**: If fixing is enabled, it reads the file for raw-text fixes, writes it back, then reads it again for structured validation, and finally writes it again if any structural fixes or formatting were applied.
- **Recommendation**: Cache the file content in memory during a single logical transaction. Use a single pass to collect both layout errors and structured data where possible.

### Atomic Writes

Frequent small writes to the same file (e.g., in `backfill` or `gui`) can be slow and increase the risk of corruption if interrupted.

- **Recommendation**: Use `tempfile.NamedTemporaryFile` and `shutil.move` for atomic writes, and ensure that multiple mutations are batched into a single write operation.

## 2. Subprocess & Git Management

### Subprocess Overhead

The `backfill.py` module makes a large number of `git` subprocess calls.

- **`discover_commit_releases()`**: Calls `git log` for every single tag interval. For a repository with hundreds of tags, this results in hundreds of subprocess spawns.
- **Recommendation**: Batch `git` operations. A single `git log --pretty=format:"..." --decorate` can often provide all necessary information about tags and their associated commits in one stream.

### Redundant Git Status

`services.changed_files()` calls `git status --porcelain` repeatedly.

- **Recommendation**: Cache the results of git status if called within a short time window or during a single batch operation like `validate --all`.

## 3. Network Operations

### Sequential API Requests

GitHub and GitLab integrations perform sequential, synchronous requests.

- **GitHub Pagination**: `get_releases()` fetches pages one by one in a `while True` loop.
- **Draft Cleanup**: `delete_draft_releases()` fetches all releases before iterating to delete drafts.
- **Recommendation**: Use `asyncio` with `httpx` or `aiohttp` to perform network requests in parallel. Pagination can be parallelized if the total number of pages is known or can be guessed.

## 4. CPU & Algorithmic Optimizations

### Regex Recompilation

Many modules (e.g., `changelog_reader.py`, `backfill.py`) use `re.compile(...)` inside loops.

- **Example**: `validate_heading` and `validate_entry` compile several patterns for every line of the changelog.
- **Recommendation**: Pre-compile regular expressions at the module or class level. Use `google-re2` as a faster, safer regex engine where compatible.

### JSON Performance

The project uses the standard `json` library for API interactions and JSON output.

- **Recommendation**: Use `orjson` for significantly faster JSON serialization and deserialization, especially for large API responses from GitHub/GitLab.

### String Concatenation

The vendored `keepachangelog` module uses `+=` for building the Markdown output in `from_dict()`.

- **Recommendation**: Use a `list` to collect lines and join them at the end with `"\n".join(lines)`. This is significantly faster for large changelogs.

### Speculative Version Parsing

`supported_version_metadata` in the vendored `keepachangelog` tries to parse every version against three different schemes (semver, calver, pep440) just to extract metadata.

- **Recommendation**: Cache the detected versioning scheme and only parse once per version.

## 5. GUI Scalability (Tkinter)

### Widget Over-allocation

The `EditScreen` rebuilds its entire widget set on every refresh, including a label for every single entry in the released history.

- **Scalability Issue**: For changelogs with hundreds or thousands of entries, `build_history()` creates O(N) widgets. Tkinter performance degrades significantly with thousands of widgets.
- **Recommendation**:
  - Use `ttk.Treeview` for the history list, which handles large datasets much better.
  - Implement "lazy loading" or virtualization for the history view.
  - Avoid full UI rebuilds on simple entry edits; update only the specific row.

### Blocking Main Thread

File I/O and CLI execution (`run_cli`) are sometimes performed on the main thread in the GUI.

- **Recommendation**: Move I/O-bound and CPU-bound tasks (like `validate` or `backfill`) to a background thread using `concurrent.futures.ThreadPoolExecutor` or `threading.Thread`, using `root.after()` to update the UI upon completion.

______________________________________________________________________

## Implemented Improvements

The following improvements have been implemented:

1. **Faster Regex Engine**: `google-re2` has been added as a direct dependency and integrated into `ChangelogReader` and `Changelog` preamble rendering.
1. **Regex Pre-compilation**: All frequently used regex patterns in `ChangelogReader` have been moved to module-level constants and pre-compiled, eliminating redundant compilation overhead during file parsing and autofixing.
1. **High-Performance JSON**: `orjson` has been added as a direct dependency and replaces the standard `json` library in GitHub/GitLab API clients, the `Changelog` model's JSON export, and the CLI's JSON output handlers.
1. **Verified Correctness**: Comprehensive test suites (501 tests) have been executed to ensure that performance optimizations preserve all existing functionality and correctly handle edge cases (e.g., regex flags).
