# Desktop GUI

`keepachangelog-manager` ships with a Tkinter desktop GUI for editing
changelogs, staging future notes, backfilling history, checking commit-message
quality, and previewing release automation.

## Launch

Installed tool:

```sh
changelogmanager gui
```

Local checkout:

```sh
uv run changelogmanager gui
```

The same global options (`--config`, `--component`, `-f/--error-format`,
`--input-file`) still work, but the GUI also exposes them in the shared
**Workspace** panel.

## Layout

The current app has a menubar, a shared workspace panel, and eight screens:

| Area | Contents |
|---|---|
| **Top — Workspace** | Changelog path, config path, component name, error format, and a global Dry run toggle |
| **Edit** | Live `[Unreleased]` editor, save, validate, release, and read-only released history |
| **Tasks** | `TASKS.md` listing, add/check/uncheck/validate/promote controls |
| **Fragments** | `changelog.d` list/add/validate/collect workflow |
| **Initialize / Backfill** | `create`, config bootstrap, `backfill`, and `from-commits` |
| **Commit Lint** | `lint-commits` audit plus `rewrite-messages` planning for unpushed commits |
| **Releases** | `github-release`, `github-pr`, and `gitlab-release`, plus sample CI snippets |
| **Components / Batch** | configured component list plus `validate --all`, `validate --all --changed-only`, and `from-commits --all` |
| **Tools / Export** | `version`, `to-json`, `to-html`, `skill export`, and `credentials check` |

## Scope

The GUI supports:

- direct editing of `[Unreleased]`
- `create`, `validate`, and `release`
- `TASKS.md` and changelog fragment workflows
- `backfill` and `from-commits`
- `lint-commits` and `rewrite-messages` planning
- `github-release`, `github-pr`, and `gitlab-release`
- component batch operations
- JSON/HTML export, skill export, version queries, and credential status checks

Use the CLI directly for:

- `validate --fix`
- `release --bump-versions`
- `credentials set`
- `credentials clear`
- `rewrite-messages --apply` once it exists

## Local mode vs CI mode

Outside CI, the GUI defaults **Dry run** to on for destructive actions. The
Releases screen also shows copyable sample GitHub Actions and GitLab CI snippets
so you can wire real publish steps into automation instead of running them live
from your laptop.

Inside CI, the Releases screen switches to live-call mode messaging.

## Release screen notes

- `github-release` uses a repository plus GitHub token
- `github-pr` uses repository, head branch, base branch, and GitHub token
- `gitlab-release` uses a project ID/path and GitLab token
- token fields are masked in the UI
- the screen redacts tokens in the echoed command preview

The release screen also includes an optional `[skip ci]` toggle for workflows
that turn its output into a release commit.

## When tkinter is missing

If `tkinter` is missing, the problem is your Python installation, not this
project. `changelogmanager gui` exits with code `1` and prints install hints
instead of a traceback.

For a current cross-platform diagnosis and fix matrix, see
[Where is TkInter?](https://matthewdeanmartin.github.io/where_is_tkinter/).

Typical fixes:

- **Debian / Ubuntu**: `sudo apt-get install python3-tk`
- **Fedora / RHEL**: `sudo dnf install python3-tkinter`
- **macOS (pyenv)**: reinstall Python with Tk support
- **Windows**: use the python.org installer with Tcl/Tk enabled
