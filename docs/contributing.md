# Contributing

## Development setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```sh
git clone https://github.com/matthewdeanmartin/keepachangelog-manager
cd keepachangelog-manager
uv sync
```

## Running the tests

```sh
uv run pytest
```

## Linting and type-checking

```sh
uv run mypy changelogmanager
uv run ruff check changelogmanager
```

## Project structure

```
changelogmanager/
  __main__.py          entry point
  cli.py               argparse setup and command handlers
  changelog.py         Changelog class — all mutation and query logic
  changelog_reader.py  ChangelogReader — parsing and validation
  change_types.py      category definitions and semver bump mapping
  config.py            YAML config file loading for multi-component repos
  github.py            GitHub API client for release management
  _llvm_diagnostics/   vendored diagnostic message formatting
```

## Diagnostics (`_llvm_diagnostics`)

Error, warning, and info messages are raised as exceptions from `changelogmanager._llvm_diagnostics`. The `main()` function catches them and calls `.report()`, which prints to stderr in the configured format. This means validation errors do not produce stack traces — they produce readable diagnostic output.

## Submitting changes

1. Open an issue to discuss larger changes before writing code.
2. Keep pull requests focused; one logical change per PR.
3. Add or update tests for any changed behaviour.
4. Run the full test and lint suite before opening a PR.
