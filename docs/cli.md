# CLI Reference

All commands are invoked as `changelogmanager [GLOBAL OPTIONS] COMMAND [COMMAND OPTIONS]`.

---

## Global options

These options apply to every command and must appear before the command name.

| Option | Default | Description |
|---|---|---|
| `--config TEXT` | _(none)_ | Path to a YAML configuration file for multi-component repos |
| `--component TEXT` | `default` | Component name to use from the config file |
| `-f, --error-format [llvm\|github]` | `llvm` | Format for diagnostic messages |
| `--input-file TEXT` | `CHANGELOG.md` | Path to the changelog file |
| `--help` | | Show help and exit |

### Error formats

`llvm` (default) — compatible with many editors and terminals:

```
CHANGELOG.md:5:3: error: Incompatible change type provided, MUST be one of: Added, Changed, ...
```

`github` — GitHub Actions annotation format, renders inline on pull requests:

```
::error file=CHANGELOG.md,line=5,col=3::Incompatible change type provided ...
```

---

## create

Create a new, empty `CHANGELOG.md`.

```
changelogmanager create [--dry-run]
```

Exits with an info message (exit code 0) if the file already exists.

---

## add

Add a new entry to the `[Unreleased]` section.

```
changelogmanager add [OPTIONS]
```

| Option | Description |
|---|---|
| `-t, --change-type [added\|changed\|deprecated\|removed\|fixed\|security]` | Category of the change |
| `-m, --message TEXT` | The changelog entry text |
| `--dry-run` | Preview without writing |

Omitting `--change-type` or `--message` triggers an interactive prompt.

---

## validate

Validate the changelog and exit. Writes nothing.

```
changelogmanager validate [--dry-run]
```

Exit code is `0` if the changelog is valid (or has only warnings), `1` if there are errors.

Checks performed:

- Heading depths do not exceed level 3
- Version headings match `## [x.y.z] - yyyy-mm-dd`
- `[Unreleased]` heading is recognised
- Change type headings are one of: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`
- No sub-lists, numbered lists, or block quotes inside entries
- Versions are listed in descending order
- `[Unreleased]` appears before any released version

---

## version

Print a version number derived from the changelog.

```
changelogmanager version [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `-r, --reference [previous\|current\|future]` | `current` | Which version to report |

| Reference | What it returns |
|---|---|
| `current` | The most recently released version |
| `previous` | The version before the current one |
| `future` | The next version, auto-calculated from `[Unreleased]` change types |

The `future` version is calculated using these SemVer bump rules:

- `removed` present → major bump
- `added` or `security` present → minor bump
- Otherwise → patch bump

---

## release

Promote `[Unreleased]` to a versioned, dated release.

```
changelogmanager release [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--override-version TEXT` | _(auto)_ | Explicit version to use instead of auto-calculated |
| `--dry-run` | | Preview without writing |

A leading `v` on `--override-version` is stripped automatically.

Fails with exit code 1 if:

- There is no `[Unreleased]` section
- The provided version is not SemVer compliant
- The version already exists in the changelog
- The version would be older than the current latest release

---

## to-json

Export the changelog to JSON.

```
changelogmanager to-json [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--file-name TEXT` | `CHANGELOG.json` | Output file path |
| `--dry-run` | | Validate and print path without writing |

The output is a JSON array. Each element corresponds to one release (including `unreleased` if present) and contains a `metadata` object plus arrays for each change type.

---

## github-release

Create or update a GitHub release from `[Unreleased]`.

```
changelogmanager github-release [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `-r, --repository TEXT` | _(required)_ | Repository in `owner/repo` format |
| `-t, --github-token TEXT` | _(required)_ | GitHub personal access token or `GITHUB_TOKEN` |
| `--draft` | _(default)_ | Create/update as a Draft release |
| `--release` | | Publish the release immediately |
| `--dry-run` | | Preview without calling GitHub |

The command first deletes all existing draft releases for the repository, then creates a new one tagged with the auto-calculated future version. The release body is generated from the `[Unreleased]` entries, grouped by change type with emoji headers.

---

## gui

Launch the optional Tkinter desktop GUI.

```
changelogmanager gui
```

Global options (`--config`, `--component`, `-f/--error-format`, `--input-file`) are applied as initial values in the window's Inputs panel and can be changed at runtime.

If `tkinter` is not available in the current Python installation, the command exits with code 1 and prints platform-specific install hints. See the [Desktop GUI](gui.md) page for the full layout and behaviour.
