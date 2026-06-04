# (Keep a) Changelog Manager

CLI and Python library for managing `CHANGELOG.md` files that follow
the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

Fork of `keepachangelog-manager`, originally mostly written by KevinDeJong at TomTom International.

![gif](https://raw.githubusercontent.com/matthewdeanmartin/keepachangelog-manager/main/resources/usage.gif)

and gui

![gui](https://raw.githubusercontent.com/matthewdeanmartin/keepachangelog-manager/main/resources/gui_edit_page.png)

## Install

```sh
uv tool install keepachangelog-manager-fork
```

The package name on PyPI is `keepachangelog-manager-fork`. The installed command is `changelogmanager` with legacy
alias of `keepachangelog-manager`.

Supports pre-commit, CLI, and GitHub Actions workflows.

## What it does

`keepachangelog-manager` helps you:

- create and validate changelogs
- add, edit, list, and remove `[Unreleased]` entries
- infer the next release from change types for SemVer, PEP 440, or CalVer projects
- release `[Unreleased]` with an optional confirmation guard
- seed `[Unreleased]` from git history using Conventional Commit subjects
- backfill missing released versions from local git tags
- export changelogs as JSON or HTML
- export a bundled CLI skill for Copilot or Claude
- create or update GitHub and GitLab releases
- open or update a GitHub pull request for release automation
- work with multi-component repositories via TOML config files
- script the CLI with `--dry-run`, `--quiet`, `--json`, `--info`, and `--verbose`
- use an optional Tkinter GUI for editing, backfill, release, and batch workflows

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
backfill      Backfill missing released versions from local git tags
```

### Machine readability

Commands and global flags for scripting and exporting structured data.

```text
version       Print previous/current/future version
to-json       Export the changelog as JSON
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
github-pr       Open/update a GitHub pull request for a changelog branch
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

Backfill an existing repo from local git history:

```sh
changelogmanager backfill --source all --dry-run
changelogmanager backfill --source all
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
See [docs/gitlab.md](docs/gitlab.md#authentication-and-the-ci_job_token-caveat).

Export structured output:

```sh
changelogmanager to-json
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

```toml
[versioning]
scheme = "semver"

[validation]
enforce_preamble = false

[[components]]
name = "Service"
changelog = "service/CHANGELOG.md"
match = ["service/**"]

[[components]]
name = "Client"
changelog = "client/CHANGELOG.md"
match = ["client/**"]
```

```sh
changelogmanager --config changelogmanager.toml --component Service validate
changelogmanager config
changelogmanager config init
changelogmanager skill export
```

If `--config` is omitted, the CLI auto-detects `changelogmanager.toml`, `.changelogmanager.toml`, or
`[tool.changelogmanager]` in `pyproject.toml` from the current directory.

`changelogmanager config init` is the quickest way to bootstrap config. It defaults to `pyproject.toml` and `semver`,
then prompts for preamble enforcement and the default component/changelog path. Re-running it updates the active config
instead of starting from scratch.

## Optional desktop GUI

```sh
changelogmanager gui
```

The GUI now includes four screens: a live `[Unreleased]` editor, an initialize/backfill screen, a release publishing
screen for GitHub/GitLab, and a components screen for batch validation and `from-commits --all`.

## Credits

### Vendored `keepachangelog`

- [`Colin-b/keepachangelog`](https://github.com/Colin-b/keepachangelog)
- llvm_diagnostics

## Documentation

- [Generic CI](docs/CI.md)
- [GitHub automation](docs/github.md)
- [GitLab automation](docs/gitlab.md)
- [Quick start](docs/quickstart.md)
- [Installation](docs/installation.md)
- [Key workflows](docs/workflows.md)
- [CLI reference](docs/cli.md)
- [Desktop GUI](docs/gui.md)
