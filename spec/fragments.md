# Changelog fragments

Status: **proposed** · Owner: TBD · Last updated: 2026-06-06

## Goal

Add release-fragment support as an offline-first collection workflow.

A fragment is a small file that represents one future changelog entry. During release
preparation, the app collects fragments, deduplicates and validates them, writes them
into `[Unreleased]` or a target version, and then archives or deletes the consumed
fragment files.

This complements `TASKS.md`: task files are a mutable TODO list; fragments are the
reviewable collection of finished change notes waiting to be assembled.

## Non-goals

- Replacing the main `CHANGELOG.md`.
- Implementing every Towncrier or Scriv convention.
- Requiring GitHub, issue numbers, or pull requests.
- Performing natural-language classification of arbitrary fragment text.

## Fragment directory

Default discovery:

1. `changelog.d/`
1. `changes/`
1. `.changelogmanager/fragments/`
1. Configured `[fragments].directory`

Suggested config:

```toml
[fragments]
directory = "changelog.d"
format = "markdown"          # markdown for phase 1
consume = "archive"          # archive | delete | keep
archive_directory = "changelog.d/archive"
```

The default should be `changelog.d/` because it is already familiar from fragment
tools in the Python ecosystem.

## Fragment shape

Phase 1 supports one Markdown file per changelog bullet.

Filename:

```text
<slug>.<type>.md
```

Examples:

```text
changelog.d/task-files.added.md
changelog.d/fragment-collection.changed.md
changelog.d/issue-123.fixed.md
changelog.d/security-redaction.security.md
```

Supported type suffixes:

- `added`
- `changed`
- `deprecated`
- `removed`
- `fixed`
- `security`

File content is the changelog bullet text, without the leading `- `:

```md
Support `TASKS.md` as a first-class changelog input.
```

Multi-line Markdown is allowed. On collection, the renderer should indent continuation
lines so the entry remains a valid Markdown list item.

## Optional metadata

Phase 1 should not require front matter. A later phase may support optional metadata
for richer workflows:

```md
---
type: added
refs:
  - "#123"
component: api
---

Support fragment collection for component changelogs.
```

If front matter is introduced, filename type and front matter type must agree. Until
then, the filename is the source of truth.

## CLI surface

Fragments are both a command group and an alternate write target for existing change
creation flows.

Command group:

```sh
changelogmanager fragments COMMAND [OPTIONS]
```

Initial commands:

| Command | Description |
|---|---|
| `fragments list` | Show pending fragments grouped by KAC type. |
| `fragments add TYPE TEXT` | Create or update a fragment file. |
| `fragments edit FRAGMENT` | Edit an existing fragment. |
| `fragments remove FRAGMENT` | Delete or archive a fragment. |
| `fragments collect` | Move pending fragments into the changelog. |
| `fragments validate` | Validate filenames, types, and content. |

## `--fragment` switch

Existing commands that currently write directly to the changelog should accept a
`--fragment` switch:

```sh
changelogmanager add added "Support task files." --fragment
changelogmanager add fixed "Preserve links during promotion." --fragment issue-123
```

Behavior:

- With `--fragment`, the command writes to the fragment directory instead of
  `[Unreleased]`.
- If `--fragment` is passed without a value, derive a slug from the entry text.
- If `--fragment NAME` is passed, use `NAME` as the slug.
- If the target fragment already exists, update it rather than creating a duplicate.
- The command should print the fragment path it created or updated.

The switch should be available anywhere the app creates an unreleased changelog entry.
At minimum this includes the `add` path. Follow-up support can extend it to GitHub
issue imports, task promotion, and commit-derived entries.

## Collection command

`fragments collect` assembles pending fragments into the active changelog:

```sh
changelogmanager fragments collect
changelogmanager fragments collect --fragment-dir changelog.d --input-file CHANGELOG.md
changelogmanager fragments collect --version 1.4.0
changelogmanager fragments collect --dry-run
```

Options:

| Option | Default | Description |
|---|---|---|
| `--fragment-dir PATH` | discovered | Fragment directory to read |
| `--version VERSION` | `Unreleased` | Target changelog version section |
| `--consume archive|delete|keep` | config | What to do with collected fragments |
| `--dry-run` | `false` | Preview without writing |
| `--allow-empty` | `false` | Succeed when no fragments exist |

Collection rules:

- Group fragments by KAC type.
- Preserve deterministic ordering by filename within each type.
- Add entries to the target section without duplicating existing identical text.
- Validate the resulting changelog before writing unless validation is explicitly
  disabled by existing project conventions.
- Consume fragments only after the changelog write succeeds.

Archive behavior:

```text
changelog.d/archive/2026-06-06/task-files.added.md
```

The archive path uses the collection date so past release assembly can be audited
without keeping pending fragments noisy.

## Fragment updates

`fragments add` and `add --fragment` should be update-friendly:

- Same slug and type updates the existing file content.
- Same slug with a different type is an error unless `--force` is supplied.
- Slugs are normalized to lowercase ASCII with words separated by `-`.
- Empty fragment content is rejected.

This makes fragments comfortable for iterative work: a user can refine the release
note as the implementation changes instead of accumulating duplicate files.

## Components

Fragments should respect configured components:

```sh
changelogmanager add added "Add API filtering." --component api --fragment
changelogmanager fragments collect --component api
```

Initial component behavior:

- A component may configure its own fragment directory in config.
- Without a component-specific directory, the global fragment directory is used.
- Collection writes to the changelog selected by `--component`.

Possible config:

```toml
[[components]]
name = "api"
changelog = "api/CHANGELOG.md"
fragment_directory = "api/changelog.d"
```

## Validation

`fragments validate` checks:

- File names end in a supported type suffix.
- Fragment content is non-empty after trimming whitespace.
- Fragment type maps to a known Keep a Changelog section.
- Optional metadata, if present in the future, agrees with filename type.
- Duplicate fragment text within the same type is reported.

Diagnostics should include file paths and, when possible, line numbers.

## Data model

Normalize fragments before collection:

```python
@dataclass
class ChangelogFragment:
    path: Path
    slug: str
    change_type: str
    text: str
    refs: list[str]
    component: str | None = None
```

The model should be independent of the final storage format so future front matter or
alternate fragment layouts do not leak into collection logic.

## Testing plan

- Filename parser tests for valid and invalid suffixes.
- Slug generation tests for `--fragment` without an explicit name.
- `add --fragment` tests for create, update, conflicting type, and empty content.
- Collection tests that prove fragments land under the right KAC sections.
- Idempotency tests: repeated collection with `--consume keep` does not duplicate
  changelog entries.
- Dry-run tests proving neither fragments nor changelog files are written.
- Component tests for component-specific fragment directories.
- Tests must use temporary directories and the existing isolated cwd fixture.

## Open questions

- Should collected fragments go to `[Unreleased]` by default, or should release flows
  collect directly into the new version section?
- Should fragment archive paths be grouped by collection date, target version, or both?
- Should task promotion be able to create fragments instead of writing directly to
  `[Unreleased]`?
- Should `backfill` and GitHub issue imports support `--fragment` from the start?

