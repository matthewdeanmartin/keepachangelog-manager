# Copilot gap review

Status: **reviewed** · Owner: TBD · Last updated: 2026-06-04

## Baseline

The project already has real quality gates:

- `build_and_test.yml` runs `make lint bandit test validate` on push and pull request.
- `.pre-commit-config.yaml` runs `changelogmanager --error-format github validate` locally.
- The current suite is green (`507 passed` during this review).

So the notes below focus on gaps that are still visible in code and workflow, not on missing basics.

## 1. Incomplete or half-finished surfaces

### Remote backfill is still exposed before it is implemented

The CLI parser still advertises `backfill --source github-releases`, `github-prs`, and `pypi`, plus `--repository` and
`--package`, but labels some of that input as reserved for future phases (`changelogmanager\cli\parser.py:354-420`). The
actual planner still fast-fails for any non-local source and only supports `tags`, `commits`, and `all` (
`changelogmanager\backfill.py:749-771`).

The GUI makes this worse by offering those unsupported sources in the Backfill screen dropdown (
`changelogmanager\gui\screens\backfill.py:35-58`). That means the product currently invites a user into a dead end
instead of hiding unfinished paths.

**Recommendation:** either hide unsupported sources in both CLI help and GUI, or implement one remote source end-to-end
before advertising it.

## 2. Workflow gaps

### Commit policy enforcement is only partially wired

There is no active commit-message or PR-title validator in the repo workflow. The PR workflow has a commented-out
`conventional-commits` job (`.github\workflows\quality_checks.yml:31-38`), while local pre-commit only validates the
changelog file itself (`.pre-commit-config.yaml:5-14`).

That matters because commit-derived workflows currently treat a lot of non-release-worthy commit types as
changelog-worthy. `docs`, `style`, `test`, `build`, `ci`, `chore`, and `refactor` all map to `changed` in the
Conventional Commit bridge (`changelogmanager\backfill.py:39-63,221-233`). So if a team leans on `from-commits` or
`backfill --source commits`, formatting and maintenance noise can easily end up in the changelog.

**Recommendation:** add an explicit policy for "no changelog needed" work. The lowest-friction version is:

1. restore commit/PR linting in CI,
2. define a skip convention such as `no-changelog`, and
3. teach `from-commits` / `backfill` to ignore clearly non-user-facing commit types by default.

## 3. Validation and corruption invariants

### Persisted mutations are not re-validated after write

The CLI mutation commands (`add`, `remove`, `edit`, `release`) update the in-memory model and then write immediately (
`changelogmanager\cli\commands.py:413-506,292-369`). They rely on the model being correct, but they do not prove that
the final file still round-trips through `ChangelogReader.read()` after the write.

The GUI is looser still: `EditScreen.save()` and `EditScreen.release()` write raw text directly with
`Path.write_text(...)`, and validation is a separate button instead of a write invariant (
`changelogmanager\gui\screens\edit.py:264-325`). That creates exactly the kind of "did we corrupt it while editing?"
risk you called out.

**Recommendation:** during development, every persisted mutation should round-trip through `ChangelogReader.read()`
before the command is considered successful. If the extra cost feels too high for production, gate it behind a
strict/dev flag rather than skipping it entirely.

### `validate --fix` is not transactional

The `validate --fix` path writes raw-text fixes to the real file before it proves the result can still be parsed and
schema-validated. This happens in both the single-file CLI loader and the multi-component validator (
`changelogmanager\cli\loaders.py:102-155`, `changelogmanager\services.py:633-705`).

If the raw rewrite succeeds but the later parse or schema validation fails, the user's file has already been modified.
That is the biggest concrete corruption risk in the current codebase.

**Recommendation:** do the full autofix pipeline in a temp file, validate the temp output, and only then replace the
original file atomically.

### Writes are not atomic, and rollback is assumed to be Git

`Changelog.write_to_file()` opens the target file with `"w"` and overwrites it in place (
`changelogmanager\changelog.py:519-530`). The GUI uses the same overwrite pattern through `Path.write_text(...)` (
`changelogmanager\gui\screens\edit.py:269-272,319-320`).

That is probably acceptable if the repository is clean and under Git, but it is not a real rollback strategy for
interrupted writes, editor crashes, or non-Git use. I do **not** think a full application-level version-history feature
is worth building yet, but the current behavior is still weaker than it should be.

**Recommendation:** make writes atomic first. After that, document Git as the supported rollback path and optionally add
a lightweight backup file in development mode.

## 4. Performance findings

### The hot path still does repeated file I/O

`ChangelogReader.read()` currently:

1. validates layout by opening the file and scanning lines,
2. reads the file again for preamble validation, and
3. calls `keepachangelog.to_dict(...)`, which reads it again (`changelogmanager\changelog_reader.py:109-143,390-461`).

`validate_one_component(..., fix=True)` can then add another read/write/read/write cycle on top (
`changelogmanager\services.py:646-705`).

This does **not** look like a place for long-lived memoization. These commands are short-lived CLIs. The right
optimization is transaction-local caching: load the file once, carry text and parsed structure through the pipeline, and
write once at the end.

### The GUI will not scale to large changelogs

The embedded CLI runner is synchronous and runs on the GUI thread (`changelogmanager\gui\cli_runner.py:22-39`). The edit
screen also renders released history as one Tk label per entry (`changelogmanager\gui\screens\edit.py:165-187`).

That is fine for small changelogs, but it will feel bad on large repositories: long-running commands block the UI, and
historical sections become widget-heavy.

**Recommendation:** if the GUI is meant to handle large changelogs, move CLI work off the main thread and replace the
history label wall with a `Treeview` or another virtualized view.

## 5. Recommended order

1. Make `validate --fix` transactional and atomic.
2. Add a post-write round-trip invariant for every persisted mutation, at least in dev/strict mode.
3. Hide or implement unsupported backfill sources so the GUI and CLI stop advertising dead ends.
4. Reinstate commit/PR linting and define a first-class "no changelog needed" policy.
5. Optimize repeated file reads; do GUI scaling work only if large changelogs are a real target use case.
