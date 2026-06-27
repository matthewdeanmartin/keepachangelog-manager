# Changelog fragments

A **changelog fragment** is a small file holding exactly one future changelog
entry. Instead of editing `CHANGELOG.md` on every branch — where everyone fights
over the same `[Unreleased]` lines — each change drops a new file into a
fragment folder. At release time you **collect** those files into the changelog
in one deterministic step.

This is the same pattern made popular by tools like Towncrier and `git-cliff`,
adapted to Keep a Changelog. If you have ever hit a merge conflict in
`CHANGELOG.md`, fragments are the fix.

> Looking for *task* fragments (the ticket-style `tickets/*.md` files that
> assemble into `TASKS.md`)? Those are a different feature — see
> [Tasks and fragments](tasks.md). This page is only about **changelog
> fragments** that flow into `CHANGELOG.md`.

## Why fragments

| Without fragments | With fragments |
|---|---|
| Every branch edits `[Unreleased]` in `CHANGELOG.md` | Every branch adds its own file |
| Two branches touching the same lines → merge conflict | Two new files never conflict |
| Reviewers diff a shared file | Reviewers diff one focused note per change |
| Release means hand-merging notes | Release runs `fragments collect` |

The changelog becomes a *generated artifact* of the release step, not a file you
co-edit all sprint.

## The big picture: Component → fragment folder → `CHANGELOG.md`

A **component** selects which `CHANGELOG.md` is written. Fragments land in a
**fragment folder**, and `fragments collect` moves them into that component's
changelog `[Unreleased]` section.

```
                         changelogmanager.toml
                ┌────────────────────────────────────┐
                │ [[components]]                       │
                │ name = "default"                     │
                │ changelog = "CHANGELOG.md"           │
                │                                      │
                │ [fragments]                          │
                │ directory = "changelog.d"            │
                │ consume   = "archive"                │
                └────────────────────────────────────┘
                              │ selects
                              ▼
   add --fragment        ┌──────────────────┐
   fragments add  ──────▶│  changelog.d/    │   one file = one entry
                         │                  │
                         │  dark-mode.added.md          "Support dark mode"
                         │  issue-123.fixed.md          "Preserve links on promote"
                         │  cve-2025.security.md        "Upgrade vulnerable dep"
                         └──────────────────┘
                              │
                              │  changelogmanager fragments collect
                              │    • group by Keep a Changelog type
                              │    • skip text already in [Unreleased]
                              │    • write, then consume the files
                              ▼
                         ┌──────────────────┐
                         │   CHANGELOG.md   │
                         │                  │
                         │  ## [Unreleased] │
                         │  ### Added       │
                         │  - Support dark mode
                         │  ### Fixed       │
                         │  - Preserve links on promote
                         │  ### Security    │
                         │  - Upgrade vulnerable dep
                         └──────────────────┘
                              │
                              │  (later) changelogmanager release
                              ▼
                         ## [1.4.0] - 2026-06-26
```

After a successful collect, the consumed fragment files are **archived** by
default (moved to `changelog.d/archive/YYYY-MM-DD/`), so a fresh `changelog.d`
only ever shows what is still pending.

## The everyday workflow

### 1. Add a fragment while you work

Either through the dedicated `fragments` group:

```sh
changelogmanager fragments add added "Support dark mode" --slug dark-mode
changelogmanager fragments add fixed "Preserve links on promotion"
```

…or as a shortcut on the normal `add` command — pass `--fragment` to redirect
the entry into the fragment folder instead of `[Unreleased]`:

```sh
changelogmanager add --change-type fixed --message "Preserve links" --fragment issue-123
```

`--fragment` with no value derives the slug from the message text; `--fragment
issue-123` sets the slug explicitly.

Commit the fragment file alongside your code change. That is the whole point —
the note travels with the branch, not in a shared file.

### 2. See what is pending

```sh
changelogmanager fragments list
```

```text
[added] changelog.d/dark-mode.added.md: Support dark mode
[fixed] changelog.d/issue-123.fixed.md: Preserve links
```

### 3. Validate before release (optional, CI-friendly)

```sh
changelogmanager fragments validate
```

This checks that every file name parses as `<slug>.<type>.md`, the type is a
known Keep a Changelog section, the content is non-empty, and that no two
fragments of the same type carry identical text. It exits non-zero on problems,
so it slots straight into a CI gate.

### 4. Collect into the changelog at release time

```sh
changelogmanager fragments collect
```

`collect`:

1. reads every valid fragment in the folder,
2. groups them by Keep a Changelog type (`Added`, `Fixed`, …),
3. skips any text already present in `[Unreleased]` (so re-running is safe),
4. writes the new entries to the changelog, then
5. **consumes** the fragment files.

Preview first with `--dry-run`:

```sh
changelogmanager fragments collect --dry-run
```

```text
would collect: [added] Support dark mode
would collect: [fixed] Preserve links
-- DRY RUN -- would collect 2 fragment(s)
```

## Fragment file format

One Markdown file per changelog bullet. The **filename encodes the change type**;
the **file body is the bullet text** (without the leading `- `).

```text
<slug>.<change-type>.md
```

| Example file | Becomes |
|---|---|
| `dark-mode.added.md` | an entry under `### Added` |
| `issue-123.fixed.md` | an entry under `### Fixed` |
| `cve-2025.security.md` | an entry under `### Security` |

Supported type suffixes are the six Keep a Changelog categories: `added`,
`changed`, `deprecated`, `removed`, `fixed`, `security`. A file whose suffix is
not one of these is ignored by `list`/`collect` and flagged by `validate`.

Slugs are normalized to lowercase ASCII with `-` separators. Re-adding the same
slug **and** type updates the file in place; the same slug with a *different*
type is refused unless you pass `--force`, so you don't accidentally fork one
note into two categories.

Multi-line Markdown in the body is allowed and is rendered as a single list item.

## Where fragments live (directory discovery)

When you don't pass `--fragment-dir`, the directory is resolved in this order:

1. `[fragments].directory` in config (if set)
1. an existing `changelog.d/`
1. an existing `changes/`
1. an existing `.changelogmanager/fragments/`

If none of those exist, the first candidate (`changelog.d/`) is created on the
first write. `changelog.d/` is the recommended default because it matches the
convention used by other fragment tools.

## What happens to collected files (consumption)

After a successful collect, the source fragments are consumed according to
`--consume` (or `[fragments].consume` in config):

| Mode | Result |
|---|---|
| `archive` *(default)* | Move files to `archive/YYYY-MM-DD/` under the fragment folder, so past releases are auditable |
| `delete` | Remove the files |
| `keep` | Leave the files in place (handy when experimenting) |

```sh
changelogmanager fragments collect --consume delete
```

## Components

The **component selects the target `CHANGELOG.md`** for collection. When you run
under a component, `collect` writes into that component's changelog:

```sh
changelogmanager --component api fragments collect
```

The fragment *folder* itself is shared by default. To keep a component's
fragments in their own folder, point at it explicitly with `--fragment-dir`:

```sh
changelogmanager --component api fragments add added "Add API filtering" --fragment-dir api/changelog.d
changelogmanager --component api fragments collect            --fragment-dir api/changelog.d
```

## Configuration

Store fragment defaults in `changelogmanager.toml` or under
`[tool.changelogmanager]` in `pyproject.toml`:

```toml
[fragments]
directory = "changelog.d"     # where fragments live
consume   = "archive"         # archive | delete | keep
```

With these set you can drop the `--fragment-dir` and `--consume` flags from your
commands and CI scripts.

## Command reference

| Command | What it does |
|---|---|
| `fragments add TYPE TEXT [--slug S]` | Create or update a fragment file |
| `add --change-type TYPE --message TEXT --fragment [SLUG]` | Same, via the normal `add` command |
| `fragments list` | Show pending fragments grouped by type |
| `fragments validate` | Check filenames, types, content, and duplicates |
| `fragments collect [--dry-run] [--consume MODE]` | Move pending fragments into the changelog |

Common flags: `--fragment-dir PATH` overrides the folder on any of these;
`--component NAME` selects the target changelog; `--dry-run` previews `collect`
without writing.

## How this compares to the other staging workflows

| Workflow | File(s) | Flows into | Use it when |
|---|---|---|---|
| **Changelog fragments** *(this page)* | `changelog.d/<slug>.<type>.md` | `CHANGELOG.md` `[Unreleased]` | Each upcoming entry should ship with its branch, conflict-free |
| `TASKS.md` | one shared `TASKS.md` | `[Unreleased]` via `tasks promote` | You want a single planning checklist |
| Ticket task fragments | `tickets/*.md` | a generated `TASKS.md` | You want richer per-ticket planning notes |

See [Tasks and fragments](tasks.md) for the latter two.
