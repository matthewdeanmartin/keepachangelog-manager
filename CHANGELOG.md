# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [6.4.0] - 2026-06-26
### Added
- GUI Workspace: Component field is now a dropdown of configured components with a 'New…' button to add a component to the config file
- CLI autodetects GitHub Actions and defaults --error-format to github (inline annotations); explicit -f and config still take precedence
- GUI Components/Batch screen: 'Add component' button and clickable component rows that set the active workspace component (component drives the changelog)
- Per-component task files: components can declare a 'tasks_file' key; tasks commands resolve it via --tasks-file > component tasks_file > [tasks].file > discovery, selected with --component. GUI New… dialog prompts for it and selecting a component repoints the Tasks-file picker

### Changed
- kacl-gui console script now launches the GUI directly instead of requiring the 'gui' subcommand
- GUI Tasks screen: the tasks file is now a prefilled primary Tasks-file picker in the Workspace panel (mirrors the Changelog picker) instead of a 'blank = auto' box with a hint label
- Version bumping (release --bump-versions) is now built in: a minimal subset of jiggle-version is vendored (changelogmanager/vendor/jiggle_version, stdlib-only — no pathspec/tomlkit). The optional [jiggle] extra and jiggle-version dependency are removed

## [6.3.0] - 2026-06-15
### Fixed
- Soft-wrapped (multi-line) changelog entries are no longer split into separate bullets when parsed; continuation lines are now folded back into their entry, so rendered output (e.g. GitHub release bodies) keeps each entry as a single bullet

### Added
- Tkinter GUI: new Tasks, Fragments, Commit Lint, and Tools/Export screens surface the tasks, fragments, lint-commits, rewrite-messages, version, to-json, to-html, skill export, and credentials check commands; the Edit screen's Release dialog now offers --bump-versions and --pyproject-only

## [6.2.0] - 2026-06-07
### Added
- Support TASKS.md files for lightweight changelog tasks and promotion into `[Unreleased]`
- Support changelog fragments with collection and opt-in add --fragment writing

## [6.1.1] - 2026-06-06
### Fixed
- Readme improvements

## [6.1.0] - 2026-06-05
### Changed
- backfill: gather commits in a single git log pass instead of one subprocess per tag (~15x faster on tag-heavy repos)

### Added
- backfill --max-commits guard refuses runaway histories and caps per-release entries to keep the changelog usable
- All mutations run validation and warn on invalid initial and final states

## [6.0.0] - 2026-06-04
### Added
- Support for pep440 and calver
- Implemented backfill
- Interactive (inquirer) prompts for remove, edit, github-release, github-pr, and gitlab-release when required arguments
- are omitted in a TTY
- backfill --include-unreleased seeds [Unreleased] from commits since the latest release tag
- from-commits --all routes commits to components by the files they touch, using per-component match globs
- Configuration in [tool.changelogmanager] (pyproject.toml) or a standalone
- changelogmanager.toml; [defaults]/[github]/[gitlab] tables back CLI flag defaults (flag > env > config > built-in
- default)

### Changed
- Configuration is now TOML-only; YAML config files are no longer read or written
- config command now displays the effective configuration as TOML
- Backfill `--strategy replace` is now an explicit unsupported error: changelog entries have no stable identity, so
- replacing them is unsafe
- Backfill `--strategy merge` additively fills entries into existing versions while preserving existing text (idempotent
- on re-runs)
- Lazy imports cut CLI startup time by ~45%

### Removed
- to-yaml export command (use to-json or to-html)
- pyyaml runtime dependency
- Unused commits.style configuration key and the never-implemented component-is-substring option

### Fixed
- config init --config <new-path> no longer crashes when the target config file does not exist yet
- Schema validation no longer rejects metadata url fields added by the keepachangelog vendor parser
- Schema validation no longer requires release_date in metadata (vendor parser omits it for unreleased-only-URL entries)
- Validation no longer warns about empty [Unreleased] sections — having no pending changes after a release is valid

## [5.2.0] - 2026-05-30
### Added
- `github-pr` command to open or update a GitHub pull request for a changelog branch, using only stdlib `urllib` (no
- third-party action dependency).
- Optional `mdformat` formatting pass in `validate --fix`: discovers `mdformat` via in-process import or
- `shutil.which`, runs after structural fixes, and is controlled by `--format` / `--no-format` flags and the
- `project.validation.format` config key (`auto` / `true` / `false`). Requires the new `[format]` optional extra
- (`pip install 'keepachangelog-manager-fork[format]'`).
- `Changelog.render(formatter, format_options)` method returns the serialized Markdown string with an optional format
- pass, keeping `write_to_file` composable without coupling discovery logic to the `Changelog` class.
- `project.validation.mdformat_options` config key passes through `wrap` and `number` options to mdformat.

### Changed
- `github-release` now skips cleanly (warning, exit 0) when there are no `[Unreleased]` entries, instead of a confusing
- silent success.
- `release.yml` workflow no longer uses `peter-evans/create-pull-request`; the changelog PR is now created via the
- vendored `github-pr` command with inline git push, satisfying zizmor's `template-injection` and `artipacked` rules.
- `release.yml` now updates an existing generated release bump branch with `--force-with-lease`, so rerunning a release
- after a partial bump failure can continue.

### Fixed
- GitHub API failures now report HTTP status and response body details, making workflow permission errors diagnosable.

## [5.1.0] - 2026-05-30
### Added
- `gitlab-release` command to create or update a GitLab release from `[Unreleased]`.
- `github-pr` command to open or update a GitHub pull request for a changelog branch, using only stdlib `urllib` (no
- third-party action dependency).

### Changed
- Better validation messages.
- `github-release` now skips cleanly (warning, exit 0) when there are no `[Unreleased]` entries, instead of a confusing
- silent success.
- `release.yml` workflow no longer uses `peter-evans/create-pull-request`; the changelog PR is now created via the
- vendored `github-pr` command with inline git push, satisfying zizmor's `template-injection` and `artipacked` rules.

## [5.0.0] - 2026-05-01
### Removed
- Old name. It is now keepachangelog-manager-fork

### Changed
- Project forked. Tomtom International doesn't appear to support it anymore.
- Phased out setup.py in favor of uv, pyproject.toml
- Generated changelog preambles and optional preamble validation now respect the configured versioning scheme, including
- PEP 440 and Calendar Versioning
- pyproject.toml config loading and auto-detection now work on Python 3.9+ via the tomli fallback
- Bundled skill assets now ship in the package for export from installed builds

### Fixed
- Validator now detects indented sub-list items (e.g. `  - nested`) as errors; previously lines with leading whitespace
- were silently skipped by `__validate_entry`
- Validator no longer cascades two errors for a single invalid version heading; after reporting an incompatible SemVer
- version the generator now returns early, preventing a spurious "Missing metadata" error on the same line

### Added
- New 'edit' command to modify or recategorise existing [Unreleased] entries
- New 'remove' command (with '--list') to drop entries from [Unreleased] by index
- New 'from-commits' command that seeds [Unreleased] from git history, parsing Conventional Commits
- New 'to-yaml' and 'to-html' export commands (PyYAML + stdlib html.escape, no new dependencies)
- 'release --yes' (alias '-y') confirmation guard; non-interactive runs without --yes are refused
- 'validate --fix' applies autofixes: reorders versions descending, lowercases change types, drops empty sections,
- dedupes entries
- 'validate --all' iterates over every component declared in the config file
- 'validate --changed-only' (with --all) skips components whose changelog is not modified per git status
- Global '--quiet' flag suppresses human-friendly output for scripting use
- Global '--json' flag emits a single machine-readable JSON object on stdout
- 'github-release' now falls back to the GITHUB_TOKEN environment variable when --github-token is omitted
- Auto-detect '.changelogmanager.yml/.yaml' in the current directory; on Python 3.11+ also
- honour [tool.changelogmanager] in pyproject.toml
- Validator now warns on empty version sections, empty change-type sections, and duplicate entries within a section
- Optional canonical-preamble check, enabled via 'project.validation.enforce_preamble: true' in the config file
- `--dry-run` option to support migration away from Click
- New 'config' and 'config init' commands for viewing and interactively creating or updating YAML or pyproject.toml
- configuration
- New 'skill export' command to export the bundled keepachangelog-manager-cli skill to Copilot, Claude, or a custom
- directory

## [4.0.0] - 2025-06-10
### Removed
- Removed support for Python >=3.7,\<=3.8 in favor of minimum version 3.9

### Changed
- Use `inquirer` instead of decomissioned `inquirer2`

## [3.3.1] - 2022-09-14
### Fixed
- Report an error when using the `release` command without the `[Unreleased]` section being present

### Changed
- The `to-json` output is now prettified

## [3.3.0] - 2022-09-12
### Added
- New option `--input-file` for managing CHANGELOG files in a different location

## [3.2.2] - 2022-08-18
### Changed
- The `CHANGELOG.json` file will now consist of an array of releases instead of having each release as dict-key

## [3.2.1] - 2022-08-18
### Fixed
- The `release` command is working correct again

## [3.2.0] - 2022-08-18
### Added
- The command `to-json` allows you to export the changelog contents in JSON format (useful for external automation
- purposes)

## [3.1.0] - 2022-07-20
### Added
- References to the Homepage and Issue Tracker in the package metadata

## [3.0.0] - 2022-05-18
### Removed
- Removed the `--apply` and `--no-apply` flags from the `add`, `release` and `github-release` command.

### Changed
- Improved user interaction for the `add` command

### Added
- The `github-release` command now supports the `--draft/--release` flags to indicate the GitHub release status

## [2.0.0] - 2022-05-18
### Fixed
- Releasing a Changelog containing no previously released version will now result in version `0.0.1` to be released

### Removed
- Removed the `keepachangelog-draft-release`, `keepachangelog-release` and `keepachangelog-validate` actions as these
- have only been intended for internal use.

## [1.0.3] - 2022-05-17
### Fixed
- The option `--override-version` accepts versions prefixed with v\`

## [1.0.2] - 2022-05-17
### Changed
- GitHub Releases and associated tags are now both prefixed with `v` (i.e. `v1.0.0` iso `1.0.0`)

## [1.0.1] - 2022-05-04
### Changed
- Updated README.md to be compatible with PyPi

## [1.0.0] - 2022-05-04
### Added
- Add support Python for older versions (`>=3.7`)
- Command Line Interface allowing users to add and release changes
- Users can now create an empty `CHANGELOG.md` using the `create` command
- Support for GitHub style error messages
- Added `validate` command to verify CHANGELOG.md consistency
- Support for creating (Draft) releases on GitHub using the `github-release` command
- Workflow to update the draft release notes when new changes are pushed to \`main\`
- <!-- mdformat -->
