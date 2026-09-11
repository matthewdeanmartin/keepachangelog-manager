# Maintenance implementation — two sprints

## Accepted direction

CHANGELOG.md drives release content and version decisions. GitHub's tag identifies
the corresponding remote release; it is not the authority for release notes.
PEP 440 remains an explicit `pyproject.toml` configuration choice. The intentional
post-publication version-bump PR remains. GitLab parity is deferred.

## Sprint 1 — correctness and file safety

- GUI local and remote release commands retain the selected component. The component picker resolves configured paths relative to the config file.
- Single and batch validation reject missing files; batch validation and component seeding use the same config-directory path base as single-component loading. Configured task-file paths use that base too.
- Explicit release versions use the configured scheme, including PEP 440. Equivalent versions cannot be released twice. SemVer comparison correctly orders numeric prerelease identifiers and ignores build metadata; PEP 440 bumps retain epochs.
- TOML Kit replaces regex-based pyproject version rewriting. Configuration updates preserve comments, initial-version settings, component version files and tag templates.
- Changelogs render before atomic replacement. Ordinary companion-update failures restore original files and in-memory changelog state. Explicit version files without editable version assignments fail clearly. This is not a power-failure-safe multi-file transaction.

## Sprint 2 — GitHub refresh and automation

- Refresh PATCHes the exact release object instead of deleting drafts. Assets, existing titles and provider metadata survive. Other versions' drafts remain untouched.
- Notes update only inside the `kaclm:release-notes` comment markers. Human text outside survives. Legacy unmarked notes are retained and a generated block is appended; one-time duplicate cleanup may be useful.
- Background draft refresh does not mutate an already published release. Explicit publication remains available.
- `github-release --version` and the GUI's version field can select a numbered changelog section or assign a new version to Unreleased notes. Versions are validated before remote mutation. New PEP 440 alpha/beta/rc/dev releases are marked prerelease; refresh preserves existing GitHub channel/latest settings.
- The repository listens for GitHub's `published` event, covering stable and prerelease publication. Its subsequent bump/build/publish sequence is preserved.
- `release-bump --github-output` emits step outputs directly. The repository workflow no longer extracts JSON with shell/Python snippets. `github-release` also accepts `GITHUB_REPOSITORY` from the environment.
- Explicit CLI values equal to defaults still override configuration. Recursive component globs respect suffixes, directory boundaries and case.
- Build verification uncovered a 116 MB source archive containing web dependencies and caches. Explicit generated-file exclusions reduce it to approximately 1.5 MB while retaining sources.

## Verification

- Full Python suite: **953 passed, 3 skipped**, including 16 snapshots.
- Regression tests cover PEP 440 release updates, GUI component/version arguments, config/comment preservation, missing/incorrect paths, rollback, release refresh failure, human notes, existing-section publication, Actions outputs and globs.
- Ruff and mypy pass. Mypy warns that the installed checker no longer supports the repository's configured Python 3.9 target; tests ran on the current Python 3.14 environment.
- Pyrefly passes. Ty's new explicit-option set inference was corrected with an explicit type annotation.
- Wheel and source distribution build successfully and pass `twine check --strict`. Archive inspection verifies new modules, TOML Kit metadata, vendored license inclusion, and cache/local-config exclusions.
- Provider behavior is verified with mocked API requests; no remote release or package was published. GUI command plumbing was exercised by tests; this is not a complete manual GUI acceptance pass.

## Remaining product decisions

1. **Prerelease intent:** keep Added/Fixed/etc. as change categories and declare alpha/beta/rc/dev at release level. Numbered headers such as `## [1.4.0rc2]` already carry this information. A declaration on Unreleased would need a chosen metadata format and persistence rules; automatic channel progression is not implemented in these sprints.
2. **GitHub checkbox:** useful to reflect or validate prerelease status, but insufficient to choose alpha versus beta versus rc, or its counter. If the changelog remains authoritative, checkbox changes should not silently rewrite its version. Existing UI choices are preserved by refresh today.
3. **Final notes:** decide whether a final release accumulates notes from preceding prereleases or contains only changes since the last prerelease.
4. **Historical components:** default to whole-repository backfill. Optional configured file globs can route commits independently of message schema. Shared-file ownership and histories predating the current layout need policy; broad component-aware historical reconstruction remains deferred.

No new change type, inferred PEP 440 default, tag-driven release policy, or GitLab parity was introduced.
