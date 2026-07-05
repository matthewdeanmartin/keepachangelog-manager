# Pre-commit

> The CLI is invoked as `kaclm` (the canonical console script) or the longer
> `changelogmanager` alias — the examples below use whichever reads best in
> context. The older `keepachangelog-manager` and `kacl-gui` scripts are
> deprecated aliases.

`keepachangelog-manager` works well with `pre-commit` in two different ways:

- validate the changelog file itself
- lint commit subjects at the `commit-msg` stage so backfill stays clean later

## Validate `CHANGELOG.md` on every commit

This repository's own `.pre-commit-config.yaml` uses a local hook:

```yaml
repos:
  - repo: local
    hooks:
      - id: check
        name: changelog validate
        language: python
        entry: changelogmanager --error-format github validate
        additional_dependencies:
          - "."
        pass_filenames: false
        always_run: true
```

That pattern is a good fit when the project already depends on
`keepachangelog-manager` and you want to block malformed changelog edits early.

## Lint commit subjects with the exported hook

This repository also publishes a `commit-msg` hook in
`.pre-commit-hooks.yaml`:

```yaml
- id: changelog-message-lint
  name: Keep a Changelog commit message lint
  entry: changelogmanager-lint-message
  language: python
  stages: [commit-msg]
  always_run: true
```

Use it from another repository like this:

```yaml
repos:
  - repo: https://github.com/matthewdeanmartin/keepachangelog-manager
    rev: <tag>
    hooks:
      - id: changelog-message-lint
```

Then install the `commit-msg` stage:

```sh
pre-commit install --hook-type commit-msg
```

The hook `entry:` deliberately uses the standalone `changelogmanager-lint-message`
script rather than `kaclm lint-message`: the standalone script skips the full
CLI import graph (GUI / GitHub / GitLab / PyPI) so it starts fast on every
commit. The two are otherwise equivalent.

## What the commit-message hook checks

`changelogmanager-lint-message` (equivalently `kaclm lint-message`) reads the
commit message file passed by git or pre-commit and classifies the subject line
against the configured schema.

Supported schemas:

- `auto`
- `conventional`
- `gitmoji`
- `keepachangelog`

It exits:

- `0` when the subject is classifiable, skippable, or exempt
- `1` when the subject is unclassifiable
- `2` for usage or configuration errors

## Example direct usage

```sh
# fast-start standalone script (used by the pre-commit hook)
changelogmanager-lint-message .git/COMMIT_EDITMSG
changelogmanager-lint-message --schema keepachangelog .git/COMMIT_EDITMSG

# equivalent full-CLI subcommand
kaclm lint-message .git/COMMIT_EDITMSG
kaclm lint-message --schema keepachangelog .git/COMMIT_EDITMSG
```

## Why use this instead of CI autofix

For teams that want early feedback, pre-commit is usually a better place than CI
for preventing bad changelog structure or low-signal commit subjects from ever
landing in the repo.
