# Releasing

This page covers the local release workflow: calculating the next version, promoting `[Unreleased]`, and optionally keeping version strings in sync outside the changelog.

For publishing to GitHub or GitLab, see [GitHub automation](github.md) and [GitLab automation](gitlab.md).

## Where your version number lives

Before using `release`, decide where your project's authoritative version number lives.

**Option A — changelog is the single source of truth.**
If your build does not read a static version string from `pyproject.toml` or source files, `changelogmanager release` is enough.

**Option B — version appears in multiple places.**
If your project also stores the version in `pyproject.toml` or Python `__version__` strings, keep those files in sync with `--bump-versions`.

## Automatic version bump

`release` inspects the change types in `[Unreleased]` and bumps the version according to the configured scheme (`semver`, `pep440`, or `calver`):

| Change type present | Bump |
|---|---|
| `removed` | Major |
| `added` or `security` | Minor |
| `changed`, `deprecated`, `fixed` only | Patch or micro |

Preview the next version:

```sh
changelogmanager version --reference future
```

Release it:

```sh
changelogmanager release --yes
```

If `[Unreleased]` exists but has no entries, the command exits successfully with a skip notice, except when explicitly finalizing a PEP 440 prerelease as described below.

## Changelog-driven PEP 440 prereleases

SemVer remains the default. Existing SemVer and CalVer version calculations and
explicit version overrides continue to work. To enable Python release phases,
add this to `pyproject.toml` (no component declaration is needed for a single project):

```toml
[tool.changelogmanager.versioning]
scheme = "pep440"
```

Declare the next release's phase in the changelog:

```markdown
## Release
- Phase: alpha
- Target: 1.4.0

## [Unreleased]
### Added
- Support Python 3.17.

## [1.3.0] - 2026-09-01
### Added
- Previous features.
```

`Target` is optional. Without it, change types choose the numeric target using
the usual bump rules. In this example, `Added` takes `1.3.0` to `1.4.0`; `alpha`
makes the next version `1.4.0a1`. An explicit target must be a final version such
as `1.4.0`; the phase supplies its suffix.

The supported phases are `dev`, `alpha`, `beta`, `rc`, and `final`. A nested
`### Release` section inside `[Unreleased]` is also accepted; formatting writes
the canonical `## Release` block before `[Unreleased]`. Only one block is allowed,
and it cannot belong to a historical release. These fields are metadata, not
change categories, and are not included in generated GitHub release notes.

Once a prerelease is recorded in the changelog, later changes keep its target
and phase unless the Release block says otherwise:

| Latest changelog version | Upcoming Phase | Suggested version |
|---|---|---|
| `1.4.0a1` | omitted or `alpha` | `1.4.0a2` |
| `1.4.0a2` | `beta` | `1.4.0b1` |
| `1.4.0b1` | `rc` | `1.4.0rc1` |
| `1.4.0rc1` | `final` | `1.4.0` |
| `1.4.0.dev1` | omitted or `dev` | `1.4.0.dev2` |

Counters start at 1 and advance from the versions already recorded in the
changelog. Repeated previews do not increment them. `release` consumes the
Release block when it creates the numbered section. Add a new block to change
phase; `Phase: final` can promote the active prerelease with no new change
entries. Final release notes do not automatically aggregate earlier prerelease
notes.

During a prerelease series, changes are checked against the last stable version
when it is available. If, for example, `Removed` requires `2.0.0` while the active
target is `1.4.0`, validation asks for an explicit larger Target. Backward phases,
non-advancing targets, malformed fields, and overrides that contradict the
Release block are rejected. Combined versions such as `1.4.0rc1.dev2` remain
available through explicit version overrides; automatic `dev` produces
`Target.devN`.

The desktop editor shows Phase and optional Target controls for PEP 440 projects.
Choose **Apply** to preview, then **Save** to persist the Release block.
**automatic** removes the block and uses the changelog history and change types.
SemVer and CalVer projects do not need or interpret this PEP 440 metadata.

When creating a GitHub release, kacl-m derives its prerelease flag from the
changelog's computed version. GitHub's Draft/Prerelease/Latest UI controls do not
select alpha, beta, or rc. Existing release flags are preserved during refresh;
the changelog remains the source of the version and phase.

## Override the version explicitly

```sh
changelogmanager release --override-version 2.0.0 --yes
```

A leading `v` is accepted and stripped automatically.

## Non-interactive releases

In scripts and CI, pass `--yes`:

```sh
changelogmanager release --yes
```

Without `--yes`, non-interactive runs are refused. Use `--dry-run` first if you want a preview.

## Syncing version strings with `--bump-versions` { #syncing-version-strings-with---bump-versions }

If your project stores the version outside the changelog, use `--bump-versions` to keep everything aligned in one step. This is built in — no extra to install.

Release and sync together:

```sh
changelogmanager release --bump-versions --yes
```

That command:

1. promotes `[Unreleased]` to the released version in `CHANGELOG.md`
1. updates `[project] version` in `pyproject.toml`
1. updates Python `__version__ = "..."` strings unless you opt out

Limit the bump to `pyproject.toml` only:

```sh
changelogmanager release --bump-versions --pyproject-only --yes
```

Preview without writing:

```sh
changelogmanager release --bump-versions --dry-run
```

JSON output includes the bumped files:

```sh
changelogmanager --json release --bump-versions --yes
```

```json
{
  "released": "1.3.0",
  "bumped_version": "1.3.0",
  "bumped_files": ["pyproject.toml", "mypackage/__about__.py"]
}
```

Typical build sequence:

```sh
changelogmanager release --bump-versions --yes
uv build
uv publish
```

## Querying versions

```sh
# most recently released version
changelogmanager version

# the version before that
changelogmanager version --reference previous

# what the next release would be
changelogmanager version --reference future
```

## Version validation and file safety

PEP 440 is opt-in using `[tool.changelogmanager.versioning] scheme = "pep440"`
in pyproject.toml. For example, `kaclm release --override-version 1.4.0rc2
--bump-versions --yes` validates the explicit version before updating files.
Alpha/beta/rc/dev remain version qualifiers, not additional change categories.
Use the Release metadata above for phase progression, or choose a version
explicitly when no Release block is present.

Version updates use TOML Kit to retain comments and table formatting. Explicit
`version_files` with no editable static version are reported as errors rather
than silently leaving package metadata behind. Changelog writes render before
replacing the destination; companion-file failures restore previous file bytes
and the in-memory changelog. Individual replacements are atomic, but this is not
a transaction that survives a power failure between multiple replacements.

Configured changelog and task paths are relative to the configuration file.
Explicit command-line paths stay relative to the working directory. Validation
of a missing changelog fails; use `create` to initialize it.
