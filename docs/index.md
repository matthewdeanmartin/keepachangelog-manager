# keepachangelog-manager

**keepachangelog-manager** is a CLI tool and Python library for managing `CHANGELOG.md` files that follow the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## keepachangelog vs keepachangelog-manager

These are two separate things that work together:

| | [keepachangelog](https://pypi.org/project/keepachangelog/) | keepachangelog-manager |
|---|---|---|
| **What it is** | A Python library | A CLI tool built on top of that library |
| **What it does** | Parses `CHANGELOG.md` into Python dicts and back | Validates, edits, releases, and exports your changelog |
| **Who uses it** | Developers calling it from Python code | Developers and CI pipelines running shell commands |

`keepachangelog-manager` uses `keepachangelog` internally for parsing and serialisation. You do not need to import `keepachangelog` yourself — the manager wraps it.

## What keepachangelog-manager adds

On top of what the `keepachangelog` library provides, this tool gives you:

- **Validation + autofix** — catches malformed headings, bad semver, wrong date formats, empty sections, duplicate entries, and can normalise common issues with `validate --fix`
- **Interactive and scripted editing** — add, list, edit, or remove `[Unreleased]` entries from the CLI
- **Automatic semver bumping** — infers the next version from change categories (`removed` → major, `added`/`security` → minor, everything else → patch)
- **Release workflow** — promotes `[Unreleased]` to a dated version, with `release --yes` for non-interactive runs
- **Git history seeding** — build `[Unreleased]` from commit history with `from-commits`, including Conventional Commit parsing
- **Multiple export formats** — export the changelog as JSON, YAML, or HTML
- **Bundled skill export** — install the packaged `keepachangelog-manager-cli` skill into Copilot or Claude skill directories
- **GitHub integration** — creates or updates a Draft or published GitHub release from unreleased changes
- **Config bootstrap + inspection** — generate or update YAML / `pyproject.toml` config with `config init`, then inspect the active config with `config`
- **Script-friendly output** — use `--dry-run`, `--quiet`, and `--json` in automation
- **Multi-component repos** — point commands at any `CHANGELOG.md` via YAML config or `[tool.changelogmanager]` in `pyproject.toml`
- **Desktop GUI** — an optional Tkinter window for common commands, launched with `changelogmanager gui`

## Next steps

- [Quick start](quickstart.md) — up and running in two minutes
- [Installation](installation.md) — all installation methods
- [Key Workflows](workflows.md) — day-to-day usage patterns
- [CLI reference](cli.md) — every command and option
- [Desktop GUI](gui.md) — running the optional Tkinter front-end
