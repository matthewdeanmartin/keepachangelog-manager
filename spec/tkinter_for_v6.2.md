# Tkinter GUI feature-coverage pass — v6.2

## Why

The Tkinter GUI lags the CLI. Several commands shipped in 5.x/6.x — and the two
newest features still sitting in `[Unreleased]` (TASKS.md and changelog fragments)
— have no GUI surface at all. This spec audits the gap and adds screens/controls so
a GUI user can reach every meaningful command.

## Current GUI surface (before this change)

`changelogmanager.gui.app.AppController` wires four screens plus a Config window:

| Screen                 | Covers                                                        |
| ---------------------- | ------------------------------------------------------------ |
| **Edit**               | live `[Unreleased]` add/edit/remove/reorder, prologue, save, validate, release (no bump flags) |
| **Initialize/Backfill**| `create`, `config init` (delegates to Config window), `backfill`, `from-commits` |
| **Releases**           | `github-release`, `github-pr`, `gitlab-release` + sample CI snippet |
| **Components/Batch**   | `validate --all`, `validate --all --changed-only`, `from-commits --all` |
| **Config ▸ Settings…** | interactive config editor                                    |

Top panel exposes the shared `--input-file`, `--config`, `--component`,
`--error-format`, and `--dry-run` controls.

## Gap analysis — CLI commands NOT reachable from the GUI

Ordered roughly newest-first (the recent changelog is the brief):

1. **`tasks`** (Unreleased, v6.2) — list / add / check / uncheck / validate / promote. *No GUI.*
2. **`fragments`** (Unreleased, v6.2) — list / add / validate / collect; plus `add --fragment`. *No GUI.*
3. **`lint-commits`** (message-linting, 6.x) — audit commit subjects. *No GUI.*
4. **`rewrite-messages`** (message-linting, 6.x) — plan subject rewrites. *No GUI.*
5. **`credentials`** (keyring) — check / set / clear GitHub & GitLab tokens. *No GUI.*
6. **`to-json` / `to-html`** export. *No GUI.*
7. **`version`** query (current / previous / future). *No GUI.*
8. **`skill export`**. *No GUI.*
9. **`release --bump-versions` / `--pyproject-only`** (version-bump feature) — Edit screen's
   release path calls `changelog.release(None)` directly and ignores these flags.

Scope decision for v6.2: prioritise the **two newest, fully-unsurfaced feature
areas (tasks, fragments)** plus the **message-linting pair** and a small
**Tools/Export** catch-all (version, to-json, to-html, credentials, skill export).
Wire the release bump flags into the existing Edit release dialog.

## Plan

### 1. New screen: `Tasks` (`gui/screens/tasks_screen.py`)

Drives `tasks` via `run_cli` (batch/seed style, like Backfill). Controls:

- **Tasks file** entry (`--tasks-file`, optional; blank = auto-discover).
- A **list view** populated by `tasks list` parsed output, each row showing
  `[x] change_type: text` with **Check/Uncheck** buttons (`tasks check <line>` /
  `tasks uncheck <line>` using the line-number selector).
- An **Add task** row: change-type combo (`TYPES_OF_CHANGE`) + message entry →
  `tasks add <change_type> <message>`.
- Command buttons: **Refresh** (re-run `tasks list`), **Validate** (`tasks validate`),
  **Promote** (`tasks promote`, honouring the shared dry-run; offer a **Keep**
  checkbox → `--keep`).
- Output pane for raw CLI output.
- After promote (non-dry-run) call `controller.reload()` so the Edit screen sees
  the new `[Unreleased]` entries.

### 2. New screen: `Fragments` (`gui/screens/fragments_screen.py`)

Drives `fragments`:

- **Fragment dir** entry (`--fragment-dir`, optional).
- **List view** from `fragments list` (`[change_type] path: text`).
- **Add fragment** row: change-type combo + message entry + optional slug →
  `fragments add <change_type> <message> [--slug …]`.
- Buttons: **Refresh**, **Validate** (`fragments validate`), **Collect**
  (`fragments collect` honouring dry-run; **Consume** combo: archive/delete/keep →
  `--consume`).
- Reload after a real collect.

### 3. New screen: `Commit Lint` (`gui/screens/lint_screen.py`)

Drives `lint-commits` and `rewrite-messages`:

- Shared options: **Since** entry, **Until** entry, **All history** check
  (`--all-history`), **Commit schema** combo
  (auto/conventional/gitmoji/keepachangelog).
- `lint-commits` controls: **Show** combo (fail/skip/pass/all), **Strict** check,
  **Max commits** entry. Button **Lint commits**.
- `rewrite-messages` controls: **Auto-prefix** combo (blank or a change type),
  **Plan out** file entry. Button **Plan rewrites**. (Apply is intentionally
  unimplemented in the CLI — no GUI affordance beyond a note.)
- Output pane.

### 4. New screen: `Tools / Export` (`gui/screens/tools_screen.py`)

Catch-all for the remaining commands:

- **Version**: reference combo (current/previous/future) → `version --reference …`,
  result shown in the output pane.
- **Export JSON**: file-name entry (default `CHANGELOG.json`) + schema-version combo
  → `to-json --file-name … --schema-version …`.
- **Export HTML**: file-name entry (default `CHANGELOG.html`) → `to-html --file-name …`.
- **Skill export**: destination dir entry → `skill export --path …`.
- **Credentials**: a **Check** button (`credentials check`) writing status to the
  output pane. (set/clear use `getpass`/keyring interactively at a TTY and are not
  safe to drive from a GUI text field — show a hint to use the CLI for storing a
  token, but DO surface `check` so users can see whether tokens are configured.)

### 5. Edit screen release dialog: surface bump flags

Replace the direct `changelog.release(None)` call in `EditScreen.release` with a
small dialog (or two checkboxes in the existing confirm) for:

- **Bump versions** → `release --bump-versions`
- **pyproject only** (enabled only when bump is checked) → `--pyproject-only`

Route the release through `run_cli` (`… --input-file … release --yes [--bump-versions]
[--pyproject-only] [--dry-run]`) instead of mutating the model directly, so the bump
logic (which lives in services/`jiggle-version`) actually runs. Keep the existing
"no unreleased entries" guard. Reload afterward.

### 6. Register the new screens

Add the four new screen classes to `SCREEN_CLASSES` in `gui/app.py` (order:
Edit, Tasks, Fragments, Initialize/Backfill, Commit Lint, Releases,
Components/Batch, Tools/Export). They appear automatically in the **Screens** menu.

## Non-goals

- `rewrite-messages --apply` (CLI stub; not implemented).
- `credentials set/clear` from GUI fields (keyring writes belong at a TTY).
- Reworking the Config window.

## Tests

- Smoke-construct each new screen under a headless/`Tk()` guard like existing GUI
  tests (skip if no display). Assert each screen builds and its command buttons map
  to the expected `run_cli` argv (monkeypatch `run_cli` and capture argv), mirroring
  how the Backfill/Releases screens are exercised today.
- Confirm `SCREEN_CLASSES` contains the new titles.
