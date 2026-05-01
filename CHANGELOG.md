# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Changed
- Project forked. Tomtom International doesn't appear to support it anymore.
- Phased out setup.py in favor of uv, pyproject.toml
- Generated changelog preambles and optional preamble validation now respect the configured versioning scheme, including PEP 440 and Calendar Versioning
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
- New 'config' and 'config init' commands for viewing and interactively creating or updating YAML or pyproject.toml configuration
- New 'skill export' command to export the bundled keepachangelog-manager-cli skill to Copilot, Claude, or a custom directory

## [4.0.0] - 2025-06-10
### Removed
- Removed support for Python >=3.7,<=3.8 in favor of minimum version 3.9

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
- The option `--override-version` accepts versions prefixed with v`

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
