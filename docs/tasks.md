# Tasks and fragments

If you want to capture work before it becomes polished release notes,
`keepachangelog-manager` supports three staging workflows:

- `TASKS.md` for one shared checklist
- changelog fragments in `changelog.d/`
- ticket-style task fragments in `tickets/`

All three can feed future release notes without forcing you to edit
`CHANGELOG.md` directly on day one.

## Using `TASKS.md`

This workflow is useful when you want a plain Markdown planning file that stays
close to Keep a Changelog categories.

### Task file discovery

The task file is resolved with this precedence (highest first):

1. `--tasks-file` on the command line
1. the selected component's `tasks_file` (see
   [Per-component task files](#per-component-task-files))
1. the global `[tasks].file` config setting
1. discovery of an existing `TASKS.md`, then `.changelogmanager/TASKS.md`

If none of those resolve to an existing file, `tasks add` creates `TASKS.md`.

### Expected format

Tasks live under Keep a Changelog headings and use GitHub-style checkboxes:

```markdown
# Tasks

## Added

- [ ] Support draft release previews

## Fixed

- [x] Preserve links during task promotion. <!-- done: 2026-06-06 -->
```

The `<!-- done: YYYY-MM-DD -->` marker is optional. `tasks check` adds it
automatically by default.

### Common commands

```sh
changelogmanager tasks add added "Support draft release previews"
changelogmanager tasks list
changelogmanager tasks check "Support draft release previews"
changelogmanager tasks validate
```

`tasks check` and `tasks uncheck` accept either a line number or the exact task
text as the selector.

### Promoting completed tasks into `[Unreleased]`

```sh
changelogmanager tasks promote
changelogmanager tasks promote --keep
```

`tasks promote`:

1. reads checked tasks under known change-type headings
1. adds them to `[Unreleased]`
1. skips duplicates already present in the changelog
1. removes the promoted checked tasks unless `--keep` is passed

## Using changelog fragments

This workflow is useful when each upcoming changelog entry should live in its
own file until collection time.

### Fragment directory discovery

Unless you pass `--fragment-dir`, the CLI looks for:

1. `changelog.d`
1. `changes`
1. `.changelogmanager/fragments`

If none exists, `fragments add` or `add --fragment` creates `changelog.d`.

### Fragment filename format

Each fragment file is named:

```text
<slug>.<change-type>.md
```

Examples:

- `issue-123.fixed.md`
- `release-preview.added.md`

The file contents are the changelog entry text.

### Common commands

```sh
changelogmanager fragments add added "Support draft release previews" --slug release-preview
changelogmanager fragments list
changelogmanager fragments validate
changelogmanager fragments collect
```

Shortcut from the normal `add` command:

```sh
changelogmanager add --change-type fixed --message "Preserve links" --fragment issue-123
```

### Collecting fragments into `[Unreleased]`

`fragments collect` imports pending fragments into the changelog, skips
duplicates already present in `[Unreleased]`, then consumes the fragment files.

Consumption modes:

| Mode | Result |
|---|---|
| `archive` | Move collected fragments into `archive/YYYY-MM-DD/` under the fragment directory |
| `delete` | Delete collected fragments |
| `keep` | Leave collected fragments in place |

The default behavior is `archive`.

## Using `tickets/` task fragments

This workflow is aimed at richer planning notes that later assemble into a
generated `TASKS.md`.

### Create a new ticket fragment

```sh
changelogmanager tasks new "Add login screen"
changelogmanager tasks new "Harden release docs" --category docs
```

The default category is `added`. Supported categories include the normal Keep a
Changelog buckets plus planning-oriented categories such as `internal`, `chore`,
`docs`, `test`, and `spike`.

### Lint ticket fragments

```sh
changelogmanager tasks fragments lint
changelogmanager tasks fragments lint --strict
```

`--strict` exits non-zero when any fragment has warnings.

### Assemble `tickets/` into `TASKS.md`

```sh
changelogmanager tasks assemble
changelogmanager tasks assemble --rich
```

Useful options:

- `--tickets-dir`: read fragments from a custom directory
- `--tasks-file`: write to a custom `TASKS.md` path
- `--rich`: emit a grouped `Status -> Category` view with nested fragment bodies

The assembled file includes a generated note pointing back to
`changelogmanager tasks assemble`.

## Configuring task and fragment defaults

You can store defaults in `changelogmanager.toml` or
`[tool.changelogmanager]` in `pyproject.toml`:

```toml
[tasks]
file = ".changelogmanager/TASKS.md"

[fragments]
directory = "changelog.d"
consume = "archive"
```

CLI flags still override config for one-off paths or consume modes.

### Per-component task files

When a project tracks several components (each with its own `CHANGELOG.md`), each
component can also have its own task file. Add a `tasks_file` key to the
component:

```toml
[[components]]
name = "api"
changelog = "api/CHANGELOG.md"
tasks_file = "api/TASKS.md"

[[components]]
name = "web"
changelog = "web/CHANGELOG.md"
# no tasks_file: falls back to [tasks].file, then discovery
```

Select the component with the global `--component` flag and the `tasks`
subcommands act on that component's task file:

```bash
# adds to api/TASKS.md
changelogmanager --component api tasks add fixed "Handle empty payloads"

# promotes api/TASKS.md into api/CHANGELOG.md's [Unreleased]
changelogmanager --component api tasks promote
```

`--tasks-file` still wins over a component's `tasks_file` for one-off paths. A
component without a `tasks_file` falls back to `[tasks].file` and then discovery,
so adding the key is purely opt-in.

In the GUI, picking a component in the Workspace panel (or on the
**Components / Batch** screen) repoints both the Changelog and the Tasks-file
pickers at that component's files. The **New…** component dialog prompts for an
optional tasks file.
