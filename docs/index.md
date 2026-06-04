# keepachangelog-manager

**keepachangelog-manager** is a CLI tool and Python library for managing `CHANGELOG.md` files that follow the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## vendored keepachangelog vs keepachangelog-manager

These are two separate layers that now live in this repository:

| | [keepachangelog](https://pypi.org/project/keepachangelog/) | keepachangelog-manager |
|---|---|---|
| **What it is** | A slim vendored parser/serializer subpackage | A CLI tool and higher-level library |
| **What it does** | Parses `CHANGELOG.md` into Python dicts and back | Validates, edits, releases, and exports your changelog |
| **Where it lives** | `changelogmanager/vendor/keepachangelog/` | `changelogmanager/` |

`keepachangelog-manager` vendors the tiny subset of
[`Colin-b/keepachangelog`](https://github.com/Colin-b/keepachangelog) that it
uses internally for parsing and serialisation. The vendored copy keeps only
`to_dict(...)`, `to_dict(..., show_unreleased=True)`, and `from_dict(...)`,
plus the small helpers those functions need.

## What keepachangelog-manager adds

On top of what the `keepachangelog` library provides, this tool gives you:

- **Validation + autofix** — catches malformed headings, bad semver, wrong date formats, empty sections, duplicate entries, and can normalise common issues with `validate --fix`
- **Interactive and scripted editing** — add, list, edit, or remove `[Unreleased]` entries from the CLI
- **Automatic semver bumping** — infers the next version from change categories (`removed` → major, `added`/`security` → minor, everything else → patch)
- **Release workflow** — promotes `[Unreleased]` to a dated version, with `release --yes` for non-interactive runs
- **Historical backfill** — create missing released sections from local git tags with `backfill --source tags`
- **Git history seeding** — build `[Unreleased]` from commit history with `from-commits`, including Conventional Commits, gitmoji, and Keep a Changelog-flavored subjects
- **Multiple export formats** — export the changelog as JSON or HTML
- **Bundled skill export** — install the packaged `keepachangelog-manager-cli` skill into Copilot or Claude skill directories
- **GitHub integration** — creates draft/published releases and opens or updates release pull requests
- **GitLab integration** — creates or updates GitLab releases, including self-hosted instances
- **Config bootstrap + inspection** — generate or update `changelogmanager.toml` / `pyproject.toml` config with `config init`, then inspect the active config with `config`
- **Script-friendly output** — use `--dry-run`, `--quiet`, and `--json` in automation
- **Multi-component repos** — point commands at any `CHANGELOG.md` via TOML config or `[tool.changelogmanager]` in `pyproject.toml`
- **Desktop GUI** — an optional Tkinter window for editing, backfill, releases, and batch operations, launched with `changelogmanager gui`

## Next steps

- [Generic CI](CI.md) — validation-focused quality gates that work in any CI system
- [GitHub automation](github.md) — draft releases, release PRs, and the repository's GitHub Actions release flow
- [GitLab automation](gitlab.md) — release creation plus the `CI_JOB_TOKEN` caveat
- [Quick start](quickstart.md) — up and running in two minutes
- [Installation](installation.md) — all installation methods
- [Key Workflows](workflows.md) — day-to-day usage patterns
- [CLI reference](cli.md) — every command and option
- [Desktop GUI](gui.md) — running the optional Tkinter front-end
