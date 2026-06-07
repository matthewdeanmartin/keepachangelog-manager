# Task file support

Status: **proposed** · Owner: TBD · Last updated: 2026-06-06

## Goal

Add first-class support for lightweight project task files that can feed
`[Unreleased]` changelog entries without requiring GitHub Issues, Jira, or any hosted
tracker.

The primary format is `TASKS.md`: a Markdown file containing TODO items grouped by
Keep a Changelog change type. The app should be able to read, validate, edit, and
promote completed tasks into the changelog the same way it already manages changelog
content.

## Non-goals

- Replacing GitHub Issues, pull requests, or release fragments.
- Parsing arbitrary inline source-code TODO tags.
- Inventing a general project-management system with owners, estimates, workflows,
  boards, or recurrence.
- Guessing user intent from unstructured prose outside the supported task-file schema.

## File discovery

Default task-file discovery:

1. `TASKS.md`
1. `.changelogmanager/TASKS.md`
1. A configured path from `[tasks].file`

Explicit CLI flags always win over discovery:

```sh
changelogmanager tasks list --tasks-file docs/TASKS.md
changelogmanager tasks check --tasks-file .changelogmanager/TASKS.md
```

Suggested config:

```toml
[tasks]
file = "TASKS.md"
done_date_source = "git"      # git | today | none
archive_completed = true
```

If no task file exists, commands that only read tasks should report that clearly.
Commands that create or edit tasks may create the file using the canonical schema.

## Canonical Markdown schema

`TASKS.md` uses Keep a Changelog section names as headings. Each task is a Markdown
task-list item.

```md
# Tasks

## Added

- [ ] Add changelog fragment collection.
- [x] Support GitHub Release draft publishing. <!-- done: 2026-06-05 -->

## Changed

- [ ] Let `config init` write task defaults.

## Fixed

- [ ] Preserve links when moving completed tasks into `[Unreleased]`.
```

Supported headings:

- `Added`
- `Changed`
- `Deprecated`
- `Removed`
- `Fixed`
- `Security`

The parser should also accept heading aliases already supported elsewhere in the
project, but new writes should emit canonical Keep a Changelog headings.

## Task item model

Normalize each task into an internal model before editing or promotion:

```python
@dataclass
class TaskItem:
    change_type: str
    text: str
    checked: bool
    done_date: str | None
    source_file: Path
    line: int
    refs: list[str]
```

`refs` are lightweight references found in the task text, such as `#123`, `GH-123`,
or full URLs. They are preserved when the item moves into the changelog.

## Done dates

Markdown task lists do not have a standard completion date. The app should support
three strategies:

| Strategy | Behavior |
|---|---|
| `git` | Infer the date from the first commit where `- [ ]` became `- [x]`. |
| `today` | Use the current local date when the app marks a task done. |
| `none` | Do not attach or infer a completion date. |

When the app itself marks a task complete, it should write an explicit HTML metadata
comment:

```md
- [x] Add task promotion support. <!-- done: 2026-06-06 -->
```

For tasks that were already checked by hand, `tasks promote` may infer a date from git
history. If git history is unavailable or ambiguous, the task still promotes, but the
date is omitted from the changelog entry.

The done date is metadata for review and filtering. It does not replace the release
date, which remains attached to the changelog version.

## CLI surface

Add a new command group:

```sh
changelogmanager tasks COMMAND [OPTIONS]
```

Initial commands:

| Command | Description |
|---|---|
| `tasks list` | Print parsed tasks grouped by change type and status. |
| `tasks add TYPE TEXT` | Add an unchecked task under a KAC section. |
| `tasks check TEXT_OR_ID` | Mark a task done and attach a done date according to config. |
| `tasks uncheck TEXT_OR_ID` | Mark a task not done and remove app-written done metadata. |
| `tasks edit TEXT_OR_ID` | Edit the task text or change type. |
| `tasks promote` | Move checked tasks into `[Unreleased]` in the active changelog. |

`TEXT_OR_ID` may start as a line number or exact task text match. A later pass can add
stable hidden IDs if line-number editing proves too brittle.

## Promotion command

`tasks promote` moves completed tasks into the active changelog:

```sh
changelogmanager tasks promote
changelogmanager tasks promote --tasks-file TASKS.md --input-file CHANGELOG.md
changelogmanager tasks promote --keep
changelogmanager tasks promote --dry-run
```

Options:

| Option | Default | Description |
|---|---|---|
| `--tasks-file PATH` | discovered | Task file to read and update |
| `--keep` | `false` | Leave completed tasks in place after adding changelog entries |
| `--archive` | config | Move promoted tasks to `## Done` instead of deleting them |
| `--dry-run` | `false` | Show proposed changelog entries without writing |
| `--since DATE` | none | Promote only checked tasks completed on or after a date |

Promotion rules:

- Only checked items (`- [x]` or `- [X]`) are promoted.
- The task's containing heading determines the changelog change type.
- The task text becomes the changelog bullet text after removing task metadata.
- Existing identical entries in `[Unreleased]` are not duplicated.
- If `--keep` is not set, promoted tasks are removed from their original section.
- If archiving is enabled, promoted tasks move under a `## Done` section grouped by
  completion date or promotion date.

Example:

```md
## Fixed

- [x] Preserve links when moving completed tasks. <!-- done: 2026-06-06 -->
```

becomes:

```md
## [Unreleased]

### Fixed

- Preserve links when moving completed tasks.
```

## Editing behavior

The app should support `TASKS.md` as an editable first-class document:

- CLI commands can add, check, uncheck, edit, remove, and promote tasks.
- GUI/TUI surfaces should open a task file alongside changelog files when present.
- Validation should report malformed task items with file/line diagnostics.
- Formatting should preserve surrounding prose and comments as much as practical.

The first implementation can preserve non-task content by operating on parsed line
ranges instead of re-rendering the whole file.

## Validation

Add a task validation path:

```sh
changelogmanager tasks validate
changelogmanager validate --tasks
```

Validation checks:

- Recognized KAC headings are used for promotable tasks.
- Checked items have valid `done: YYYY-MM-DD` metadata when metadata is present.
- Task text is non-empty after metadata removal.
- Duplicate checked tasks in the same change type are warned about.
- Promotable tasks under unknown headings produce an actionable warning.

## Testing plan

- Parser tests for canonical headings, aliases, checked/unchecked states, metadata,
  references, and unknown sections.
- Promotion tests that prove completed tasks move into `[Unreleased]` under the
  correct KAC section.
- Idempotency tests: running `tasks promote` twice does not duplicate entries.
- `--dry-run` tests proving neither `TASKS.md` nor `CHANGELOG.md` is written.
- Git-date inference tests using a temporary git repository.
- Tests must rely on the existing cwd isolation fixture and use `tmp_path`; never point
  at the repository's real `CHANGELOG.md`.

## Open questions

- Should `TASKS.md` support one task belonging to multiple change types, or should
  duplication be explicit?
- Should task IDs be hidden HTML comments from the start, or deferred until users need
  stable editing references?
- Should archiving completed tasks be the default, or should promotion delete them by
  default to keep `TASKS.md` short?
