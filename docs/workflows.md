# Key Workflows

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

`--strict` skips non-Conventional Commit subjects. Without it, unmatched subjects are added as `changed`.

______________________________________________________________________

## Releasing

### Automatic version bump

`release` inspects the change types in `[Unreleased]` and bumps the version according to SemVer:

| Change type present | Bump |
|---|---|
| `removed` | Major |
| `added` or `security` | Minor |
| `changed`, `deprecated`, `fixed` only | Patch |

```sh
changelogmanager release
```

### Override the version

```sh
changelogmanager release --override-version 2.0.0
```

The `v` prefix is accepted and stripped automatically (`v2.0.0` becomes `2.0.0`).

### Non-interactive releases

For scripts, CI, or any non-interactive run, add `--yes`:

```sh
changelogmanager release --yes
```

Without `--yes`, non-interactive release runs are refused. Pair it with `--dry-run` first if you want a preview.

______________________________________________________________________

## Querying versions

```sh
# most recently released version
changelogmanager version

# the version before that
changelogmanager version --reference previous

# what the next release would be, based on Unreleased changes
changelogmanager version --reference future
```

______________________________________________________________________

## Validation

### Basic validation

```sh
changelogmanager validate
```

The validator checks:

- Heading depth (maximum 3 levels)
- Version headings follow `## [x.y.z] - yyyy-mm-dd`
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

- reorder released versions into descending SemVer order
- lowercase change-type headings such as `Added` -> `added`
- remove empty change-type sections
- deduplicate identical entries within a section

### Validate all configured components

```sh
changelogmanager --config .changelogmanager.yml validate --all
changelogmanager --config .changelogmanager.yml validate --all --changed-only
```

`--changed-only` uses `git status --porcelain` and skips configured components whose changelog files are unchanged.

### Initialize or update config interactively

```sh
changelogmanager config
changelogmanager config init
```

`config` shows the effective config plus where it came from. `config init` writes YAML or `pyproject.toml` using interactive prompts, defaulting to `pyproject.toml`, `Conventional Commits`, and `semver`. Re-running it updates the active config with the current answers.

### Export the bundled CLI skill

```sh
changelogmanager skill export
changelogmanager skill export --path .github/skills
```

Without `--path`, the CLI prompts for a common Copilot or Claude skills location and writes the `keepachangelog-manager-cli` folder there.

### Enforce the canonical preamble

You can require the standard Keep a Changelog preamble from configuration:

```yaml
project:
  commits:
    style: conventional
  versioning:
    scheme: semver
  validation:
    enforce_preamble: true
```

If `versioning.scheme` is set to `pep440` or `calver`, `create` writes that scheme into the changelog preamble and validation expects the same wording.

### GitHub Actions format

```sh
changelogmanager --error-format github validate
```

Errors are printed in GitHub Actions annotation format (`::error file=...`), making them appear inline in pull request diffs.

______________________________________________________________________

## GitHub releases

### Create a draft release

```sh
changelogmanager github-release \
  --repository owner/repo
```

This deletes any existing draft releases and creates a new draft from the `[Unreleased]` section. The release tag is set to the inferred future version.

If `--github-token` is omitted, the command falls back to the `GITHUB_TOKEN` environment variable.

### Publish the release immediately

```sh
changelogmanager github-release \
  --github-token "$GITHUB_TOKEN" \
  --repository owner/repo \
  --release
```

### Typical CI pattern

```yaml
- name: Create GitHub release
  run: |
    changelogmanager github-release \
      --repository "${{ github.repository }}" \
      --release
```

Run `github-release` while `[Unreleased]` still exists. If you also want to rewrite `CHANGELOG.md`, do that in a later step or workflow with `changelogmanager release --override-version "$TAG"` after the GitHub release tag is known.

______________________________________________________________________

## Exports

```sh
changelogmanager to-json
changelogmanager to-yaml
changelogmanager to-html
```

Default output files:

| Command | Default output |
|---|---|
| `to-json` | `CHANGELOG.json` |
| `to-yaml` | `CHANGELOG.yaml` |
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
changelogmanager to-yaml --file-name changelog-export.yaml
changelogmanager to-html --file-name changelog-export.html
```

______________________________________________________________________

## Multi-component repositories

When a single repository contains multiple packages, each with its own `CHANGELOG.md`, create a configuration file:

```yaml
project:
  components:
    - name: Service Component
      changelog: service/CHANGELOG.md
    - name: Client Interface
      changelog: client/CHANGELOG.md
  commits:
    style: component-is-substring
  versioning:
    scheme: pep440
```

Then pass `--config` and `--component` to any command:

```sh
changelogmanager --config config.yml --component "Client Interface" version
changelogmanager --config config.yml --component "Service Component" release
```

If `--config` is omitted, the CLI auto-detects `.changelogmanager.yml`, `.changelogmanager.yaml`, `changelogmanager.yml`, `changelogmanager.yaml`, or `[tool.changelogmanager]` in `pyproject.toml` from the current directory.

______________________________________________________________________

## Specifying a changelog file directly

If you do not use a config file, you can point at any file with `--input-file`:

```sh
changelogmanager --input-file packages/api/CHANGELOG.md validate
```

______________________________________________________________________

## Automation-friendly output

Suppress human-friendly output:

```sh
changelogmanager --quiet validate
```

Emit a single JSON object to stdout:

```sh
changelogmanager --json version --reference future
changelogmanager --json remove --list
```

`--json` is useful for CI or wrapper scripts that need structured output. For destructive non-interactive workflows such as `release`, combine it with the command's explicit confirmation flags, for example `changelogmanager --json release --yes`.
