# Key Workflows

For detailed release mechanics, see [Releasing](releases.md). For checklist and
fragment staging, see [Tasks and fragments](tasks.md).

## Day-to-day changelog editing

### Add a change interactively

```sh
changelogmanager add
```

You will be prompted for a change type and message, then asked to confirm.

### Add a change non-interactively

```sh
changelogmanager add --change-type fixed --message "Prevent crash on empty input"
```

Valid change types are `added`, `changed`, `deprecated`, `removed`, `fixed`,
and `security`.

### Write a fragment instead of editing `[Unreleased]`

```sh
changelogmanager add --change-type added --message "Support release previews" --fragment
changelogmanager add --change-type fixed --message "Preserve links" --fragment issue-123
```

### Preview without writing

Every mutating command accepts `--dry-run`.

```sh
changelogmanager add --change-type added --message "New feature" --dry-run
changelogmanager release --dry-run
changelogmanager backfill --source local --dry-run
```

## Maintaining `[Unreleased]`

### List entries before editing

```sh
changelogmanager remove --list
```

This prints each `[Unreleased]` entry as `[change-type] index: message`, which
is the selector format used by `edit` and `remove`.

### Edit an existing entry

```sh
changelogmanager edit --change-type added --index 0 --message "Document the non-interactive release flow"
changelogmanager edit --change-type changed --index 1 --new-change-type fixed
```

You can combine `--message` and `--new-change-type`.

### Remove an entry

```sh
changelogmanager remove --change-type fixed --index 0
```

If removing the last entry empties a change-type section, that section is
removed automatically.

## Seed notes from git history

### Seed `[Unreleased]` from commit subjects

```sh
changelogmanager from-commits
```

By default this starts at the most recent git tag and classifies subjects using
the selected schema.

Useful variants:

```sh
changelogmanager from-commits --since v1.2.0
changelogmanager from-commits --all-history
changelogmanager from-commits --strict
changelogmanager --config changelogmanager.toml from-commits --all
```

`--strict` skips subjects that do not match the selected schema. Without it,
unmatched subjects fall back to `changed`.

### Audit commit subjects before backfill

```sh
changelogmanager lint-commits
changelogmanager lint-commits --show all
changelogmanager lint-commits --strict
```

This is a read-only audit. It helps you spot subjects that would become noisy
`changed` entries during backfill.

### Plan rewrites for unpushed commits

```sh
changelogmanager rewrite-messages
changelogmanager rewrite-messages --plan-out rewrite-plan.tsv
```

This command is scoped to the unpushed range only (`@{upstream}..HEAD`) and is
currently plan-only. It never rewrites history today; it suggests cleaner
subjects you can apply yourself with `git commit --amend` or `git rebase -i`.

## Backfilling historical releases

### Backfill from local history

```sh
changelogmanager backfill --source local --dry-run
changelogmanager backfill --source local
changelogmanager backfill --source tags
```

This is the usual "adopt the tool in an existing repository" path. It walks git
tags, normalizes a leading `v`, filters them through the active versioning
scheme, and adds missing release sections.

### Backfill from online sources

```sh
changelogmanager backfill --source github-releases --repository owner/repo
changelogmanager backfill --source github-prs --repository owner/repo
changelogmanager backfill --source pypi --package my-package-name
changelogmanager backfill --source all --repository owner/repo
```

Source summary:

- `tags`: local git tags only
- `commits`: local commit intervals grouped by tags
- `local`: tags plus commits
- `github-releases`: GitHub Releases API
- `github-prs`: merged GitHub PRs grouped by tag dates
- `pypi`: PyPI release history
- `all`: local plus GitHub releases and PRs

### Seed `[Unreleased]` from commits since the latest tag

```sh
changelogmanager backfill --source local --include-unreleased
```

### Limit the range

```sh
changelogmanager backfill --source local --since v1.0.0 --until v2.0.0
```

### Merge into existing versions

```sh
changelogmanager backfill --source local --strategy merge --no-missing-only
```

`merge` is additive and intended to be idempotent on re-runs. `replace` is
listed for compatibility but intentionally unsupported because changelog entries
have no stable identity.

### Placeholder behavior

When the tool cannot recover richer notes for a release interval, it uses an
explicit placeholder rather than inventing text:

```markdown
### Changed

- Release notes unavailable; backfilled from tag `v1.2.3`.
```

## Validation

### Validate the current changelog

```sh
changelogmanager validate
```

The validator checks heading depth, version headings, change headings,
descending release order, entry formatting, and `[Unreleased]` placement.

### Autofix common problems

```sh
changelogmanager validate --fix
```

Autofix can normalize safe layout issues, reorder releases, remove empty
sections, and deduplicate identical entries. Add `--dry-run` to preview.

### Validate all configured components

```sh
changelogmanager --config changelogmanager.toml validate --all
changelogmanager --config changelogmanager.toml validate --all --changed-only
```

## Multi-component repositories

When one repository contains multiple packages, define components in config and
target them explicitly:

```toml
[versioning]
scheme = "pep440"

[[components]]
name = "Service Component"
changelog = "service/CHANGELOG.md"
match = ["service/**"]

[[components]]
name = "Client Interface"
changelog = "client/CHANGELOG.md"
match = ["client/**"]
```

Then run:

```sh
changelogmanager --config changelogmanager.toml --component "Client Interface" version
changelogmanager --config changelogmanager.toml --component "Service Component" release
```

## Export and automation helpers

```sh
changelogmanager to-json
changelogmanager to-html
changelogmanager skill export
changelogmanager credentials check
```

See [Scripting and CI integration](scripting.md) for `--json`, `--quiet`, exit
codes, and CI patterns.
