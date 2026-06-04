# Desktop GUI

`keepachangelog-manager` ships with an optional Tkinter desktop GUI for editing changelogs, backfilling history,
publishing releases, and running batch component workflows.

## Launch

```sh
changelogmanager gui
```

That's it — the same global options (`--config`, `--component`, `-f/--error-format`, `--input-file`) work, but the GUI
lets you change them at any time from the **Workspace** panel at the top of the window.

You can also launch it as a module:

```sh
python -m changelogmanager gui
```

## Layout

The current app is organized as a menubar plus four top-level screens:

| Area | Contents |
|---|---|
| **Top — Workspace** | Changelog path, config path, component name, error format, and a global Dry run toggle |
| **Edit** | Live `[Unreleased]` editor, add/remove/reorder controls, save, validate, release, and read-only released history |
| **Initialize / Backfill** | `create`, config settings, `backfill`, and `from-commits` with source/schema/range controls and an output log |
| **Releases** | `github-release`, `github-pr`, and `gitlab-release`, plus copyable sample CI snippets |
| **Components / Batch** | Configured component listing plus `validate --all`, `validate --all --changed-only`, and `from-commits --all` |

## Scope

The GUI supports:

- direct editing of `[Unreleased]` entries, including reordering
- `create`, `validate`, and `release`
- `backfill` and `from-commits`
- `github-release`, `github-pr`, and `gitlab-release`
- batch `validate --all`, `validate --all --changed-only`, and `from-commits --all`

Use the CLI directly for export commands (`to-json`, `to-html`), `validate --fix`, `release --bump-versions`,
`skill export`, and JSON/quiet automation modes.

## Destructive commands

Outside CI, the GUI defaults **Dry run** to on. Leave it on while you experiment, then untick it once you're satisfied
with the previewed output.

`github-release` and `github-pr` require a repository (in `owner/repo` form) and a GitHub token. `gitlab-release`
requires a project ID/path and a GitLab token. Token fields are masked and pre-populated from the corresponding
environment variables when present.

## When tkinter is missing

Some Python builds — notably minimal Linux containers and certain `pyenv` builds — ship without `tkinter`. In that case `changelogmanager gui` exits with code 1 and prints platform-specific install hints rather than a Python traceback. The CLI itself remains fully usable.

Typical fixes:

- **Debian / Ubuntu** — `sudo apt-get install python3-tk`
- **Fedora / RHEL** — `sudo dnf install python3-tkinter`
- **macOS (pyenv)** — reinstall Python with Tk support, e.g. `PYTHON_CONFIGURE_OPTS="--with-tcltk-includes='-I/opt/homebrew/opt/tcl-tk/include' --with-tcltk-libs='-L/opt/homebrew/opt/tcl-tk/lib -ltcl8.6 -ltk8.6'" pyenv install 3.12.x`
- **Windows** — use the python.org installer with the "tcl/tk and IDLE" option enabled
