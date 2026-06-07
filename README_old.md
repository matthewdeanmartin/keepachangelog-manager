# (Keep a) Changelog Manager

Python tool to

- initialize a CHANGELOG.md
- backfill it with commits, PRs, etc
- CLI and GUI to edit and update entries
- Validate
- Create a Github or Gitlab release page with CHANGLOG.md as note.

It supports these standards

- [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
- Semantic Version, PEP 440, Calver
- Conventional Commits, Gitmoji (for backfill from commit messages)

This is a fork of `keepachangelog-manager`, originally mostly written by KevinDeJong at TomTom International, but now
archived.

## Install

```sh
uv tool install keepachangelog-manager-fork
```

The package name on PyPI is `keepachangelog-manager-fork`. The installed command is `changelogmanager` with legacy
alias of `keepachangelog-manager`.

Supports pre-commit, CLI, and GitHub Actions workflows.

## GUI

```sh
changelogmanager gui
```

The GUI now includes four screens: a live `[Unreleased]` editor, an initialize/backfill screen, a release publishing
screen for GitHub/GitLab, and a components screen for batch validation and `from-commits --all`.

![gui](https://raw.githubusercontent.com/matthewdeanmartin/keepachangelog-manager/main/resources/gui_edit_page.png)

## What it does

`keepachangelog-manager` helps you:

Edit entries

- create and validate changelogs
- add, edit, list, and remove `[Unreleased]` entries
- work with multi-component repositories (multiple changelog) via TOML config files

Flip Unreleased Changelog to a Released Changelog

- infer the next release from change types for SemVer, PEP 440, or CalVer projects
- release `[Unreleased]` with an optional confirmation guard

Initialize or bulk update Changelog

- seed `[Unreleased]` from git history using Conventional Commit subjects
- backfill missing released versions from local git tags

Many features for bash scripting ergonomics.

Online integration with Git Forge Release pages

- create or update GitHub and GitLab releases
- open or update a GitHub pull request for release automation

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

### Exports and scripting

Commands that produce structured output or integrate with CI:

```text
version       Print previous/current/future version
to-json       Export the changelog as JSON
to-html       Export the changelog as HTML
skill export  Export the bundled CLI skill for Copilot or Claude
```

For `--json`, `--quiet`, `jq` patterns, exit codes, and full `release.yml` examples, see
[Scripting and CI integration](docs/scripting.md).

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

## Configuration

Use `--config` to set switch defaults and `--component` for multi-component repositories:

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

## CLI Visuals

![gif](https://raw.githubusercontent.com/matthewdeanmartin/keepachangelog-manager/main/resources/usage.gif)

## Credits

### Vendored

- [`Colin-b/keepachangelog`](https://github.com/Colin-b/keepachangelog)
- [llvm_diagnostics](https://pypi.org/project/llvm-diagnostics/)

## Documentation

- [Generic CI](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/CI.md)
- [GitHub automation](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/github.md)
- [GitLab automation](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/gitlab.md)
- [Quick start](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/quickstart.md)
- [Installation](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/installation.md)
- [Key workflows](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/workflows.md)
- [Scripting and CI integration](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/scripting.md)
- [CLI reference](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/cli.md)
- [Desktop GUI](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/gui.md)
