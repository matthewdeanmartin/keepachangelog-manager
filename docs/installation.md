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

## Optional extras

### `jiggle` — version string synchronisation

The `jiggle` extra adds support for the `release --bump-versions` flag, which updates
`pyproject.toml` and Python source `__version__` strings to match the changelog release
version.  It is not installed by default because it pulls in
[jiggle-version](https://github.com/matthewdeanmartin/jiggle_version) and its dependencies.

```sh
# uv tool install (global CLI)
uv tool install "keepachangelog-manager-fork[jiggle]"

# uv project dependency
uv add "keepachangelog-manager-fork[jiggle]"

# pip
pip install "keepachangelog-manager-fork[jiggle]"
```

See [Syncing version strings with --bump-versions](workflows.md#syncing-version-strings-with---bump-versions)
for usage details.

### `format` - optional mdformat integration

The `format` extra adds `mdformat`, which `validate --fix` can use for an additional Markdown formatting pass after structural changelog fixes.

```sh
# uv tool install (global CLI)
uv tool install "keepachangelog-manager-fork[format]"

# uv project dependency
uv add "keepachangelog-manager-fork[format]"

# pip
pip install "keepachangelog-manager-fork[format]"
```

Without this extra, `validate --fix` still applies its built-in changelog autofixes. The formatter pass is optional.

## Package name vs command name

The PyPI package is named `keepachangelog-manager-fork`. The command you run is `changelogmanager` (or the alias `keepachangelog-manager`). Both entry points call the same code.
