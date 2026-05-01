# Installation

## Requirements

- Python 3.9 or newer

## Install as a tool (recommended for CLI use)

Install with [uv](https://docs.astral.sh/uv/) so the tool is isolated from your project's dependencies:

```sh
uv tool install keepachangelog-manager-fork
```

This makes the `changelogmanager` command available globally.

## Install into a project

If you want to call the library from Python code, or pin it as a dev dependency:

```sh
# uv
uv add --dev keepachangelog-manager-fork

# pip
pip install keepachangelog-manager-fork
```

## Verify the installation

```sh
changelogmanager --help
```

You should see the top-level help text listing all available commands.

## Package name vs command name

The PyPI package is named `keepachangelog-manager-fork`. The command you run is `changelogmanager` (or the alias `keepachangelog-manager`). Both entry points call the same code.
