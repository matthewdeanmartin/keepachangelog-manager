# (Keep a) Changelog Manager

`keepachangelog-manager` is a CLI tool and Tkinter GUI for managing
`CHANGELOG.md` files that follow the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

It helps teams:

- create a changelog
- keep `[Unreleased]` tidy
- validate structure and wording
- backfill history from git, GitHub, or PyPI
- audit commit subjects before they turn into noisy release notes
- cut releases and optionally sync version strings too

This repository is a fork of the original `keepachangelog-manager`, originally
written mostly by Kevin DeJong at TomTom International.

## Install

```sh
uv tool install keepachangelog-manager-fork
```

The PyPI package is `keepachangelog-manager-fork`. The installed commands are
`changelogmanager` and the legacy alias `keepachangelog-manager`. There is also
a `kacl-gui` entry point wired to the same main module, but there is no plain
`kacl` command.

## What it does

`keepachangelog-manager` supports:

- create, validate, and release `CHANGELOG.md`
- add, edit, list, and remove `[Unreleased]` entries
- `validate --fix` for safe changelog cleanup
- `TASKS.md`, `changelog.d/`, and `tickets/` staging workflows
- semantic version calculation for `semver`, `pep440`, and `calver`
- `release --bump-versions` to sync `pyproject.toml` and Python `__version__` strings
- backfill from local tags and commits, GitHub Releases, merged GitHub PRs, and PyPI history
- `from-commits` to seed `[Unreleased]` from commit subjects
- `lint-commits` to audit commit subjects
- `rewrite-messages` to plan better subjects for unpushed commits
- GitHub and GitLab release automation
- JSON and HTML export
- stored GitHub and GitLab credentials via the OS keyring
- multi-component repository support
- optional desktop GUI

## Quick examples

Initialize a project:

```sh
changelogmanager config init
changelogmanager create
```

Add and review unreleased notes:

```sh
changelogmanager add --change-type added --message "Support release previews"
changelogmanager remove --list
changelogmanager edit --change-type added --index 0 --message "Support draft release previews"
```

Adopt the tool in an existing repo:

```sh
changelogmanager backfill --source local --dry-run
changelogmanager backfill --source local
```

Audit commit subjects:

```sh
changelogmanager lint-commits --strict
changelogmanager rewrite-messages --plan-out rewrite-plan.tsv
```

Release:

```sh
changelogmanager version --reference future
changelogmanager release --yes
```

If your version also lives outside the changelog:

```sh
uv tool install "keepachangelog-manager-fork[jiggle]"
changelogmanager release --bump-versions --yes
```

## GUI

```sh
changelogmanager gui
```

The GUI currently includes screens for:

- editing `[Unreleased]`
- tasks
- changelog fragments
- initialize/backfill
- commit lint and rewrite planning
- GitHub and GitLab release flows
- batch component operations
- version/export/credential tools

![gui](https://raw.githubusercontent.com/matthewdeanmartin/keepachangelog-manager/main/resources/gui_edit_page.png)

## Documentation

- [Quick start](docs/quickstart.md)
- [Installation](docs/installation.md)
- [Key workflows](docs/workflows.md)
- [Releasing](docs/releases.md)
- [Tasks and fragments](docs/tasks.md)
- [Scripting and CI integration](docs/scripting.md)
- [CLI reference](docs/cli.md)
- [Desktop GUI](docs/gui.md)
- [Generic CI](docs/CI.md)
- [GitHub automation](docs/github.md)
- [GitLab automation](docs/gitlab.md)
- [Contributing](docs/contributing.md)

## Credits

- [`Colin-b/keepachangelog`](https://github.com/Colin-b/keepachangelog)
- [llvm_diagnostics](https://pypi.org/project/llvm-diagnostics/)
