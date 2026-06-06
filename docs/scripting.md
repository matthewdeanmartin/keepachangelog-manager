# Scripting and CI Integration

This page covers machine-readable output, exit codes, `jq` patterns, and complete CI workflow
examples. It is aimed at shell scripts, GitHub Actions jobs, and any automation that consumes the
CLI non-interactively.

For day-to-day interactive use, see [Key workflows](workflows.md).
For the full option reference, see [CLI reference](cli.md).

---

## Exit codes

The CLI uses two exit codes:

| Code | Meaning |
|------|---------|
| `0` | Success — or a non-fatal info/warning diagnostic |
| `1` | Error — command failed, validation found errors, or a precondition was not met |

`validate` exits `1` when there are errors; warnings alone still produce `0`. All other commands
exit `1` only on hard failures (missing `[Unreleased]`, bad version, API error, etc.).

There is no exit code `2` for "usage error" — a bad flag causes argparse to print help and exit `2`
via the standard library, not via the CLI dispatch.

---

## Machine-readable flags

| Flag | Effect |
|------|--------|
| `--json` | Emit a single JSON object to stdout instead of human text |
| `--quiet` | Suppress non-error human output; diagnostics and exit codes still work |

`--json` and `--quiet` are global flags that go **before** the command name:

```sh
changelogmanager --json version --reference future
changelogmanager --quiet validate
```

Runtime logs (`--info`, `--verbose`) always go to stderr and never pollute stdout.

---

## JSON output shapes

### `version`

```sh
changelogmanager --json version --reference future
```

```json
{
  "version": "1.4.0",
  "reference": "future"
}
```

### `validate`

```sh
changelogmanager --json validate
```

```json
{
  "valid": true,
  "errors": [],
  "warnings": []
}
```

On failure the array contains diagnostic objects with `file`, `line`, `col`, and `message`.

### `release`

```sh
changelogmanager --json release --yes
```

```json
{
  "released": "1.4.0"
}
```

With `--bump-versions`:

```json
{
  "released": "1.4.0",
  "bumped_version": "1.4.0",
  "bumped_files": ["pyproject.toml", "mypackage/__about__.py"]
}
```

### `remove --list`

```sh
changelogmanager --json remove --list
```

```json
{
  "entries": [
    {"change_type": "added", "index": 0, "message": "Support dark mode"},
    {"change_type": "fixed", "index": 0, "message": "Crash on empty input"}
  ]
}
```

### `remove --count`

Prints the total number of unreleased entries as a bare integer — no `jq` needed:

```sh
changelogmanager remove --count   # prints e.g. "2"
```

With `--json`:

```sh
changelogmanager --json remove --count
```

```json
{ "count": 2 }
```

### `github-release`

```sh
changelogmanager --json github-release --repository owner/repo
```

```json
{
  "release_state": "draft",
  "version": "1.4.0",
  "html_url": "https://github.com/owner/repo/releases/tag/v1.4.0"
}
```

### `from-commits`

```sh
changelogmanager --json from-commits
```

```json
{
  "added": 3,
  "skipped": 1,
  "since": "v1.3.0"
}
```

### `backfill`

```sh
changelogmanager --json backfill --source tags --dry-run
```

```json
{
  "unreleased_added": 0,
  "since": null
}
```

---

## Extracting values with `jq`

Capture the next version into a shell variable:

```sh
NEXT_VERSION=$(changelogmanager --json version --reference future | jq -r '.version')
echo "Next release: $NEXT_VERSION"
```

Check whether validation passed:

```sh
RESULT=$(changelogmanager --json validate)
if echo "$RESULT" | jq -e '.valid == false' > /dev/null; then
  echo "Changelog has errors:" >&2
  echo "$RESULT" | jq -r '.errors[] | "\(.file):\(.line): \(.message)"' >&2
  exit 1
fi
```

List all unreleased entries:

```sh
changelogmanager --json remove --list \
  | jq -r '.entries[] | "[\(.change_type)] \(.message)"'
```

Check whether there are any unreleased entries before attempting a release:

```sh
COUNT=$(changelogmanager remove --count)
if [ "$COUNT" -eq 0 ]; then
  echo "Nothing to release." >&2
  exit 0
fi
```

Get all files that were version-bumped by `release --bump-versions`:

```sh
BUMPED=$(changelogmanager --json release --bump-versions --yes \
  | jq -r '.bumped_files[]')
git add CHANGELOG.md $BUMPED
```

---

## Typical release.yml patterns

The most common automation context is a GitHub Actions release job. The examples below assume
`changelogmanager` is installed into the job's virtualenv via `uv`.

### Minimal: validate on every PR

```yaml
- name: Validate changelog
  run: uv run changelogmanager --error-format github validate
```

`--error-format github` makes errors appear as inline annotations on the pull request diff.
The job fails automatically on exit code `1`.

### Release triggered by publishing a GitHub draft release

This is the pattern used in this repository. A separate workflow keeps a draft release in sync
with `[Unreleased]` on every push to `main`. When you publish that draft, a `release` event fires
and the following job runs.

```yaml
jobs:
  bump:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Install with jiggle extra
        run: uv sync --frozen --extra jiggle

      - name: Release changelog and bump versions
        run: |
          VERSION="${{ github.event.release.tag_name }}"
          VERSION="${VERSION#v}"   # strip leading v
          uv run changelogmanager release \
            --override-version "$VERSION" \
            --bump-versions \
            --yes

      - name: Commit and push bump branch
        run: |
          VERSION="${{ github.event.release.tag_name }}"
          BRANCH="release/bump-${{ github.run_id }}"
          git checkout -b "$BRANCH"
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add CHANGELOG.md pyproject.toml
          git commit -m "chore: release ${VERSION}"
          git push origin "$BRANCH"

      - name: Open or update release PR
        run: |
          VERSION="${{ github.event.release.tag_name }}"
          BRANCH="release/bump-${{ github.run_id }}"
          uv run changelogmanager github-pr \
            --repository "${{ github.repository }}" \
            --head "$BRANCH" \
            --base "${{ github.event.release.target_commitish }}" \
            --title "chore: release ${VERSION}"

  build:
    needs: bump
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: "release/bump-${{ github.run_id }}"
      - uses: astral-sh/setup-uv@v5
      - run: uv build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: release
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
```

### Keep a draft GitHub release in sync with `[Unreleased]`

Run this on every push to `main` so reviewers always see the current draft before publishing:

```yaml
- name: Update draft release
  run: |
    uv run changelogmanager github-release \
      --repository "${{ github.repository }}"
```

### Validate and auto-fix in CI (opt-in)

Preview what `--fix` would change without rewriting tracked files:

```yaml
- name: Preview changelog fixes
  run: uv run changelogmanager validate --fix --dry-run
```

If you want CI to commit autofixes automatically:

```yaml
- name: Autofix changelog
  run: |
    uv run changelogmanager validate --fix
    if ! git diff --quiet CHANGELOG.md; then
      git config user.name  "github-actions[bot]"
      git config user.email "github-actions[bot]@users.noreply.github.com"
      git add CHANGELOG.md
      git commit -m "chore: autofix changelog"
      git push
    fi
```

---

## Scripting guard patterns

### Skip gracefully when `[Unreleased]` is empty

`release` already exits `0` with a skip notice when `[Unreleased]` has no entries, so most CI
jobs need no guard at all:

```sh
changelogmanager release --yes   # safe to call unconditionally
```

If your script needs to branch on whether a release actually happened, check the `--json` output:

```sh
RESULT=$(changelogmanager --json release --yes)
if echo "$RESULT" | jq -e '.skipped' > /dev/null 2>&1; then
  echo "Nothing to release."
else
  VERSION=$(echo "$RESULT" | jq -r '.released')
  echo "Released $VERSION"
fi
```

Or use `remove --count` to check up front without `jq`:

```sh
if [ "$(changelogmanager remove --count)" -eq 0 ]; then
  echo "Nothing to release." >&2
  exit 0
fi
changelogmanager release --yes
```

### Gate on validation before releasing

```sh
changelogmanager validate || { echo "Fix changelog errors before releasing." >&2; exit 1; }
changelogmanager release --yes
```

### Capture next version before it is promoted

```sh
NEXT=$(changelogmanager --json version --reference future | jq -r '.version')
changelogmanager release --yes
echo "Released $NEXT"
```

### Non-interactive add in a commit hook

```sh
# In .git/hooks/post-commit or a CI step
SUBJECT=$(git log -1 --format=%s)
changelogmanager add \
  --change-type changed \
  --message "$SUBJECT" \
  --quiet
```

---

## Scripting behaviors to be aware of

- **`release` requires `--yes` in non-interactive contexts.** Without it the command detects no
  TTY and refuses. This is intentional — accidental releases in CI are hard to undo.
- **`release` exits `0` when `[Unreleased]` is empty.** If the `[Unreleased]` heading exists but
  has no entries, `release` prints a skip notice and exits `0` — so a "nothing to release" run
  does not fail a CI job. It still exits `1` if there is no `[Unreleased]` section at all.
- **`--dry-run` writes nothing.** All commands support `--dry-run`; use it to validate inputs
  before committing to a destructive change in CI.
- **`--json` does not suppress stderr diagnostics.** Validation errors printed by `validate` in
  LLVM/GitHub format still go to stderr even with `--json`. Redirect stderr if you want a
  completely clean stdout pipe.
- **Exit code `0` on warnings.** `validate` exits `0` for warnings. If your script needs to
  distinguish warnings from a clean run, parse the `--json` output and inspect `.warnings`.
