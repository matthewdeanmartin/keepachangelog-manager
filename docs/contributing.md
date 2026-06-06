# Contributing

## Development setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management, but contributors should normally use the
`Makefile` as the main entry point for local development tasks.

```sh
git clone https://github.com/matthewdeanmartin/keepachangelog-manager
cd keepachangelog-manager
make help
make sync
```

## Preferred local workflow

Use Make targets instead of ad-hoc raw commands whenever possible:

- `make format` / `make format-check`
- `make lint`
- `make test`
- `make validate` — validates `CHANGELOG.md` with `keepachangelog-manager`
- `make quality` — standard pre-PR checks
- `make prerelease` — prerelease checks plus docs sync and build
- `make build`

`make quality` is the usual “before I open a PR” target. `make prerelease` is the
stronger “before a release” target.

## Changelog and release workflow

This repository dogfoods `keepachangelog-manager`.

- Use `keepachangelog-manager` / `changelogmanager` to add, edit, validate, and release changelog entries
- Run `make validate` to confirm the changelog stays valid
- Prefer the tool over manual changelog surgery when changing `[Unreleased]` or preparing releases

Releases themselves are handled by GitHub Actions. The repository keeps a draft GitHub Release in sync from the
`[Unreleased]` section, and publishing that release triggers the release workflow that bumps versions, opens the release
PR, builds artifacts, and publishes to PyPI. See [GitHub automation](github.md).

## Before submitting changes

1. Sync your environment with `make sync`.
1. Update `CHANGELOG.md` with `keepachangelog-manager` when the change is user-facing.
1. Run `make quality` before opening a PR.
1. Run `make prerelease` before cutting or validating a release.

## Project structure

```
changelogmanager/
  __main__.py          entry point
  cli/
    entry.py           CLI bootstrap
    parser.py          argparse parser construction
    commands.py        command handlers
  changelog.py         Changelog class — mutation and query logic
  changelog_reader.py  ChangelogReader — parsing, validation, and autofix
  change_types.py      category definitions and version bump mapping
  config.py            TOML config loading and serialization
  gui/                 Tkinter desktop app
  github.py            GitHub API client for release management
  gitlab.py            GitLab API client for release management
  llvm_diagnostics/    vendored diagnostic message formatting
```

## Diagnostics (`llvm_diagnostics`)

Error, warning, and info messages are raised as exceptions from `changelogmanager.llvm_diagnostics`. The `main()` function catches them and calls `.report()`, which prints to stderr in the configured format. This means validation errors do not produce stack traces — they produce readable diagnostic output.

## Submitting changes

1. Open an issue to discuss larger changes before writing code.
1. Keep pull requests focused; one logical change per PR.
1. Add or update tests for any changed behaviour.
1. Run `make quality` before opening a PR, and `make prerelease` before validating a release.
