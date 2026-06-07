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
- keep future release notes in `TASKS.md` and promote finished items into `[Unreleased]`
- work with multi-component repositories (multiple changelog) via TOML config files

Flip Unreleased Changelog to a Released Changelog

- infer the next release from change types for SemVer, PEP 440, or CalVer projects
- release `[Unreleased]` with an optional confirmation guard

Initialize or bulk update Changelog

- seed `[Unreleased]` from git history using Conventional Commit subjects
- backfill missing released versions from local git tags
- support fragment-file workflows for teams that prefer `changelog.d` over direct changelog edits

Many features for bash scripting ergonomics.

Online integration with Git Forge Release pages

- create or update GitHub and GitLab releases
- open or update a GitHub pull request for release automation

## Examples

These are the happy-path workflows. For every alternate path and every extra flag, use [`./docs/`](docs/).

### 1. Initialize a new repo

Start with config if you want to lock in Semantic Versioning and defaults up front, then create the changelog:

```sh
changelogmanager config init
changelogmanager create
```

That gives you a clean `CHANGELOG.md` with an `[Unreleased]` section and the standard preamble.

### 2. Backfill released history from local tags

If the repo already has releases, let the tool build the missing version sections before you start editing new work:

```sh
changelogmanager backfill --source local --dry-run
changelogmanager backfill --source local
```

This is the "adopt the tool in an existing repo" path. It uses local tags and commit intervals, and falls back to an honest placeholder when old release notes are not recoverable.

### 3. Backfill `[Unreleased]` from commits since the last tag

If your release history is already fine and you only want today's work pulled into `[Unreleased]`:

```sh
changelogmanager backfill --source local --include-unreleased
```

That is the quickest "catch me up from git" workflow.

### 4. Edit or update `[Unreleased]`

Use direct changelog editing when you want polished wording instead of whatever came from commit subjects:

```sh
changelogmanager add --change-type added --message "Support draft release previews"
changelogmanager remove --list
changelogmanager edit --change-type added --index 0 --message "Support draft GitHub release previews"
```

The day-to-day model is simple: add entries as work lands, list them when you need context, and edit them before release.

### 5. Validate and update commit messages

If you want commit subjects that backfill cleanly, use Keep a Changelog-style subjects such as:

```text
Added: support release PR automation
Fixed: preserve tag ordering during backfill
```

Audit the range you already have:

```sh
changelogmanager lint-commits --strict
```

Then get a rewrite plan for unpushed commits that need cleanup:

```sh
changelogmanager rewrite-messages --plan-out rewrite-plan.tsv
```

The rewrite command is intentionally plan-only today, which is perfect for reviewing the suggested subjects before you amend or rebase.

### 6. Validate and autofix the changelog

Before you cut a release, make sure the file is structurally clean:

```sh
changelogmanager validate
changelogmanager validate --fix
```

`--fix` handles the safe cleanup work: heading normalization, version ordering, duplicate removal, and other common Keep a Changelog paper cuts.

### 7. Preview the semantic version bump and release

See what the next release would be:

```sh
changelogmanager version --reference future
```

Then promote `[Unreleased]` into a real release:

```sh
changelogmanager release --yes
```

If your version also lives in `pyproject.toml` or Python `__version__` strings, install the `jiggle` extra and do it in one step:

```sh
uv tool install "keepachangelog-manager-fork[jiggle]"
changelogmanager release --bump-versions --yes
```

### 8. Start the next round of tasks

After a release, it is usually time to collect the next set of user-facing changes that will eventually land in `[Unreleased]`:

```sh
changelogmanager tasks add added "Support release task docs"
changelogmanager tasks add fixed "Keep promoted task text out of TASKS.md"
changelogmanager tasks list
```

When tasks are complete, mark them checked and promote them into the changelog. If your team prefers fragment files instead of a shared task list, the tool also supports changelog fragments; see [`./docs/tasks.md`](docs/tasks.md).

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
- [Releasing](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/releases.md)
- [Tasks and fragments](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/tasks.md)
- [Scripting and CI integration](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/scripting.md)
- [CLI reference](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/cli.md)
- [Desktop GUI](https://github.com/matthewdeanmartin/keepachangelog-manager/docs/gui.md)
