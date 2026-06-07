# (Keep a) Changelog Manager

`keepachangelog-manager` is for teams that want one changelog workflow from day 0 through release day:

- start a `CHANGELOG.md`
- pull history into it
- keep `[Unreleased]` tidy
- validate commit subjects and changelog structure
- cut a release and, if needed, bump version strings too

The examples below assume **Keep a Changelog** plus **Semantic Versioning**. If you want the full option matrix, multi-component repos, CI wiring, GitHub/GitLab release automation, JSON output, or the other schemas, send that curiosity to [`./docs/`](docs/).

This is a fork of `keepachangelog-manager`, originally mostly written by KevinDeJong at TomTom International, but now archived.

## Install

```sh
uv tool install keepachangelog-manager-fork
```

The package name on PyPI is `keepachangelog-manager-fork`. The installed command is `changelogmanager`, with legacy alias `keepachangelog-manager`.

## GUI

```sh
changelogmanager gui
```

The GUI has screens for live `[Unreleased]` editing, initialize/backfill, release publishing, and batch component operations.

![gui](https://raw.githubusercontent.com/matthewdeanmartin/keepachangelog-manager/main/resources/gui_edit_page.png)

## What it does

`keepachangelog-manager` helps you:

- create, validate, and release `CHANGELOG.md`
- add, edit, list, and remove `[Unreleased]` entries
- backfill missing history from tags, commits, releases, or package metadata
- lint commit subjects so backfill does not turn vague messages into junk changelog lines
- publish GitHub and GitLab releases from changelog content

## Examples

These are the happy-path workflows. For every alternate path and every extra flag, use [`./docs/`](docs/).

### 1. Initialize a new repo

Start with config if you want to lock in Semantic Versioning and defaults up front, then create the changelog:

```sh
changelogmanager config init
changelogmanager create
```

That gives you a clean `CHANGELOG.md` with an `[Unreleased]` section and the standard preamble.

### 2. Backfill released history from local tags

If the repo already has releases, let the tool build the missing version sections before you start editing new work:

```sh
changelogmanager backfill --source local --dry-run
changelogmanager backfill --source local
```

This is the "adopt the tool in an existing repo" path. It uses local tags and commit intervals, and falls back to an honest placeholder when old release notes are not recoverable.

### 3. Backfill `[Unreleased]` from commits since the last tag

If your release history is already fine and you only want today's work pulled into `[Unreleased]`:

```sh
changelogmanager backfill --source local --include-unreleased
```

That is the quickest "catch me up from git" workflow.

### 4. Edit or update `[Unreleased]`

Use direct changelog editing when you want polished wording instead of whatever came from commit subjects:

```sh
changelogmanager add --change-type added --message "Support draft release previews"
changelogmanager remove --list
changelogmanager edit --change-type added --index 0 --message "Support draft GitHub release previews"
```

The day-to-day model is simple: add entries as work lands, list them when you need context, and edit them before release.

### 5. Validate and update commit messages

If you want commit subjects that backfill cleanly, use Keep a Changelog-style subjects such as:

```text
Added: support release PR automation
Fixed: preserve tag ordering during backfill
```

Audit the range you already have:

```sh
changelogmanager lint-commits --strict
```

Then get a rewrite plan for unpushed commits that need cleanup:

```sh
changelogmanager rewrite-messages --plan-out rewrite-plan.tsv
```

The rewrite command is intentionally plan-only today, which is perfect for reviewing the suggested subjects before you amend or rebase.

### 6. Validate and autofix the changelog

Before you cut a release, make sure the file is structurally clean:

```sh
changelogmanager validate
changelogmanager validate --fix
```

`--fix` handles the safe cleanup work: heading normalization, version ordering, duplicate removal, and other common Keep a Changelog paper cuts.

### 7. Preview the semantic version bump and release

See what the next release would be:

```sh
changelogmanager version --reference future
```

Then promote `[Unreleased]` into a real release:

```sh
changelogmanager release --yes
```

If your version also lives in `pyproject.toml` or Python `__version__` strings, install the `jiggle` extra and do it in one step:

```sh
uv tool install "keepachangelog-manager-fork[jiggle]"
changelogmanager release --bump-versions --yes
```

## CLI Visuals

![gif](https://raw.githubusercontent.com/matthewdeanmartin/keepachangelog-manager/main/resources/usage.gif)

## Credits

### Vendored

- [`Colin-b/keepachangelog`](https://github.com/Colin-b/keepachangelog)
- [llvm_diagnostics](https://pypi.org/project/llvm-diagnostics/)

## Documentation

- [Generic CI](docs/CI.md)
- [GitHub automation](docs/github.md)
- [GitLab automation](docs/gitlab.md)
- [Quick start](docs/quickstart.md)
- [Installation](docs/installation.md)
- [Key workflows](docs/workflows.md)
- [Scripting and CI integration](docs/scripting.md)
- [CLI reference](docs/cli.md)
- [Desktop GUI](docs/gui.md)
