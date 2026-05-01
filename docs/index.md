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

- **Validation** — catches malformed headings, bad semver, wrong date formats, and disallowed markup before they cause problems
- **Interactive and scripted `add`** — append entries to `[Unreleased]` via a prompt or a single one-liner
- **Automatic semver bumping** — infers the next version from change categories (`removed` → major, `added`/`security` → minor, everything else → patch)
- **Release workflow** — promotes `[Unreleased]` to a dated version in one command
- **GitHub integration** — creates or updates a Draft Release from your unreleased changes
- **JSON export** — dumps the full changelog as structured JSON for downstream tooling
- **Multi-component repos** — point commands at any `CHANGELOG.md` via a YAML config file

## Next steps

- [Quick start](quickstart.md) — up and running in two minutes
- [Installation](installation.md) — all installation methods
- [Key Workflows](workflows.md) — day-to-day usage patterns
- [CLI reference](cli.md) — every command and option
