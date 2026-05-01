# Desktop GUI

`keepachangelog-manager` ships with an optional Tkinter desktop GUI that surfaces every CLI command in a paneled window. It is useful for one-off edits, exploring a changelog interactively, or onboarding teammates who would rather click than memorise flags.

## Launch

```sh
changelogmanager gui
```

That's it — the same global options (`--config`, `--component`, `-f/--error-format`, `--input-file`) work, but the GUI lets you change them at any time from the **Inputs** panel at the top of the window.

You can also launch it as a module:

```sh
python -m changelogmanager gui
```

## Layout

| Pane | Contents |
|---|---|
| **Top — Inputs** | Input file (with Browse), config file, component name, error format, and a global Dry-run toggle |
| **Left — Commands** | One button per CLI subcommand; clicking jumps to the matching tab |
| **Center — Tabs** | One tab per command with its specific inputs, a Run button, and a scrollable output log; plus a **changelog** tab that shows the current file |
| **Right — Help** | Context-sensitive help for the currently selected tab |

## Auto-run on tab activation

The non-destructive commands `version` and `validate` run automatically the first time you open their tab, using the current Inputs panel values. Re-runs are manual via the **Run** button so you stay in control after editing the file.

## Destructive commands

`release`, `add`, `to-json` (without `--dry-run`), and `github-release` all modify state. The GUI honours the global **Dry run** checkbox — leave it on while you experiment, then untick it once you're satisfied with the previewed output.

`github-release` additionally requires a repository (in `owner/repo` form) and a GitHub token. The token field is masked and pre-populated from the `GITHUB_TOKEN` environment variable when present.

## When tkinter is missing

Some Python builds — notably minimal Linux containers and certain `pyenv` builds — ship without `tkinter`. In that case `changelogmanager gui` exits with code 1 and prints platform-specific install hints rather than a Python traceback. The CLI itself remains fully usable.

Typical fixes:

- **Debian / Ubuntu** — `sudo apt-get install python3-tk`
- **Fedora / RHEL** — `sudo dnf install python3-tkinter`
- **macOS (pyenv)** — reinstall Python with Tk support, e.g. `PYTHON_CONFIGURE_OPTS="--with-tcltk-includes='-I/opt/homebrew/opt/tcl-tk/include' --with-tcltk-libs='-L/opt/homebrew/opt/tcl-tk/lib -ltcl8.6 -ltk8.6'" pyenv install 3.12.x`
- **Windows** — use the python.org installer with the "tcl/tk and IDLE" option enabled
