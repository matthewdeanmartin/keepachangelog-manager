# (Keep a) Changelog Manager

CLI and Python library for managing `CHANGELOG.md` files that follow
the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

Fork of `keepachangelog-manager`, originally mostly written by KevinDeJong at TomTom International.

![gif](https://raw.githubusercontent.com/matthewdeanmartin/keepachangelog-manager/main/resources/usage.gif)

## Vendored `keepachangelog`

This project now vendors a slimmed-down copy of
[`Colin-b/keepachangelog`](https://github.com/Colin-b/keepachangelog) under
`changelogmanager/vendor/keepachangelog/` instead of depending on the PyPI
package at runtime.

Credits:

- upstream project: [`Colin-b/keepachangelog`](https://github.com/Colin-b/keepachangelog)
- upstream license: MIT, copied to
  [`changelogmanager/vendor/keepachangelog/LICENSE`](changelogmanager/vendor/keepachangelog/LICENSE)

What we keep from it:

- `to_dict(...)`
- `to_dict(..., show_unreleased=True)`
- `from_dict(...)`
- release metadata and compare-link parsing

What we intentionally dropped:

- CLI entry points
- release automation helpers
- `to_raw_dict(...)`
- web framework integrations

The vendored subfolder also includes copied upstream parser/serializer tests in
`tests/test_vendored_keepachangelog/`.

## Install

```sh
uv tool install keepachangelog-manager-fork
```

The package name on PyPI is `keepachangelog-manager-fork`. The installed commands is `changelogmanager` with legacy
alias of `keepachangelog-manager`.

Supports precommit, cli, and GitHub actions workflows.

## What it does

`keepachangelog-manager` helps you:

- create and validate changelogs
- add, edit, list, and remove `[Unreleased]` entries
- infer the next SemVer release from change types
- release `[Unreleased]` with an optional confirmation guard
- seed `[Unreleased]` from git history using Conventional Commit subjects
- export changelogs as JSON, YAML, or HTML
- export a bundled CLI skill for Copilot or Claude
- create or update GitHub and GitLab releases
- work with multi-component repositories via config files
- script the CLI with `--dry-run`, `--quiet`, `--json`, `--info`, and `--verbose`
- use an optional Tkinter GUI for common workflows

## Commands

Commands are grouped below by what they do.

### File editing

Commands that read and rewrite your `CHANGELOG.md`.

```text
create        Create a new (empty) CHANGELOG.md
add           Add an entry to [Unreleased]
edit          Edit an existing [Unreleased] entry
remove        Remove an [Unreleased] entry (or --list them)
from-commits  Seed [Unreleased] from git commit history
```

### Machine readability

Commands and global flags for scripting and exporting structured data.

```text
version       Print previous/current/future version
to-json       Export the changelog as JSON
to-yaml       Export the changelog as YAML
to-html       Export the changelog as HTML
skill export  Export the bundled CLI skill for Copilot or Claude

--json        Emit a single machine-readable JSON object on stdout
--quiet       Suppress human-friendly output
--info        Runtime logging on stderr
--verbose     Verbose runtime logging on stderr (implies --info)
```

### Repo release tools

Commands that cut a release and publish it to a forge.

```text
release         Release [Unreleased] into a versioned section
github-release  Create/update a GitHub release from the changelog
gitlab-release  Create/update a GitLab release from the changelog
```

### Validation & setup

```text
validate      Validate the CHANGELOG.md (use --fix to autofix)
config        Show or initialize configuration (config init)
gui           Launch the optional Tkinter GUI
```

## Quick examples

Add an entry:

```sh
changelogmanager add --change-type added --message "Document the new release flow"
```

Edit or remove an existing `[Unreleased]` entry:

```sh
changelogmanager remove --list
changelogmanager edit --change-type added --index 0 --message "Document the guarded release flow"
changelogmanager remove --change-type added --index 0
```

Seed `[Unreleased]` from commit history:

```sh
changelogmanager from-commits
```

Validate and autofix common issues:

```sh
changelogmanager validate --fix
```

Release non-interactively:

```sh
changelogmanager release --yes
```

Publish a forge release from `[Unreleased]`:

```sh
changelogmanager github-release --repository owner/name
changelogmanager gitlab-release --project group/name
```

GitLab note: the default `CI_JOB_TOKEN` usually cannot create releases — use a
project/group/personal access token via `GITLAB_TOKEN`.
See [docs/CI.md](docs/CI.md#authentication-and-the-ci_job_token-caveat).

Export structured output:

```sh
changelogmanager to-json
changelogmanager to-yaml
changelogmanager to-html
```

Export the bundled CLI skill:

```sh
changelogmanager skill export
```

Machine-readable mode for scripts:

```sh
changelogmanager --json version --reference future
changelogmanager --quiet validate
changelogmanager --info validate
changelogmanager --verbose from-commits --dry-run
```

`--info` and `--verbose` enable stdlib runtime logging on stderr for diagnostics. `--verbose` is the more detailed level
and implies `--info`. Existing validation diagnostics still use the configured LLVM or GitHub Actions annotation format.

## Configuration

Use `--config` and `--component` for multi-component repositories:

```yaml
project:
  components:
    - name: Service
      changelog: service/CHANGELOG.md
    - name: Client
      changelog: client/CHANGELOG.md
  commits:
    style: conventional
  versioning:
    scheme: semver
  validation:
    enforce_preamble: false
```

```sh
changelogmanager --config .changelogmanager.yml --component Service validate
changelogmanager config
changelogmanager config init
changelogmanager skill export
```

If `--config` is omitted, the CLI auto-detects `.changelogmanager.yml`, `.changelogmanager.yaml`,
`changelogmanager.yml`, `changelogmanager.yaml`, or `[tool.changelogmanager]` in `pyproject.toml` from the current
directory.

`changelogmanager config init` is the quickest way to bootstrap config. It defaults to `pyproject.toml`,
`Conventional Commits`, and `semver`, and re-running it updates the active config instead of starting from scratch.

## Optional desktop GUI

```sh
changelogmanager gui
```

The GUI currently wraps the common commands `create`, `version`, `validate`, `release`, `to-json`, `add`, and
`github-release`.

## Documentation

- [CI and GitHub Actions](docs/CI.md)
- [Quick start](docs/quickstart.md)
- [Installation](docs/installation.md)
- [Key workflows](docs/workflows.md)
- [CLI reference](docs/cli.md)
- [Desktop GUI](docs/gui.md)
