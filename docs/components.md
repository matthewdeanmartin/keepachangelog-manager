# Component Workflows

Use this guide when one repository contains several independently released
packages. For the usual single-project case, start with [Key Workflows](workflows.md)
and [Releasing](releases.md); you do not need to declare multiple components.

A component is a named part of a repository with its own changelog and releases.
Two components can release the same version at different times. They share a Git
repository, but own separate version files and Git tag namespaces. Components do
not roll up into a combined release or meta-changelog. Batch commands return
separate results for each component.

## Configuration

In `changelogmanager.toml`:

```toml
[versioning]
scheme = "semver"

[[components]]
name = "core"
changelog = "core/CHANGELOG.md"
tasks_file = "core/TASKS.md"
fragment_directory = "core/changelog.d"
match = ["core/**", "shared/**"]
version_files = ["core/pyproject.toml", "core/__about__.py"]
tag_template = "core-v{version}"

[[components]]
name = "plugin"
changelog = "plugin/CHANGELOG.md"
tasks_file = "plugin/TASKS.md"
fragment_directory = "plugin/changelog.d"
match = ["plugin/**", "shared/**"]
version_files = ["plugin/pyproject.toml", "plugin/__about__.py"]
tag_template = "plugin-v{version}"
```

In `pyproject.toml`, use `[tool.changelogmanager.versioning]` and
`[[tool.changelogmanager.components]]` instead. Configured file and fragment paths
resolve from the configuration directory. Explicit CLI paths resolve from the
current working directory. `match` globs use repository-relative paths: `*`
matches one path segment and `**` matches zero or more segments.

Component names in multi-component projects must be simple identifiers containing
letters, digits, hyphens, or underscores, starting with a letter or digit. Names
are case-sensitive. Versioning, validation, and automation defaults are shared.

Without `tag_template`, one component uses `v{version}` and multiple components
use `{component}-v{version}`. When adding a second component to an existing project,
set the original component's template explicitly if you want to keep its existing
`v{version}` history. Existing tags are never renamed.

`version_files` is an exact list of Python files and `pyproject.toml` files, not
globs. Multi-component version bumps require it. Files must remain inside the
configuration directory and cannot belong to two components. Changelogs also
cannot have two owners. Duplicate names, invalid routing settings, and overlapping
tag namespaces are rejected when the configuration is loaded.

## Inspect and validate

```sh
kaclm components list
kaclm components show core
kaclm --component plugin components show
kaclm --json components show core
kaclm --json components validate
```

These commands are read-only. `list` displays the components, changelog paths, tag
templates, and detected issues. `show` also displays resolved task and fragment
paths, routing rules, version-file selection, release branch names, and inherited
settings. JSON output includes the same information.

`components validate` exits with status 1 for missing changelogs, missing or
uneditable explicit version files (including generated version files), or ambiguous
commit routing. A missing multi-component version-file list is a warning unless
`[defaults].bump_versions = true`; changelog-only releases do not need version files.
The JSON report contains `valid`, `components`, `issues`, `warnings`,
`version_bump_ready`, and `routing_issues`. Sidecar files and
fragment directories may be absent: the corresponding add commands create them.
Use `validate --all` to check the contents of the changelogs themselves.

## Day-to-day changes

The examples below assume the configuration above and commands run from its
directory. Select a component explicitly when editing its notes. If either
changelog does not exist yet, initialize it first:

```sh
kaclm --component core create
kaclm --component plugin create
```

Add a note directly, or stage a task for later promotion:

```sh
kaclm --component core add --change-type fixed --message "Handle empty requests"
kaclm --component plugin tasks add added "Support plugin filtering"
```

After completing the task, check it before promoting it into release notes:

```sh
kaclm --component plugin tasks check "Support plugin filtering"
kaclm --component plugin tasks promote
```

`--component` selects the changelog and configured task file. An explicit
`--input-file` or `--tasks-file` overrides the corresponding destination. Tasks
without a per-component `tasks_file` inherit `[tasks].file`, then discovery; use
separate files when the components have separate task backlogs.

## Import commits and release history

```sh
kaclm --component core from-commits --dry-run
kaclm from-commits --all --dry-run
kaclm --component core backfill --source local --dry-run
kaclm --component core backfill --include-unreleased --dry-run
```

Both single-component and batch commit imports use `match`. A commit goes to every
component whose globs match any touched file. This allows changes in `shared/**`
to appear in both changelogs. A component without globs is a fallback for commits
that match no other component. Routing permits at most one fallback; with no
fallback, unmatched commits are omitted. Routing uses changed files, not the scope
text in Conventional Commit subjects.

By default, each component imports commits after its own nearest reachable release
tag. A sibling's recent release does not shorten that range. If the component has
no reachable release tag, its full history is considered. `--all-history` explicitly
selects full history; `--since REF` selects an explicit Git boundary. For batch
imports, an explicit boundary applies to every component. Batch JSON results
include each component's actual `since` value.

Historical backfill uses only tags and GitHub releases in the selected component's
namespace, stripping the template to obtain changelog versions. Local commit
entries and GitHub PR entries also use file routing. GitHub PR backfill uses that
component's local tag timeline; without component release tags it returns no
released PR history. PyPI history uses the explicitly selected `--package`.

For local historical backfill, `--since` and `--until` can be component tags or
bare versions. Unreleased backfill uses `--since` as a Git ref. Git operations for
imports and backfill run from the configuration directory, so an explicit config
works from another working directory.

## Stage and collect fragments

Component fragment selection is `--fragment-dir` > `fragment_directory` >
`[fragments].directory` > discovery in the configuration directory. This applies
to `fragments add/list/validate/collect` and `add --fragment`.

Declare separate `fragment_directory` paths for independent components. If you
inherit a shared folder, collection reads and consumes all its fragments into the
selected changelog; fragments do not carry a component identifier.

```sh
kaclm --component core fragments add added "Support filtering"
kaclm --component core fragments collect
```

## Release one component

Each command releases only the selected component. Preview the next version and
its file updates before releasing:

```sh
kaclm --component core version --reference future
kaclm --component core release --bump-versions --dry-run --yes
kaclm --component core release --bump-versions --yes
```

The Python version files in the configuration must already exist and contain
editable versions. Omit `--bump-versions` if the tool only manages your changelog.
To release the plugin, run the same commands with `--component plugin`; it can
release on a different schedule and use the same version number as core.

Publishing GitHub/GitLab releases is a separate operation; see
[GitHub automation](github.md#independent-packages-in-a-monorepo) and
[GitLab automation](gitlab.md). Publish from `[Unreleased]` before local promotion;
GitHub also accepts `--version VERSION` to publish an already released local
section. Their commands use the selected component's tag template. For rollback,
preview the selected component's release tag:

```sh
kaclm --component core release-rollback --dry-run
```

Rollback automatically selects a tag from the chosen component's namespace and
rejects an explicit sibling tag before deleting anything. Run release and rollback
commands inside the intended Git repository. Release branches and GitHub/GitLab
releases stay separate per component. Dependency constraints, lockfiles, build
ordering, and combined releases are outside this feature's scope.

## Batch validation and CI

Check configuration and release readiness, then validate each changelog:

```sh
kaclm components validate
kaclm validate --all
kaclm validate --all --changed-only
```

`--changed-only` checks changelogs changed in the Git working tree; it does not
select components based on changed package source files. Commit routing is a
separate operation:

```sh
kaclm from-commits --all --dry-run
kaclm --json from-commits --all
```

The batch result contains one entry per component, including its actual history
cutoff. It does not create an aggregate release. CI can select one component per
job, or use batch commands for validation and commit import. See
[Generic CI](CI.md) for exit codes and machine-readable output.
