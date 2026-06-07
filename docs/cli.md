# CLI Reference

All commands are invoked as `changelogmanager [GLOBAL OPTIONS] COMMAND [COMMAND OPTIONS]`.

______________________________________________________________________

## Global options

These options apply to every command and must appear before the command name.

| Option | Default | Description |
|-------------------------------------|-----------------------------|--------------------------------------------------------------------------------|
| `--config TEXT` | _(auto-detect if possible)_ | Path to `changelogmanager.toml`, `.changelogmanager.toml`, or `pyproject.toml` |
| `--component TEXT` | `default` | Component name to use from the config file |
| `-f, --error-format [llvm\|github]` | `llvm` | Format for diagnostic messages |
| `--input-file TEXT` | `CHANGELOG.md` | Path to the changelog file |
| `--info` | `false` | Enable runtime info/warning/error logging on stderr |
| `--verbose` | `false` | Enable verbose runtime logging on stderr (implies `--info`) |
| `--quiet` | `false` | Suppress non-error human-readable output |
| `--json` | `false` | Emit one machine-readable JSON object on stdout |
| `--help` | | Show help and exit |

If `--config` is omitted, the CLI looks for `changelogmanager.toml`, `.changelogmanager.toml`, or
`[tool.changelogmanager]` in `pyproject.toml` in the current directory.

Runtime logging is emitted on stderr so it does not interfere with `--json` output on stdout. These logs are separate
from validation diagnostics: layout/content validation still uses the selected `llvm` or `github` error format for
CI/editor integration.

### Error formats

`llvm` (default) — compatible with many editors and terminals:

```
CHANGELOG.md:5:3: error: Incompatible change type provided, MUST be one of: Added, Changed, ...
```

`github` — GitHub Actions annotation format, renders inline on pull requests:

```
::error file=CHANGELOG.md,line=5,col=3::Incompatible change type provided ...
```

______________________________________________________________________

## create

Create a new, empty `CHANGELOG.md`.

```
changelogmanager create [--dry-run]
```

Exits with an info message (exit code 0) if the file already exists.

If config declares `project.versioning.scheme`, the generated Keep a Changelog preamble mentions that scheme (`semver`,
`pep440`, or `calver`) instead of always saying Semantic Versioning.

______________________________________________________________________

## config

Show the effective configuration and where it came from.

```
changelogmanager config
```

If a config file is active, the output reports whether it came from `--config` or auto-detection and prints the merged
config. If no config file is found, the command shows the built-in defaults.

### config init

Create or update config interactively with the same `inquirer` prompts used elsewhere in the CLI.

```
changelogmanager config init
```

The prompt flow asks where config should live (`pyproject.toml` or `changelogmanager.toml`), which versioning scheme to
mention in the preamble, whether to enforce the preamble during validation, and the default component/changelog path
when the config only tracks one component. The defaults are `pyproject.toml` and `semver`. Running it again updates
the existing config instead of only creating a new one.

______________________________________________________________________

## skill export

Export the bundled `keepachangelog-manager-cli` skill directory.

```
changelogmanager skill export [--path PATH] [--dry-run]
```

If `--path` is omitted, the command prompts for a common target such as the current project's Copilot skills directory,
the current project's Claude skills directory, or the personal Claude skills directory. The chosen directory receives a
`keepachangelog-manager-cli` folder containing `SKILL.md`.

______________________________________________________________________

## add

Add a new entry to the `[Unreleased]` section.

```
changelogmanager add [OPTIONS]
```

| Option | Description |
|----------------------------------------------------------------------------|--------------------------|
| `-t, --change-type [added\|changed\|deprecated\|removed\|fixed\|security]` | Category of the change |
| `-m, --message TEXT` | The changelog entry text |
| `--dry-run` | Preview without writing |

Omitting `--change-type` or `--message` triggers an interactive prompt.

______________________________________________________________________

## validate

Validate the changelog and exit. Writes nothing unless `--fix` is also passed.

```
changelogmanager validate [--fix] [--all] [--changed-only] [--format|--no-format] [--dry-run]
```

| Option | Description |
|------------------|----------------------------------------------------------------------------------------------------------|
| `--fix` | Apply autofixes: reorder versions, lowercase change types, drop empty sections, dedupe identical entries |
| `--all` | Validate every component declared in the config file |
| `--changed-only` | With `--all`, skip configured components whose changelog file is unchanged in git |
| `--format` | After `--fix`, require and run `mdformat` |
| `--no-format` | After `--fix`, skip the optional `mdformat` pass even when available |
| `--dry-run` | Preview `--fix` output without writing |

Exit code is `0` if the changelog is valid (or has only warnings), `1` if there are errors.

Checks performed:

- Heading depths do not exceed level 3
- Version headings match `## [x.y.z] - yyyy-mm-dd`
- `[Unreleased]` heading is recognised
- Change type headings are one of: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`
- No sub-lists, numbered lists, or block quotes inside entries
- Versions are listed in descending order
- `[Unreleased]` appears before any released version

Warnings are also emitted for empty version sections, empty change-type sections, and duplicate entries within a
section.

When `project.validation.enforce_preamble: true` is configured, the validator also requires the canonical Keep a
Changelog preamble to mention both Keep a Changelog and the configured versioning scheme.

The formatter pass is optional. If `mdformat` is installed, `validate --fix` can use it automatically; `--format`
forces it and errors if `mdformat` is unavailable, while `--no-format` disables it.

______________________________________________________________________

## version

Print a version number derived from the changelog.

```
changelogmanager version [OPTIONS]
```

| Option | Default | Description |
|-----------------------------------------------|-----------|-------------------------|
| `-r, --reference [previous\|current\|future]` | `current` | Which version to report |

| Reference | What it returns |
|------------|--------------------------------------------------------------------|
| `current` | The most recently released version |
| `previous` | The version before the current one |
| `future` | The next version, auto-calculated from `[Unreleased]` change types |

The `future` version is calculated using the configured versioning scheme
(`semver`, `pep440`, or `calver`) and these change-type bump rules:

- `removed` present -> major bump
- `added` or `security` present -> minor bump
- Otherwise -> patch/micro bump

______________________________________________________________________

## release

Promote `[Unreleased]` to a versioned, dated release.

```
changelogmanager release [OPTIONS]
```

| Option | Default | Description |
|---------------------------|----------|---------------------------------------------------------------|
| `--override-version TEXT` | _(auto)_ | Explicit version to use instead of auto-calculated |
| `-y, --yes` | `false` | Skip the interactive confirmation prompt |
| `--bump-versions` | `false` | Also update `pyproject.toml` and Python `__version__` strings |
| `--pyproject-only` | `false` | With `--bump-versions`, skip Python source files |
| `--dry-run` | | Preview without writing |

A leading `v` on `--override-version` is stripped automatically.

Non-interactive runs without `--yes` are refused. Use `release --dry-run` to preview, then `release --yes` in CI or
scripts.

Exits with code 0 and a skip notice if `[Unreleased]` exists but has no entries — useful in
CI so a "nothing to release" run does not fail the job.

Fails with exit code 1 if:

- There is no `[Unreleased]` section at all
- The provided version is not compliant with the configured versioning scheme
- The version already exists in the changelog
- The version would be older than the current latest release

`--bump-versions` requires the optional `jiggle` extra.

______________________________________________________________________

## to-json

Export the changelog to JSON.

```
changelogmanager to-json [OPTIONS]
```

| Option | Default | Description |
|--------------------|------------------|-----------------------------------------------------|
| `--file-name TEXT` | `CHANGELOG.json` | Output file path |
| `--schema-version` | _(current)_ | KAG-Manager JSON schema version to validate against |
| `--dry-run` | | Validate and print path without writing |

The output is a JSON array. Each element corresponds to one release (including `unreleased` if present) and contains a
`metadata` object plus arrays for each change type.

______________________________________________________________________

## to-html

Export the changelog to HTML.

```
changelogmanager to-html [OPTIONS]
```

| Option | Default | Description |
|--------------------|------------------|-----------------------------------------|
| `--file-name TEXT` | `CHANGELOG.html` | Output file path |
| `--dry-run` | | Validate and print path without writing |

The generated HTML is a simple standalone document that escapes changelog content before rendering it.

______________________________________________________________________

## remove

List or remove entries from `[Unreleased]`.

```
changelogmanager remove [OPTIONS]
```

| Option | Description |
|----------------------------------------------------------------------------|---------------------------------------------------------------------|
| `-t, --change-type [added\|changed\|deprecated\|removed\|fixed\|security]` | Category containing the entry to remove |
| `-i, --index INTEGER` | 0-based index within that category |
| `--list` | List all `[Unreleased]` entries with indices instead of removing |
| `--count` | Print the total number of `[Unreleased]` entries as a plain integer |
| `--dry-run` | Preview without writing |

Use `--list` first to discover the `change-type` and `index` pair you want. Use `--count` in scripts when you only need
to know whether entries exist — it prints a bare integer to stdout and sets `{"count": N}` in `--json` output.

______________________________________________________________________

## edit

Edit an existing `[Unreleased]` entry.

```
changelogmanager edit [OPTIONS]
```

| Option | Description |
|----------------------------------------------------------------------------|---------------------------------------|
| `-t, --change-type [added\|changed\|deprecated\|removed\|fixed\|security]` | Category containing the entry to edit |
| `-i, --index INTEGER` | 0-based index within that category |
| `-m, --message TEXT` | Replacement message |
| `--new-change-type [added\|changed\|deprecated\|removed\|fixed\|security]` | Move the entry into another category |
| `--dry-run` | Preview without writing |

Provide `--message` and/or `--new-change-type`, or run interactively and enter a replacement message when prompted.

______________________________________________________________________

## tasks

Manage a lightweight `TASKS.md` file that can feed `[Unreleased]`.

```
changelogmanager tasks SUBCOMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `list` | List parsed tasks |
| `add CHANGE_TYPE MESSAGE` | Add a task under a changelog heading |
| `check SELECTOR` | Mark a task done |
| `uncheck SELECTOR` | Mark a task not done |
| `validate` | Validate task structure |
| `promote` | Move checked tasks into `[Unreleased]` |

Shared task option:

| Option | Description |
|--------|-------------|
| `--tasks-file TEXT` | Explicit task file path |

`check` and `uncheck` accept either a task line number or the exact task text as the selector.

`promote` skips entries already present in `[Unreleased]` and removes promoted checked tasks unless `--keep` is passed.

If `--tasks-file` is omitted, the CLI looks for `TASKS.md`, then `.changelogmanager/TASKS.md`.

______________________________________________________________________

## fragments

Manage changelog fragment files such as `changelog.d/issue-123.fixed.md`.

```
changelogmanager fragments SUBCOMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `list` | List pending fragments |
| `add CHANGE_TYPE MESSAGE` | Create or update a fragment |
| `validate` | Validate fragment filenames and contents |
| `collect` | Move pending fragments into `[Unreleased]` |

Common fragment options:

| Option | Description |
|--------|-------------|
| `--fragment-dir TEXT` | Explicit fragment directory |
| `--slug TEXT` | Slug used for `fragments add` filenames |
| `--consume [archive\|delete\|keep]` | What `collect` does with consumed fragments |

`collect` skips entries already present in `[Unreleased]`. Its default consume mode is `archive`, which moves collected
files into an `archive/YYYY-MM-DD/` folder under the fragment directory.

`add --fragment [SLUG]` is a shortcut for writing a fragment instead of editing `[Unreleased]` directly.

If `--fragment-dir` is omitted, the CLI looks for `changelog.d`, then `changes`, then `.changelogmanager/fragments`.

______________________________________________________________________

## github-release

Create or update a GitHub release from `[Unreleased]`.

```
changelogmanager github-release [OPTIONS]
```

| Option | Default | Description |
|---------------------------|-----------------------|-----------------------------------|
| `-r, --repository TEXT` | _(required)_ | Repository in `owner/repo` format |
| `-t, --github-token TEXT` | `GITHUB_TOKEN` if set | GitHub personal access token |
| `--draft` | _(default)_ | Create/update as a Draft release |
| `--release` | | Publish the release immediately |
| `--dry-run` | | Preview without calling GitHub |

The command first deletes all existing draft releases for the repository, then creates a new one tagged with the
auto-calculated future version. The release body is generated from the `[Unreleased]` entries, grouped by change type
with emoji headers.

______________________________________________________________________

## github-pr

Open or update a GitHub pull request for a changelog branch.

```
changelogmanager github-pr [OPTIONS]
```

| Option | Default | Description |
|---------------------------|-----------------------|------------------------------------|
| `-r, --repository TEXT` | _(required)_ | Repository in `owner/repo` format |
| `--head TEXT` | _(required)_ | Source branch for the pull request |
| `--base TEXT` | _(required)_ | Target branch for the pull request |
| `--title TEXT` | _(auto)_ | Pull request title |
| `--body TEXT` | _(auto)_ | Pull request body |
| `-t, --github-token TEXT` | `GITHUB_TOKEN` if set | GitHub token |
| `--dry-run` | | Preview without calling GitHub |

If an open pull request already exists for the same `head` and `base`, the command updates its title/body instead of
opening a duplicate.

______________________________________________________________________

## backfill

Backfill missing released versions from existing history.

```
changelogmanager backfill [OPTIONS]
```

| Option | Default | Description |
|---------------------------|-------------------|-------------------------------------------------------------------------------|
| `--source` | `local` | Source set to import from (see table below) |
| `--repository TEXT` | | GitHub repository in `owner/repo` format |
| `--package TEXT` | | PyPI package name |
| `-t, --github-token TEXT` | _(keyring / env)_ | GitHub token; falls back to OS keyring then `GITHUB_TOKEN` |
| `--since TEXT` | | Earliest version/tag/ref to consider |
| `--until TEXT` | | Latest version/tag/ref to consider |
| `--missing-only` | `true` | Only add versions missing from the changelog |
| `--no-missing-only` | | With `--strategy merge`, also backfill entries into existing versions |
| `--include-unreleased` | `false` | Seed `[Unreleased]` from commits since the latest release tag |
| `--strategy` | `conservative` | How to handle versions already present |
| `--commit-schema` | `auto` | Commit schema for commit-derived entries |
| `--max-commits N` | `5000` | Refuse when the walked range exceeds N commits; pass `0` to disable the guard |
| `--dry-run` | | Preview without writing |

### `--source` choices

| Value | What it uses | Network | Requires |
|-------------------|--------------------------------------------|---------|----------------|
| `tags` | Local git tags only | no | — |
| `commits` | Local git commits grouped by tag interval | no | — |
| `local` | `tags` + `commits` (default) | no | — |
| `github-releases` | GitHub Releases API | yes | `--repository` |
| `github-prs` | GitHub merged PRs, grouped by tag date | yes | `--repository` |
| `pypi` | PyPI JSON API | yes | `--package` |
| `all` | `local` + `github-releases` + `github-prs` | yes | `--repository` |

`all` without `--repository` falls back to `local` with a warning. Users who want the old no-network behaviour should
use `--source local`.

### Strategy

- `--strategy conservative` (default) only adds versions absent from the changelog; existing sections are never touched.
- `--strategy merge --no-missing-only` additively fills entries into versions already present, preserving existing text.
  Matching is on change type plus normalised message, so re-running is idempotent.
- `--strategy replace` is intentionally unsupported.

### Online sources

**`github-releases`** fetches GitHub Releases. The release body is imported as a `changed` entry; an empty body gets a
placeholder. Requires `--repository owner/repo`. A GitHub token is strongly recommended to avoid the 60 req/hr
unauthenticated rate limit — pass `--github-token`, store one with `changelogmanager credentials set github`, or set
`GITHUB_TOKEN`.

**`github-prs`** fetches merged pull requests and groups them into versions using the local git tag timeline: each PR is
assigned to the earliest tag whose date falls on or after the PR's merge date. PRs merged after all known tags are
silently dropped (they belong to `[Unreleased]`). When no local tags exist, PRs are grouped into calendar-month
synthetic versions (`YYYY-MM`). PR labels map to KAC categories:

| Label | Category |
|--------------------------|--------------|
| `bug`, `fix` | `fixed` |
| `enhancement`, `feature` | `added` |
| `security` | `security` |
| `removed` | `removed` |
| `deprecation` | `deprecated` |
| `breaking change` | `changed` |
| _(anything else)_ | `changed` |

**`pypi`** fetches release history from the PyPI JSON API (no auth needed) and creates stub entries (
`Released on PyPI.`) for each published version. Useful for bootstrapping a changelog from a long PyPI history.

### Commit schema

`--commit-schema auto` tries Conventional Commits, gitmoji, and Keep a Changelog flavored subjects (
`Fixed: repair parser`) in sequence. Use `conventional`, `gitmoji`, or `keepachangelog` to restrict to one schema.

For tag-only imports or commit intervals with no parseable messages, the tool inserts a placeholder:

```markdown
### Changed

- Release notes unavailable; backfilled from tag `v1.2.3`.
```

______________________________________________________________________

## credentials

Manage API tokens stored in the OS keyring (Windows Credential Manager, macOS Keychain, or libsecret on Linux).

```
changelogmanager credentials set github    # prompts securely, stores in keyring
changelogmanager credentials set gitlab
changelogmanager credentials clear github
changelogmanager credentials clear gitlab
changelogmanager credentials check         # prints which tokens are configured
```

`set` prompts for the token value without echoing it to the terminal. The stored token is picked up automatically by
`backfill --source github-releases/github-prs`, `github-release`, `github-pr`, and `gitlab-release` without needing an
environment variable or `--github-token` flag.

Token resolution order for GitHub commands: `--github-token` flag → OS keyring → `GITHUB_TOKEN` environment variable.

______________________________________________________________________

## gitlab-release

Create or update a GitLab release from `[Unreleased]`.

```
changelogmanager gitlab-release [OPTIONS]
```

| Option | Default | Description |
|---------------------------|---------------------------------|---------------------------------------------------|
| `-p, --project TEXT` | _(required)_ | GitLab project ID or path such as `group/project` |
| `-t, --gitlab-token TEXT` | `GITLAB_TOKEN` / `CI_JOB_TOKEN` | GitLab token |
| `--gitlab-url TEXT` | `https://gitlab.com` | Base URL of the GitLab instance |
| `--ref TEXT` | `HEAD` | Commit or branch the created tag should point at |
| `--dry-run` | | Preview without calling GitLab |

GitLab has no draft-release state, so this command is an upsert: it updates the release if the computed tag already
exists and creates it otherwise.

Token lookup order is `--gitlab-token`, then `GITLAB_TOKEN`, then `CI_JOB_TOKEN`.

______________________________________________________________________

## from-commits

Seed `[Unreleased]` from git commit subjects.

```
changelogmanager from-commits [OPTIONS]
```

| Option | Default | Description |
|-------------------|---------------------|-----------------------------------------------------------------------|
| `--since TEXT` | _(last tag if any)_ | Git ref to start from |
| `--all-history` | `false` | Walk full history instead of starting at the last tag |
| `--all` | `false` | Route commits to every configured component by `match` globs |
| `--strict` | `false` | Skip commit subjects that do not match the selected schema |
| `--commit-schema` | `auto` | Commit schema: `auto`, `conventional`, `gitmoji`, or `keepachangelog` |
| `--dry-run` | | Preview without writing |

Commit type mapping:

| Conventional Commit type | Changelog type |
|-----------------------------------------------------------------------------|----------------|
| `feat`, `feature` | `added` |
| `fix`, `bug` | `fixed` |
| `deprecate` | `deprecated` |
| `remove` | `removed` |
| `security`, `sec` | `security` |
| `docs`, `style`, `test`, `build`, `ci`, `chore`, `refactor`, `revert`, etc. | `changed` |

Breaking-change subjects like `feat!:` are treated as `removed`.

With `--all`, the command requires a config file and uses each component's optional `match` globs to route commits by
the files they touch.

______________________________________________________________________

## gui

Launch the optional Tkinter desktop GUI.

```
changelogmanager gui
```

Global options (`--config`, `--component`, `-f/--error-format`, `--input-file`) are applied as initial values in the
window's Workspace panel and can be changed at runtime.

The GUI currently ships four screens:

- **Edit** — live `[Unreleased]` editing, save, validate, release, and read-only released history
- **Initialize / Backfill** — `create`, config settings, `backfill`, and `from-commits`
- **Releases** — `github-release`, `github-pr`, and `gitlab-release`
- **Components / Batch** — `validate --all`, `validate --all --changed-only`, and `from-commits --all`

Use the CLI directly for `to-json`, `to-html`, `validate --fix`, `release --bump-versions`, `skill export`, and other
automation-oriented flows.

If `tkinter` is not available in the current Python installation, the command exits with code 1 and prints
platform-specific install hints. See the [Desktop GUI](gui.md) page for the full layout and behaviour.
