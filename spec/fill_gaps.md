# Capability gaps and unimplemented paths

This note captures the biggest product gaps visible in the current CLI, the inquirer-backed interactive flows, and the
Tkinter GUI.

## Summary

The CLI surface is much broader than either the inquirer flow or the GUI. Today:

| Area | What exists | Main gap |
|----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| CLI | Full command surface, including `remove`, `edit`, `from-commits`, `backfill`, `github-pr`, `gitlab-release`, `to-yaml`, `to-html`, config, skill export, JSON/quiet/info/verbose, and advanced validate/release flags | Some branches are explicitly future-phase only rather than implemented |
| Inquirer | `config init`, `skill export` destination selection, and missing `add` arguments | Interactive UX is inconsistent; most multi-flag commands still require raw switches |
| GUI | `create`, `version`, `validate`, `release`, `to-json`, `add`, `github-release` | Large parts of the CLI are absent, and several supported commands expose only a subset of their flags |

## Inquirer coverage gaps

### What is interactive today

1. `config init` asks for config location, commit style, versioning scheme, preamble enforcement, and the default
   component/changelog path.
1. `skill export` asks for the destination when `--path` is omitted.
1. `add` prompts for missing `--change-type` and `--message`, plus a final confirmation.
1. `release` has a confirmation prompt, but it is plain `input(...)`, not inquirer.

## What is missing

The interactive story is inconsistent across commands that still expect a cluster of flags:

| Command | Current interactive support | Gap |
|---------------------------------------------------|-----------------------------|-------------------------------------------------------------------------------------------|
| `create` | None | No guided path for picking the target file or config/component |
| `validate` | None | No interactive route for `--fix`, `--all`, `--changed-only`, `--format`, or `--no-format` |
| `release` | Raw `input()` only | No inquirer flow for override version, dry-run preview, or bump-version options |
| `remove` / `edit` | None | No guided entry picker despite these commands being index-driven |
| `to-json` / `to-yaml` / `to-html` | None | No guided export target selection |
| `github-release` / `github-pr` / `gitlab-release` | None | No guided collection of repository/project/token inputs |
| `from-commits` / `backfill` | None | No guided selection of source, schema, range, or strategy |

## UX bug worth fixing first

`config init --config new-file.yml` is currently fragile: `main()` preloads config metadata for every `config` command
before dispatch, so a not-yet-created config path can fail before the init handler gets a chance to create it. That
makes the most natural non-default config-init flow unreliable.

## GUI gaps

### Commands the GUI does surface

The GUI `COMMANDS` tuple is currently:

- `create`
- `version`
- `validate`
- `release`
- `to-json`
- `add`
- `github-release`

That matches the current GUI docs.

### Entire CLI commands missing from the GUI

These commands exist in the CLI but are not surfaced in the GUI:

- `config`
- `config init`
- `skill export`
- `remove`
- `edit`
- `to-yaml`
- `to-html`
- `github-pr`
- `gitlab-release`
- `from-commits`
- `backfill`

### Flags missing even for GUI-supported commands

| Command | CLI supports | GUI exposes | Missing from GUI |
|------------------|-----------------------------------------------------------------------------------|-------------------------------------|-----------------------------------------------------|
| `validate` | `--fix`, `--all`, `--changed-only`, `--format`, `--no-format`, `--dry-run` | only shared inputs + command run | All advanced validate flows except the bare command |
| `release` | `--override-version`, `--yes`, `--bump-versions`, `--pyproject-only`, `--dry-run` | override version + dry-run | `--yes` behavior, version bumping options |
| `to-json` | `--file-name`, `--schema-version`, `--dry-run` | file name + dry-run | `--schema-version` |
| `add` | missing args can be prompted in CLI | type + message are mandatory in GUI | No guided prompt/confirm branch |
| `github-release` | repo, token, draft/release, dry-run | repo, token, draft/release, dry-run | Reasonably complete for this command |

### Global CLI features missing from the GUI

The GUI always builds argv from `--config`, `--component`, `--error-format`, `--input-file`, and optional `--dry-run`.
It does not surface:

- `--json`
- `--quiet`
- `--info`
- `--verbose`

That means the GUI cannot drive the machine-readable or logging-oriented workflows that the CLI supports.

## Explicitly unimplemented or future-phase CLI paths

The code already advertises several `backfill` branches that fail fast instead of working end-to-end:

- remote backfill sources: `github-releases`, `github-prs`, and `pypi`
- `--strategy replace`
- merge into existing versions
- `--no-missing-only`
- `--include-unreleased`

These are good candidates for a follow-on implementation plan because they already exist at the parser/help level.

## Suggested fill order

1. Fix `config init --config <new-path>` so the guided setup path works reliably.
1. Add a consistent inquirer layer for the index-heavy and token-heavy commands: `remove`, `edit`, `github-release`,
   `github-pr`, `gitlab-release`.
1. Expand the GUI to cover the missing export/editing commands first: `remove`, `edit`, `to-yaml`, `to-html`.
1. Add advanced GUI toggles for `validate --fix` and `release --bump-versions`.
1. Implement the already-advertised future-phase `backfill` branches or hide them until they are real.

## DONE

The following items from the fill order are implemented and covered by unit tests
(`tests/test_basic/test_fill_gaps.py`, plus the existing suite — 475 tests green).
GUI work (fill-order items 3 and 4's GUI toggles) was intentionally left for a later
pass; linting/mypy were also left to a separate pass.

### 1. `config init --config <new-path>` reliability — DONE

`main()` used to eagerly resolve the versioning scheme from the explicit `--config`
path for every `config` command, which raised an uncaught `FileNotFoundError` when the
path did not exist yet (the exact non-default `config init` flow). `main()` now only
resolves the scheme from a config file that actually exists on disk and otherwise falls
back to defaults, so:

- `config init --config new-file.yml` creates the file instead of crashing.
- `config --config missing.yml` (display) now exits 1 with a handled diagnostic rather
  than a traceback.

### 2. Consistent inquirer layer for index-/token-heavy commands — DONE

Added shared interactive helpers (`interactive_enabled`, `prompt_for_unreleased_entry`,
`resolve_entry_selection`, `prompt_text`, `resolve_required_value`) and wired them in:

- `remove` / `edit`: when `--change-type`/`--index` are omitted in a TTY, the user gets
  an inquirer picker listing the `[Unreleased]` entries. `edit` also prompts for the
  replacement message when neither `--message` nor `--new-change-type` is given. The
  `edit` parser arguments are no longer `required=True`, so the interactive path is
  reachable; non-interactive use still errors cleanly with the same message.
- `github-release` (`--repository`, token), `github-pr` (`--repository`, `--head`,
  `--base`, token), and `gitlab-release` (`--project`, token): these now prompt for the
  missing repository/project/branch/token values in a TTY, still honour the relevant env
  vars (`GITHUB_TOKEN`, `GITLAB_TOKEN`/`CI_JOB_TOKEN`), and fall back to a handled error
  when run non-interactively without the required inputs. Their parser arguments were
  relaxed from `required=True` to optional so the interactive flow can fill them.

### 5. Future-phase `backfill` branches — PARTIALLY DONE

- `backfill --include-unreleased` is now **implemented** for the local case: it seeds
  `[Unreleased]` from commits since the latest scheme-compatible release tag (reusing the
  existing commit-classification machinery), dedupes against existing `[Unreleased]`
  entries, and supports `--dry-run`. New helpers: `backfill.latest_release_tag` and
  `backfill.plan_unreleased_backfill`; CLI helper `backfill_unreleased`. The misleading
  "(future phase)" help text was removed.
- The remaining branches remain **explicit fast-fails** (the "hide until real" option),
  because they need infrastructure out of scope for this pass: remote sources
  (`github-releases`, `github-prs`, `pypi`), `--strategy replace`, merge into existing
  versions, and `--no-missing-only` (rewriting/merging already-present version sections).
