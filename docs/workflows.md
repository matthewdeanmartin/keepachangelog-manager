# Key Workflows

For detailed release mechanics, see [Releasing](releases.md). For checklist-style planning and fragment-file staging, see [Tasks and fragments](tasks.md).

## Day-to-day development

### Add a change interactively

Run `add` without arguments to get a guided prompt:

```sh
changelogmanager add
```

You will be asked to choose a change type and type your message, then confirm before the file is written.

### Add a change non-interactively

Suitable for scripts and CI:

```sh
changelogmanager add --change-type fixed --message "Prevent crash on empty input"
```

Valid change types are: `added`, `changed`, `deprecated`, `removed`, `fixed`, `security`.

### Preview without writing

Every command accepts `--dry-run`. It runs all validation and prints what would happen, but does not modify any files:

```sh
changelogmanager add --change-type added --message "New feature" --dry-run
changelogmanager release --dry-run
```

______________________________________________________________________

## Maintaining `[Unreleased]`

### List entries before editing

```sh
changelogmanager remove --list
```

This prints each `[Unreleased]` entry as `[change-type] index: message`, which is the index format used by both `edit` and `remove`.

### Edit an existing entry

Update the text in place:

```sh
changelogmanager edit --change-type added --index 0 --message "Document the non-interactive release flow"
```

Recategorise an entry:

```sh
changelogmanager edit --change-type changed --index 1 --new-change-type fixed
```

You can combine `--message` and `--new-change-type` in the same command.

### Remove an entry

```sh
changelogmanager remove --change-type fixed --index 0
```

If removing the last entry in a section empties that change type, the section is removed automatically.

### Seed entries from commit history

```sh
changelogmanager from-commits
```

By default the command starts from the most recent git tag, then parses commit subjects using Conventional Commit-style prefixes:

| Commit prefix | Changelog bucket |
|---|---|
| `feat`, `feature` | `added` |
| `fix`, `bug` | `fixed` |
| `deprecate` | `deprecated` |
| `remove` | `removed` |
| `security`, `sec` | `security` |
| `docs`, `refactor`, `test`, `chore`, etc. | `changed` |

Breaking commits like `feat!:` are treated as `removed`, which produces a major version bump.

Useful variants:

```sh
changelogmanager from-commits --since v1.2.0
changelogmanager from-commits --all-history
changelogmanager from-commits --strict
```

`--strict` skips subjects that do not match the selected commit schema. Without it, unmatched subjects are added as
`changed`.

______________________________________________________________________

## Backfilling historical releases

### Backfill missing version sections from local history

```sh
changelogmanager backfill --source all --dry-run
changelogmanager backfill --source all
changelogmanager backfill --source tags --dry-run
changelogmanager backfill --source tags
```

This is aimed at repositories that already have release tags but either no `CHANGELOG.md` yet or gaps in the released sections. The command discovers local git tags, normalizes a leading `v`, filters them through the changelog's active versioning scheme, and adds only versions that are missing. With `--source all` or `--source commits`, it also reads commit subjects between tag intervals before falling back to tag placeholders.

Commit parsing supports `--commit-schema auto`, `conventional`, `gitmoji`, and `keepachangelog`. Auto tries all built-in schemas, so subjects like `feat: add export`, `:bug: fix parser`, and `Fixed: restore ordering` can all become typed changelog entries.

For each imported version, the tool uses an intentionally honest placeholder:

```markdown
### Changed

- Release notes unavailable; backfilled from tag `v1.2.3`.
```

That keeps the generated changelog valid without inventing release notes.

### Limit the range

```sh
changelogmanager backfill --source tags --since v1.0.0 --until v2.0.0
```

`--since` and `--until` accept either the exact tag name or the normalized version string.

### What happens today

- `--source tags` is the implemented path
- `--source commits` and `--source all` are local-only and use commits grouped by tag interval
- existing versions are skipped by default via `--missing-only`
- `--strategy merge --no-missing-only` additively backfills entries into existing versions while preserving their text; it is idempotent on re-runs
- `--include-unreleased` seeds `[Unreleased]` from commits since the latest release tag
- non-version tags are reported and skipped
- `--strategy replace` and the remote backfill sources (`github-releases`, `github-prs`, `pypi`) are not implemented; `replace` is intentionally unsupported because changelog entries have no stable identity

______________________________________________________________________

## Releasing

For local version calculation, `release`, `version`, and `--bump-versions`, see [Releasing](releases.md).

For forge-specific publishing flows, see [GitHub automation](github.md) and [GitLab automation](gitlab.md).

______________________________________________________________________

## Validation

### Basic validation

```sh
changelogmanager validate
```

The validator checks:

- Heading depth (maximum 3 levels)
- Version headings follow `## [version] - yyyy-mm-dd`, where `version` matches the configured scheme
- Change headings are one of the six allowed types
- Entries do not use sub-lists, numbered lists, or block quotes
- Versions are in descending order
- `[Unreleased]` is at the top

Warnings are also reported for:

- Empty version sections
- Empty change-type sections
- Duplicate entries within the same change-type section

### Autofix common issues

```sh
changelogmanager validate --fix
```

This can:

- repair safe layout issues before parsing, such as `## Unreleased`,
  `## Added`, miscased or near-miss change headings, simple entry wrappers,
  a leading `v` in release headings, and ISO date separator variants
- reorder released versions into descending configured-version order
- lowercase change-type headings such as `Added` -> `added`
- remove empty change-type sections
- deduplicate identical entries within a section

### Validate all configured components

```sh
changelogmanager --config changelogmanager.toml validate --all
changelogmanager --config changelogmanager.toml validate --all --changed-only
```

`--changed-only` uses `git status --porcelain` and skips configured components whose changelog files are unchanged.

### Initialize or update config interactively

```sh
changelogmanager config
changelogmanager config init
```

`config` shows the effective config plus where it came from. `config init` writes `changelogmanager.toml` or
`pyproject.toml` using interactive prompts, defaulting to `pyproject.toml` and `semver`. Re-running it updates the
active config with the current answers.

### Export the bundled CLI skill

```sh
changelogmanager skill export
changelogmanager skill export --path .github/skills
```

Without `--path`, the CLI prompts for a common Copilot or Claude skills location and writes the `keepachangelog-manager-cli` folder there.

### Enforce the canonical preamble

You can require the standard Keep a Changelog preamble from configuration:

```toml
[versioning]
scheme = "semver"

[validation]
enforce_preamble = true
```

If `versioning.scheme` is set to `pep440` or `calver`, `create` writes that scheme into the changelog preamble and validation expects the same wording.

### GitHub Actions format

```sh
changelogmanager --error-format github validate
```

Errors are printed in GitHub Actions annotation format (`::error file=...`), making them appear inline in pull request diffs.

______________________________________________________________________

## Exports

```sh
changelogmanager to-json
changelogmanager to-json --schema-version v1
changelogmanager to-html
```

Default output files:

| Command | Default output |
|---|---|
| `to-json` | `CHANGELOG.json` |
| `to-html` | `CHANGELOG.html` |

`to-json` writes one object per release. Example output:

```json
[
    {
        "metadata": {
            "version": "1.2.0",
            "release_date": "2024-05-01",
            "semantic_version": {
                "major": 1,
                "minor": 2,
                "patch": 0,
                "prerelease": null,
                "buildmetadata": null
            }
        },
        "added": [
            "New export command"
        ],
        "fixed": [
            "Handle missing release date gracefully"
        ]
    }
]
```

Use a custom filename:

```sh
changelogmanager to-json --file-name changelog-export.json
changelogmanager to-html --file-name changelog-export.html
```

`to-json` also accepts `--schema-version` so automation can pin the expected export contract.

______________________________________________________________________

## Multi-component repositories

When a single repository contains multiple packages, each with its own `CHANGELOG.md`, create a configuration file:

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

[[components]]
name = "default"
changelog = "CHANGELOG.md"
```

Then pass `--config` and `--component` to any command:

```sh
changelogmanager --config changelogmanager.toml --component "Client Interface" version
changelogmanager --config changelogmanager.toml --component "Service Component" release
```

`from-commits --all` uses each component's optional `match` globs to route commits by touched files. A component with
no `match` acts as the fallback bucket for commits that do not match any explicit component.

If `--config` is omitted, the CLI auto-detects `changelogmanager.toml`, `.changelogmanager.toml`, or
`[tool.changelogmanager]` in `pyproject.toml` from the current directory.

______________________________________________________________________

## Specifying a changelog file directly

If you do not use a config file, you can point at any file with `--input-file`:

```sh
changelogmanager --input-file packages/api/CHANGELOG.md validate
```

______________________________________________________________________

## Automation-friendly output

See [Scripting and CI integration](scripting.md) for `--json` / `--quiet` usage, exit codes,
`jq` patterns, and complete `release.yml` examples.
