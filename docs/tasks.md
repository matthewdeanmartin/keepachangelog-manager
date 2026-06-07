# Tasks and fragments

If you want to capture work before it becomes a polished changelog entry, `keepachangelog-manager` supports two lightweight staging workflows:

- **`TASKS.md`** for a checklist you can review in one file
- **fragments** for one-file-per-change workflows in `changelog.d/`

Both flows eventually feed `[Unreleased]` in `CHANGELOG.md`.

## Using `TASKS.md`

This workflow is useful when you want a plain Markdown planning file that stays close to changelog categories.

### Task file discovery

Unless you pass `--tasks-file`, the CLI looks for:

1. `TASKS.md`
1. `.changelogmanager/TASKS.md`

If neither file exists, `tasks add` creates `TASKS.md`.

### Expected format

Tasks live under Keep a Changelog headings and use GitHub-style checkboxes:

```markdown
# Tasks

## Added

- [ ] Support draft release previews

## Fixed

- [x] Preserve links during task promotion. <!-- done: 2026-06-06 -->
```

The `<!-- done: YYYY-MM-DD -->` marker is optional. `tasks check` adds it automatically by default.

### Common commands

```sh
changelogmanager tasks add added "Support draft release previews"
changelogmanager tasks list
changelogmanager tasks check "Support draft release previews"
changelogmanager tasks validate
```

`tasks check` and `tasks uncheck` accept either a line number or the exact task text as the selector.

### Promoting completed tasks into `[Unreleased]`

When a checked task is ready to become release notes, promote it:

```sh
changelogmanager tasks promote
```

That command:

1. reads checked tasks under known change-type headings
1. adds them to `[Unreleased]`
1. skips duplicates already present in the changelog
1. removes the promoted checked tasks from `TASKS.md`

If you want to keep the completed checklist items in the task file, use:

```sh
changelogmanager tasks promote --keep
```

## Using fragments

This workflow is useful when you want each upcoming changelog entry to live in its own file until collection time.

### Fragment directory discovery

Unless you pass `--fragment-dir`, the CLI looks for:

1. `changelog.d`
1. `changes`
1. `.changelogmanager/fragments`

If none exists, `fragments add` or `add --fragment` creates `changelog.d`.

### Fragment filename format

Each fragment file must be named:

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

If you already use `add`, there is also a shortcut that writes a fragment instead of editing `[Unreleased]` directly:

```sh
changelogmanager add --change-type fixed --message "Preserve links" --fragment issue-123
```

### Collecting fragments into `[Unreleased]`

`fragments collect` imports pending fragments into the changelog, skips duplicates already present in `[Unreleased]`, then consumes the fragment files.

Consumption modes:

| Mode | Result |
|---|---|
| `archive` | Move collected fragments into `archive/YYYY-MM-DD/` under the fragment directory |
| `delete` | Delete collected fragments |
| `keep` | Leave collected fragments in place |

The default behavior is `archive`.

## Configuring task and fragment defaults

You can store the default task file and fragment behavior in `changelogmanager.toml` or `[tool.changelogmanager]` in `pyproject.toml`:

```toml
[tasks]
file = ".changelogmanager/TASKS.md"

[fragments]
directory = "changelog.d"
consume = "archive"
```

CLI flags still override config when you need a one-off path or consume mode.
