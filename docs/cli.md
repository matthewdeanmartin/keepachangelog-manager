# CLI Reference

All commands are invoked as `changelogmanager [GLOBAL OPTIONS] COMMAND [COMMAND OPTIONS]`.

______________________________________________________________________

## Global options

These options apply to every command and must appear before the command name.

| Option | Default | Description |
|-------------------------------------|-----------------------------|-------------------------------------------------------------|
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
|---------------------------|----------|----------------------------------------------------|
| `--override-version TEXT` | _(auto)_ | Explicit version to use instead of auto-calculated |
| `-y, --yes` | `false` | Skip the interactive confirmation prompt |
| `--bump-versions` | `false` | Also update `pyproject.toml` and Python `__version__` strings |
| `--pyproject-only` | `false` | With `--bump-versions`, skip Python source files |
| `--dry-run` | | Preview without writing |

A leading `v` on `--override-version` is stripped automatically.

Non-interactive runs without `--yes` are refused. Use `release --dry-run` to preview, then `release --yes` in CI or
scripts.

Fails with exit code 1 if:

- There is no `[Unreleased]` section
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
|------------------------|------------------|-------------------------------------------------|
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
|----------------------------------------------------------------------------|------------------------------------------------------------------|
| `-t, --change-type [added\|changed\|deprecated\|removed\|fixed\|security]` | Category containing the entry to remove |
| `-i, --index INTEGER` | 0-based index within that category |
| `--list` | List all `[Unreleased]` entries with indices instead of removing |
| `--dry-run` | Preview without writing |

Use `--list` first to discover the `change-type` and `index` pair you want.

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
|---------------------------|-----------------------|----------------------------------------------|
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
|-------------------------|-----------------|------------------------------------------------------------|
| `--source` | `all` | Source set to import from |
| `--repository TEXT` | | Reserved for future GitHub backfill phases |
| `--package TEXT` | | Reserved for future PyPI backfill phases |
| `--since TEXT` | | Earliest version/tag/ref to consider |
| `--until TEXT` | | Latest version/tag/ref to consider |
| `--missing-only` | `true` | Only add versions missing from the changelog |
| `--no-missing-only` | | With `--strategy merge`, also backfill entries into existing versions |
| `--include-unreleased` | `false` | Seed `[Unreleased]` from commits since the latest release tag |
| `--strategy` | `conservative` | How to handle versions already present |
| `--commit-schema` | `auto` | Commit schema for commit-derived entries |
| `--dry-run` | | Preview without writing |

Current behavior:

- `--source tags` is implemented
- `--source commits` fills tag intervals from local commit subjects
- `--source all` uses local commits when they produce entries and falls back to tag placeholders
- `--commit-schema auto` tries Conventional Commits, gitmoji, and Keep a Changelog flavored subjects such as `Fixed: repair parser`
- remote sources (`github-releases`, `github-prs`, `pypi`) are parsed but fail fast because they are not implemented yet
- `--strategy conservative` (default) only adds versions missing from the changelog and never touches existing sections
- `--strategy merge --no-missing-only` additively fills entries into versions already present, preserving existing text and metadata; matching is on change type plus normalized message, so re-running is idempotent. (With the default `--missing-only`, merge still only adds absent versions.)
- `--strategy replace` is intentionally unsupported: changelog entries have no stable identity, so replacing them is unsafe. Use `merge` to fill gaps instead.

For tag-only imports, or commit intervals with no richer local messages, the tool adds a conservative placeholder entry under `Changed`, for example:

```markdown
### Changed

- Release notes unavailable; backfilled from tag `v1.2.3`.
```

______________________________________________________________________

## gitlab-release

Create or update a GitLab release from `[Unreleased]`.

```
changelogmanager gitlab-release [OPTIONS]
```

| Option | Default | Description |
|--------------------------|-------------------------|------------------------------------------------------------|
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
|-----------------|---------------------|-------------------------------------------------------------------|
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
