# Maintenance audit — 2026-09-10

The app has substantial functionality, but independent monorepo releases and Python prereleases are not yet consistent across the full workflow. Passing unit tests currently conceal several integration gaps.

Reviewed the working tree at `fa10da8`, including the pre-existing uncommitted component-release changes and tests. Those changes were preserved. This report does not implement fixes.

## Verification

- `uv run pytest -q`: 927 passed, 2 skipped; 16 snapshots passed.
- `npm test -- --reporter=dot` in `web`: 125 passed across 15 files.
- Additional isolated Python reproductions confirmed the path/validation discrepancy, file truncation on rendering failure, commented TOML header failure, incorrect SemVer ordering, PEP 440 epoch loss, and glob overmatching below. All reproduction file operations used temporary directories. No remote releases or publications were attempted.
- GUI conclusions come from source inspection and existing tests, not an interactive desktop acceptance run. Web tests exercise logic, not complete browser workflows. Live provider interoperability and package publishing remain untested.

## Capability assessment

| User workflow | Assessment |
| --- | --- |
| Initialize CHANGELOG.md | Implemented; existing-file guard and configuration initialization exist. Nested output directories and onboarding deserve acceptance coverage. |
| Backfill commits, PRs and releases | Local tags/commits, GitHub releases/PRs and PyPI adapters exist. Component tags and component-specific history boundaries are not integrated. GitLab MR/release backfill is absent from the source choices. |
| CLI and GUI editing | CLI and Tk editing exist. Tk component selection does not consistently survive command construction. The web app focuses on task/changelog fragments rather than providing the complete Python release workflow. |
| Validate | Substantial parsing, layout, strict, fix and schema support. Batch validation can validate the wrong path and return success. Version ordering is incorrect for SemVer prereleases. |
| GitHub/GitLab release pages | Both exist, but derive notes from Unreleased and a suggested version. Publishing an existing numbered section and selecting a prerelease version are missing from these commands. GitHub draft replacement is destructive. |
| Tasks using KACL categories | TASKS.md, changelog fragments, ticket fragments, promotion and assembly exist. Good foundation; three workflows, multiple interfaces and discovery rules need a clearer default and shared component context. |

## Confirmed defects and high-priority gaps

### 1. P1 — Writes can destroy the input before rendering succeeds

`changelogmanager/changelog.py:650–661` opens the destination with mode `w` before evaluating `render(...)`. A rendering/formatter exception leaves the original file empty. An injected rendering failure reproduced a zero-byte changelog. `services.release_changelog` also writes the changelog before updating companion version files, so a later decoding, write or replacement failure can leave a partially released project.

Render and validate all outputs first. Use sibling temporary files and atomic replacement for individual files, and a rollback/recovery strategy for multi-file changes. Merely checking whether version files exist does not establish that their updates will succeed.

### 2. P1 — Monorepo batch operations use a different path base

The new `cli/loaders.py:resolve_changelog_file` resolves configured paths against the config directory. `services.py:441` (component seeding) and `services.py:694` (batch validation) use raw configured paths relative to the process working directory. The GUI component picker also copies raw paths into an explicit input-file argument.

Reproduction: place a config and invalid `CHANGELOG.md` under `project/`, invoke from its parent using the absolute config path. Single-component loading rejects the invalid version. `validate_components(...)` reports `('CHANGELOG.md', 'ok')`, having inspected the missing parent-directory file instead. Seeding can similarly target the wrong file. Configured task paths also flow to discovery without a common config-directory resolver.

Resolve every component path once in a shared context. A validator should report a missing expected file rather than treat it like an empty changelog intended for creation.

### 3. P1 — GUI releases can combine one component's changelog with another's version files

`gui/screens/edit.py:release` and `gui/screens/releases.py:run_selected` pass `--config` and `--input-file`, but omit `--component`. The CLI independently resolves release ownership using the default component.

With a `default` component and a selected sibling, the GUI can release the sibling changelog while bumping default-component version files or choosing its tag namespace. Without a component literally named `default`, the command fails. This is a source-confirmed integration defect in the current working tree; the recent CLI ownership protections need GUI propagation too.

All interfaces should pass one resolved component context. Add acceptance tests selecting a non-default component and asserting that its changelog, versions and tag agree.

### 4. P1 — Component history is not isolated

`backfill.py:normalize_tag_version` removes only a leading `v`. A tag generated by the new release scope, such as `plugin-v1.2.0`, remains unchanged and is rejected as a version during backfill. Local and GitHub release backfill both use this normalization.

`cli/commands.py:command_from_commits` uses the repository-wide `services.last_release_tag()` for its default boundary. The single-component path collects all subjects without routing by touched files; `--all` routes files but uses one shared boundary. A newer plugin tag can exclude unreleased core changes, and selecting only core can import plugin messages. `release-rollback` also defaults to the repository-wide last tag.

Thread release scope through tag discovery, backfill, commit routing and rollback. Independent components need independent reachable release boundaries. Cover interleaved component releases, same-version tags, maintenance branches, and changes touching multiple components.

### 5. P1 — Python prerelease support stops short of publishing

`versioning.py` correctly uses `packaging.version.Version` for PEP 440 parsing and ordering, and explicit local release overrides provide a useful starting point. This is not an absent parser.

However:

- The default is SemVer, including this repository's configuration.
- PEP 440 auto-bumping only increments numeric release components. Reproduced: patch from `1.2.0rc1` becomes `1.2.1`; patch from `1!1.2.0` becomes `1.2.1`, dropping the epoch and producing a lower version.
- There are no explicit alpha/beta/rc/dev increment or finalization operations. A user can manually choose a local version, but remote release commands always suggest their own version.
- `github.py:create_release` does not send a `prerelease` flag. Both provider release commands derive notes from Unreleased, so releasing the changelog locally first leaves nothing for them to publish unless new entries have appeared.
- `.github/workflows/release.yml:57` subscribes to `released`. It does not handle prerelease publication. GitHub documents `published` as the event for both stable and prerelease publication, including drafts.

Treat version syntax, next-version policy, tag naming, and provider prerelease status as separate concerns. Add an explicit version/section option to provider publishing. Decide how final release notes aggregate earlier prereleases before implementing promotion.

Sources: [PyPA version specification](https://packaging.python.org/en/latest/specifications/version-specifiers/), [GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).

### 6. P1 — SemVer comparison is also broken

`versioning.py:91–98` uses custom tuple ordering rather than the semantic-version parser's precedence. Reproduced:

```text
1.2.0 < 1.2.0-rc.1       -> True
1.2.0-rc.10 < 1.2.0-rc.2 -> True
```

Both results are wrong. Build metadata also participates in this custom order. These comparisons affect release eligibility and version selection. Fixing PEP 440 alone would leave existing SemVer teams with faulty prerelease behavior.

### 7. P1 — Valid pyproject.toml can silently skip the version update

`vendor/jiggle_version/update.py:107` recognizes table headers only if nothing follows the closing bracket. A valid `[project] # comment` header prevents its version assignment being found. Reproduced: requesting `1.1.0` leaves `version="1.0.0"` unchanged without error.

Only `[project]` and `[tool.setuptools]` are considered; legacy Poetry and setup.cfg are not supported by this updater. Dynamic versions may intentionally have nothing to rewrite, but that needs explicit ownership semantics. Require a meaningful result for explicitly configured version targets, preserving intentional tag-derived versions as a separate mode.

### 8. P2 — Recursive glob matching ignores the suffix

`commit_routing.py:110–112` accepts any path below the prefix before `**`, even when the pattern has a constrained suffix. Reproduced: `api/readme.md` matches `api/**/*.py`.

This can route commits to unintended components. `fnmatch.fnmatch` also uses platform-dependent case normalization. Define repository-path glob semantics once and test root files, recursion, extension filters, case, spaces and non-ASCII names.

### 9. P1 — GitHub release refresh deletes drafts before replacement succeeds

`services.py:github_release` deletes matching draft releases and then POSTs a new one. Component patterns reduce cross-component deletion, but every matching draft in that namespace is still eligible. Hand-edited notes/assets on another pending version can be lost; a failed POST leaves no replacement. Existing published releases are not updated by this path.

Upsert the exact intended tag's release, preserving unrelated versions and assets. GitLab already uses a more useful exact-tag create/update approach. Allow an explicit target commit for GitHub too; currently its payload supplies neither a SHA nor `target_commitish`.

### 10. P1/P2 — Release automation conflates a tag with a later build commit

The repository workflow publishes a release first, then creates a version-bump commit and builds from the bump branch (`release.yml:140`). Its own comments acknowledge that building the original tag would produce the old version. Consequently the tag/source archive and uploaded distribution refer to different repository states. Building from a mutable branch also weakens reproducibility when reruns overlap.

`services.release_bump` creates its branch from current HEAD; its `base` argument is for the PR, not an enforced checkout. This assumption must be visible or validated. Prefer a release plan that prepares the version commit first, builds from its immutable SHA, and tags that same commit.

## Product friction and excessive assumptions

- **One project-wide version scheme.** `config.get_versioning_scheme` accepts no component. Python plus JavaScript/other components cannot select independent schemes within one config.
- **Explicit version_files are a good safety boundary**, but rejecting empty lists means a component with no editable version file cannot use release-bump. Model tag-derived/no-file versions intentionally rather than enabling recursive mutation.
- **The added tag/ownership model is promising but incomplete.** It protects explicitly listed companion files and provides separate default namespaces. It does not yet make every consuming command component-aware.
- **Configuration discovery searches only cwd.** Commands run from a package subdirectory can lose root settings. Prefer documented ancestor discovery bounded by a project/repository root and an inspect command explaining each resolved value.
- **Explicit CLI defaults do not always win.** `cli/config_resolve.py:apply_config_defaults` infers explicitness by comparing values to built-in defaults. Explicit `--commit-schema auto` can be replaced by config because `auto` is also the default. Track whether the argument was supplied.
- **GitHub automation still requires avoidable glue.** `release-bump` is a meaningful improvement over bespoke shell, but the example still configures author/authentication, extracts JSON into GITHUB_OUTPUT, and passes context already available in Actions. Support optional native Actions outputs and environment inference, plus a small reusable workflow. Do not hardcode this repository's publish process as every team's process.
- **Skip CI defaults to true.** This avoids loops but suppresses checks on version-changing commits/PRs. Make the default a considered product decision; use event/path/concurrency controls to prevent release loops.
- **Enterprise/provider parity is limited.** GitHub API URLs are hardcoded to api.github.com; GitLab permits a custom URL. GitLab backfill and a comparable release-MR workflow are absent. Remote inference only supports a narrow owner/repo shape.
- **Task support is real, but the preferred workflow is unclear.** TASKS.md, shipping fragments and ticket fragments solve different needs. Onboard users into one and explain progression; preserve extended/non-shipping categories as planning data. Centralize component paths and fixture-based Python/web format compatibility.
- **Documentation lags implementation.** `web/README.md` says GitHub persistence is future work, while `web/src/app/core/backend/github-backend.ts` implements scanning and branch/PR saves. Consolidate README variants and update supported-workflow documentation.

## Proposed maintenance sequence

1. Protect user files and validation results: render-before-write, recoverable multi-file updates, consistent path resolution, correct missing-file validation, checked version updates, correct version comparison and routing.
2. Complete component isolation across CLI, Tk, history/backfill, task paths and remote release operations. Preserve the useful explicit ownership model already in the working tree.
3. Complete Python prereleases: PEP 440 per-component configuration, explicit version selection, prerelease transitions/finalization policy, provider status, existing-section publication, and matching tag/build SHA.
4. Reduce CI setup with context inference, native outputs and reusable GitHub/GitLab examples. Make retries exact-tag/idempotent and preserve drafts.
5. Add user-journey coverage in isolated repositories: single Python package; independently versioned Python packages; mixed schemes; shared-file changes; execution from nested directories; prerelease-to-final; existing-section publication; failure recovery; GUI non-default component; Python/web task round trips.

The main product decisions are whether Python detection should choose PEP 440 by default, how final notes should aggregate prerelease notes, and whether GitLab parity is part of the first maintenance milestone. Correctness fixes above do not depend on those decisions.
