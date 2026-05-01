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

---

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

---

## Querying versions

```sh
# most recently released version
changelogmanager version

# the version before that
changelogmanager version --reference previous

# what the next release would be, based on Unreleased changes
changelogmanager version --reference future
```

---

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

### GitHub Actions format

```sh
changelogmanager --error-format github validate
```

Errors are printed in GitHub Actions annotation format (`::error file=...`), making them appear inline in pull request diffs.

---

## GitHub releases

### Create a draft release

```sh
changelogmanager github-release \
  --github-token "$GITHUB_TOKEN" \
  --repository owner/repo
```

This deletes any existing draft releases and creates a new draft from the `[Unreleased]` section. The release tag is set to the inferred future version.

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
    changelogmanager release
    changelogmanager github-release \
      --github-token "${{ secrets.GITHUB_TOKEN }}" \
      --repository "${{ github.repository }}" \
      --release
```

---

## JSON export

```sh
changelogmanager to-json
```

Writes `CHANGELOG.json` with one object per release. Example output:

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
```

---

## Multi-component repositories

When a single repository contains multiple packages, each with its own `CHANGELOG.md`, create a YAML configuration file:

```yaml
project:
  components:
    - name: Service Component
      changelog: service/CHANGELOG.md
    - name: Client Interface
      changelog: client/CHANGELOG.md
```

Then pass `--config` and `--component` to any command:

```sh
changelogmanager --config config.yml --component "Client Interface" version
changelogmanager --config config.yml --component "Service Component" release
```

---

## Specifying a changelog file directly

If you do not use a config file, you can point at any file with `--input-file`:

```sh
changelogmanager --input-file packages/api/CHANGELOG.md validate
```
