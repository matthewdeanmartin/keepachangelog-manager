# CLI Reference

All commands use:

```text
changelogmanager [GLOBAL OPTIONS] COMMAND [COMMAND OPTIONS]
```

## Global options

| Option | Default | Description |
|---|---|---|
| `--config` | auto-detect | Path to `changelogmanager.toml`, `.changelogmanager.toml`, or `pyproject.toml` |
| `--component` | `default` | Component name from config |
| `-f`, `--error-format` | `llvm` | Diagnostic format: `llvm` or `github` |
| `--input-file` | `CHANGELOG.md` | Changelog path to operate on |
| `--info` | off | Enable runtime info/warning/error logs on stderr |
| `--verbose` | off | Verbose logs on stderr |
| `--quiet` | off | Suppress normal human output |
| `--json` | off | Emit one JSON object on stdout |

If `--config` is omitted, the CLI looks for `changelogmanager.toml`,
`.changelogmanager.toml`, or `[tool.changelogmanager]` in `pyproject.toml`.

`github` format is best for GitHub Actions annotations. `llvm` remains useful
for local terminal use, editor integration, non-GitHub CI, and any context
where file:line diagnostics are easier to read than workflow commands.

## Core changelog commands

### `create`

Create a new changelog.

```sh
changelogmanager create [--dry-run]
```

### `config`

Show the effective configuration.

```sh
changelogmanager config
```

Interactive bootstrap or update:

```sh
changelogmanager config init
```

### `skill export`

Export the bundled `keepachangelog-manager-cli` skill directory.

```sh
changelogmanager skill export [--path PATH] [--dry-run]
```

### `version`

Print a version derived from the changelog.

```sh
changelogmanager version [--reference previous|current|future]
```

### `validate`

Validate the changelog.

```sh
changelogmanager validate [--fix] [--all] [--changed-only] [--format|--no-format] [--dry-run]
```

`--fix` can normalize safe layout issues, reorder releases, remove empty
sections, and deduplicate entries.

### `release`

Promote `[Unreleased]` to a dated release.

```sh
changelogmanager release [--override-version VERSION] [--yes] [--bump-versions] [--pyproject-only] [--dry-run]
```

`--bump-versions` requires the `jiggle` extra.

### `to-json`

Export the changelog to JSON.

```sh
changelogmanager to-json [--file-name FILE] [--schema-version VERSION] [--dry-run]
```

### `to-html`

Export the changelog to HTML.

```sh
changelogmanager to-html [--file-name FILE] [--dry-run]
```

### `add`

Add a new changelog entry.

```sh
changelogmanager add [--change-type TYPE] [--message TEXT] [--fragment [SLUG]] [--fragment-dir DIR] [--dry-run]
```

If `--fragment` is used, the entry is written as a changelog fragment instead of
editing `[Unreleased]`.

### `remove`

List or remove unreleased entries.

```sh
changelogmanager remove --list
changelogmanager remove --count
changelogmanager remove --change-type TYPE --index N [--dry-run]
```

### `edit`

Edit an unreleased entry.

```sh
changelogmanager edit --change-type TYPE --index N [--message TEXT] [--new-change-type TYPE] [--dry-run]
```

## Task and fragment staging

### `tasks`

Manage a lightweight `TASKS.md` file.

```sh
changelogmanager tasks list [--tasks-file FILE]
changelogmanager tasks add TYPE MESSAGE [--tasks-file FILE]
changelogmanager tasks check SELECTOR [--tasks-file FILE]
changelogmanager tasks uncheck SELECTOR [--tasks-file FILE]
changelogmanager tasks validate [--tasks-file FILE]
changelogmanager tasks promote [--tasks-file FILE] [--keep] [--dry-run]
```

### `tasks assemble`

Assemble richer `tickets/*.md` fragments into `TASKS.md`.

```sh
changelogmanager tasks assemble [--tickets-dir DIR] [--tasks-file FILE] [--rich] [--dry-run]
```

### `tasks new`

Scaffold a new task fragment in `tickets/`.

```sh
changelogmanager tasks new SUMMARY [--category CATEGORY] [--tickets-dir DIR]
```

Supported categories include normal Keep a Changelog buckets plus planning
categories such as `internal`, `chore`, `docs`, `test`, and `spike`.

### `tasks fragments lint`

Lint ticket fragments without writing.

```sh
changelogmanager tasks fragments lint [--tickets-dir DIR] [--strict]
```

### `fragments`

Manage changelog fragment files such as `changelog.d/issue-123.fixed.md`.

```sh
changelogmanager fragments list [--fragment-dir DIR]
changelogmanager fragments add TYPE MESSAGE [--slug SLUG] [--fragment-dir DIR]
changelogmanager fragments validate [--fragment-dir DIR]
changelogmanager fragments collect [--fragment-dir DIR] [--consume archive|delete|keep] [--dry-run]
```

## History seeding and backfill

### `backfill`

Backfill missing release sections from existing history.

```sh
changelogmanager backfill [--source SOURCE] [--repository OWNER/REPO] [--package NAME] [--since REF] [--until REF] [--missing-only|--no-missing-only] [--include-unreleased] [--strategy conservative|merge|replace] [--commit-schema auto|conventional|gitmoji|keepachangelog] [--max-commits N] [--dry-run]
```

Sources:

- `tags`
- `commits`
- `local`
- `github-releases`
- `github-prs`
- `pypi`
- `all`

### `from-commits`

Seed `[Unreleased]` from git commit subjects.

```sh
changelogmanager from-commits [--since REF] [--all-history] [--all] [--strict] [--commit-schema auto|conventional|gitmoji|keepachangelog] [--dry-run]
```

`--all` routes commits into all configured components by their `match` globs.

## Commit message quality tools

### `lint-commits`

Audit commit subjects against the supported changelog schemas.

```sh
changelogmanager lint-commits [--since REF] [--until REF] [--all-history] [--commit-schema auto|conventional|gitmoji|keepachangelog] [--show fail|skip|pass|all] [--strict] [--max-commits N] [--dry-run]
```

This is read-only and useful as a CI gate.

### `rewrite-messages`

Plan subject rewrites for the **unpushed** commit range only.

```sh
changelogmanager rewrite-messages [--commit-schema auto|conventional|gitmoji|keepachangelog] [--plan-out FILE] [--auto-prefix TYPE] [--apply] [--yes] [--max-commits N]
```

Current behavior:

- planning is implemented
- output can go to stdout or TSV
- `--apply` is intentionally not implemented yet and fails fast after the consent gate

## GitHub and GitLab automation

### `github-release`

Create or update a GitHub release from `[Unreleased]`.

```sh
changelogmanager github-release [--repository OWNER/REPO] [--github-token TOKEN] [--draft|--release] [--dry-run]
```

### `github-pr`

Open or update a GitHub pull request.

```sh
changelogmanager github-pr [--repository OWNER/REPO] [--head BRANCH] [--base BRANCH] [--title TEXT] [--body TEXT] [--github-token TOKEN] [--dry-run]
```

### `gitlab-release`

Create or update a GitLab release from `[Unreleased]`.

```sh
changelogmanager gitlab-release [--project ID_OR_PATH] [--gitlab-token TOKEN] [--gitlab-url URL] [--ref REF] [--dry-run]
```

## Stored credentials

Manage API tokens in the OS keyring.

```sh
changelogmanager credentials set github
changelogmanager credentials set gitlab
changelogmanager credentials clear github
changelogmanager credentials clear gitlab
changelogmanager credentials check
```

The CLI uses these stored tokens for GitHub and GitLab commands when applicable.

## GUI

Launch the Tkinter GUI:

```sh
changelogmanager gui
```

The GUI currently exposes screens for editing, tasks, fragments, backfill,
commit lint, releases, batch component operations, and export tools.
