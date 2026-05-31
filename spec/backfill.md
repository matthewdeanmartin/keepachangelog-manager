# Backfill design

Status: **proposed** · Owner: TBD · Last updated: 2026-05-31

## Goal

Add a `backfill` workflow that can create or enrich a Keep a Changelog
`CHANGELOG.md` from release history that already exists elsewhere: git tags,
GitHub Releases, merged pull requests, PyPI releases, and commit history.

The product goal is to make adoption easy for projects that did not maintain a
high-quality changelog from day one. A user should be able to point the tool at
an existing repository, preview the proposed changelog entries, and accept a
reviewable result without hand-copying old release notes.

## Non-goals

- Perfectly inferring user intent from every historical commit.
- Replacing `validate`, `validate --fix`, or `from-commits`.
- Publishing releases. Backfill writes changelog content; `github-release`,
  `gitlab-release`, and future publish commands remain separate.
- Building a hosted service or storing credentials.

## User stories

- As a maintainer adopting this tool, I want to generate a first
  `CHANGELOG.md` from tags and GitHub Releases.
- As a library maintainer, I want to recover historical release notes from PyPI
  package descriptions when the repository is incomplete.
- As a release manager, I want to fill missing versions in an existing
  changelog without overwriting hand-written sections.
- As a CI user, I want a dry-run report that explains what would be added.
- As a reviewer, I want entries to include enough provenance to trust where
  they came from.

## Proposed command shape

Introduce a new top-level command:

```sh
changelogmanager backfill [OPTIONS]
```

Initial options:

| Option | Default | Description |
|---|---|---|
| `--source [tags\|github-releases\|github-prs\|pypi\|commits\|all]` | `all` | Source or source set to import from |
| `--repository TEXT` | auto-detect if possible | GitHub repository in `owner/repo` format |
| `--package TEXT` | auto-detect if possible | PyPI package name |
| `--since TEXT` | oldest available | Earliest version/tag/ref to consider |
| `--until TEXT` | latest available | Latest version/tag/ref to consider |
| `--missing-only` | `true` | Only add versions missing from the changelog |
| `--include-unreleased` | `false` | Also seed `[Unreleased]` from changes since the latest release |
| `--strategy [conservative\|merge\|replace]` | `conservative` | How to handle versions already present |
| `--dry-run` | `false` | Preview without writing |

Examples:

```sh
changelogmanager backfill --source tags
changelogmanager backfill --source github-releases --repository owner/repo
changelogmanager backfill --source pypi --package keepachangelog-manager-fork
changelogmanager backfill --source all --dry-run
```

`--strategy conservative` adds only missing versions and never changes existing
sections. `--strategy merge` may add missing entries to existing versions while
preserving existing text. `--strategy replace` is reserved for explicit future
work because it is destructive enough to need extra safeguards.

## Data model

Backfill should use an internal normalized model before rendering:

```python
@dataclass
class BackfillRelease:
    version: str
    date: str | None
    tag: str | None
    title: str | None
    body: str | None
    entries: list[BackfillEntry]
    sources: list[BackfillSource]

@dataclass
class BackfillEntry:
    change_type: str
    text: str
    source: str
    url: str | None = None
    confidence: str = "medium"
```

The normalized model lets multiple source adapters cooperate without each one
knowing about Keep a Changelog serialization.

## Source precedence

When multiple sources describe the same version, prefer richer curated sources
over inferred ones:

1. Existing `CHANGELOG.md` content
2. GitHub Release notes
3. PyPI release descriptions
4. Merged pull requests
5. Conventional commits
6. Bare git tags

Existing changelog content is always authoritative unless the user explicitly
chooses a future replace strategy.

## Phase 1: Local Tag Backfill

Implement a useful local-only foundation with no network calls.

### Scope

- Add `backfill --source tags`.
- Discover tags with `git tag --sort=creatordate` or equivalent.
- Normalize tag names by stripping a leading `v` when matching versions.
- Infer release dates from tag dates when available.
- Add missing version sections with a placeholder entry under `Changed`.
- Support `--since`, `--until`, `--missing-only`, `--dry-run`, `--json`, and
  multi-component `--input-file` / `--config` / `--component`.

### Placeholder text

For tags with no richer source, use intentionally honest text:

```md
### Changed

- Release notes unavailable; backfilled from tag `v1.2.3`.
```

This is more trustworthy than inventing entries.

### Acceptance criteria

- Running against a tagged repository with no changelog creates version sections
  in descending version order.
- Running against an existing changelog adds only missing versions.
- `--dry-run` reports the versions that would be added and writes nothing.
- The generated changelog passes `validate`.

## Phase 2: GitHub Releases

Add curated remote release notes as the first high-value network source.

### Scope

- Add `backfill --source github-releases`.
- Reuse the existing GitHub API helper where practical.
- Read `GITHUB_TOKEN` when available, but allow unauthenticated requests.
- Fetch releases, including pagination.
- Map release tag, name, publication date, body, and URL.
- Parse release bodies into Keep a Changelog sections when headings match known
  change types.
- Fall back to a single `Changed` entry when release notes are unstructured.

### Notes parsing

Recognize common headings:

- `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`
- Markdown heading variants such as `## Added`, `### Fixed`
- Emoji-prefixed headings emitted by this project, if present

Do not attempt aggressive natural-language classification in this phase.

### Acceptance criteria

- GitHub Release notes produce meaningful entries instead of placeholders.
- Existing hand-written changelog sections are preserved.
- Rate-limit and authentication failures produce actionable errors.
- `--dry-run --json` includes source URLs for proposed entries.

## Phase 3: GitHub Pull Requests

Fill gaps between tags using merged pull requests.

### Scope

- Add `backfill --source github-prs`.
- For each version interval, find PRs merged between the previous tag and the
  current tag.
- Classify PRs from labels, then title prefixes, then default to `Changed`.
- Include PR numbers in generated entries by default.
- Support config-driven label mapping.

Example config:

```yaml
project:
  github:
    labels:
      "type: feature": added
      "type: bug": fixed
      "security": security
      "breaking": removed
```

### Entry shape

```md
- Add OAuth device flow support (#123).
```

When the PR title already contains a terminal period, preserve it rather than
adding another one.

### Acceptance criteria

- PRs are assigned to the correct version interval.
- Label mapping takes precedence over title parsing.
- Duplicate PR-derived entries are not added on repeated runs.
- The command works when a repository has tags but no GitHub Releases.

## Phase 4: PyPI Releases

Add package-index backfill for Python projects.

### Scope

- Add `backfill --source pypi`.
- Auto-detect the package name from `pyproject.toml` when possible.
- Query PyPI JSON metadata for release versions, upload dates, and project URLs.
- Use release descriptions if available.
- Optionally align PyPI versions with git tags and GitHub Releases when
  `--source all` is used.

### Version filtering

Respect the active versioning scheme where possible:

- `semver`: prefer SemVer-compatible versions.
- `pep440`: accept PEP 440 versions.
- `calver`: preserve strings and validate only date shape where configured.

### Acceptance criteria

- `backfill --source pypi --package NAME` can create missing sections for
  released PyPI versions.
- Yanked releases are included but marked in provenance metadata for JSON
  output.
- Pre-releases are included only when the configured versioning scheme accepts
  them or a future `--include-prereleases` flag is added.

## Phase 5: Source Fusion

Make `--source all` genuinely useful.

### Scope

- Combine tags, GitHub Releases, GitHub PRs, PyPI, and commits into one
  proposed changelog.
- Deduplicate entries by normalized text, PR number, commit SHA, and source URL.
- Prefer curated release notes over inferred PR/commit entries.
- Produce a clear conflict report when sources disagree on release dates or tag
  names.

### Conflict handling

Default behavior should be conservative:

- Keep the existing changelog date if present.
- Prefer GitHub Release publication date over tag date for missing dates.
- Report, but do not fail, when PyPI upload date differs from tag/release date.
- Fail only when versions cannot be ordered under the active versioning scheme.

### Acceptance criteria

- `backfill --source all --dry-run` gives a readable plan of additions.
- Re-running after applying the plan is idempotent.
- The output changelog validates.
- JSON output includes per-entry provenance.

## Phase 6: Review Workflow

Improve trust and editability before writing.

### Scope

- Add `--interactive` to review proposed versions and entries.
- Add `--output FILE` to write a proposed changelog somewhere other than the
  active changelog.
- Add `--report FILE` to write a machine-readable provenance report.
- Consider a future `backfill apply REPORT.json` workflow.

### Acceptance criteria

- Users can preview, accept, skip, or edit proposed entries interactively.
- CI users can generate a report artifact without mutating the repository.
- Human reviewers can see where every generated entry came from.

## Rendering rules

- Preserve the existing preamble when the changelog exists.
- Use the configured preamble when creating a new changelog.
- Render versions newest-first, with `[Unreleased]` first if present.
- Use configured change-type names and ordering.
- Do not add empty change-type sections.
- Preserve a trailing newline.

## Diagnostics and JSON output

Human output should be concise:

```text
Backfill plan for CHANGELOG.md
  add 1.3.0 from GitHub Release v1.3.0
  add 1.2.0 from 4 merged pull requests
  skip 1.1.0 already present
```

JSON output should include:

```json
{
  "added_versions": ["1.3.0", "1.2.0"],
  "skipped_versions": ["1.1.0"],
  "sources": ["github-releases", "github-prs"],
  "dry_run": true
}
```

Later phases can expand this with per-entry provenance.

## Implementation sketch

1. Add `changelogmanager/backfill.py`:
   - normalized dataclasses
   - source adapter protocol
   - merge/dedupe logic
   - rendering bridge into `Changelog`
2. Add local git helpers in the backfill module or a small
   `changelogmanager/git.py` module.
3. Extend `changelogmanager/github.py` with release/PR read helpers as needed.
4. Add CLI wiring in `cli.py`.
5. Add config readers for source preferences and label mappings.
6. Add docs in `README.md`, `docs/cli.md`, and `docs/workflows.md` after Phase
   1 lands.

## Testing plan

- Unit tests for version normalization and ordering.
- Unit tests for source precedence and deduplication.
- Local git integration tests with temporary repositories and annotated tags.
- GitHub/PyPI adapter tests with mocked HTTP responses.
- Golden-file tests for rendered changelog output.
- Idempotency tests: run backfill twice and assert no second change.
- `--dry-run` tests that prove no file writes happen.
- Multi-component tests using config-defined changelog paths.

## Open questions

- Should placeholders be enabled by default, or should tag-only backfill create
  empty version sections with warnings?
- Should PR-derived entries include links by default, or only PR numbers?
- Should `backfill` support GitLab Releases and merge requests in the first
  public version, or follow after the GitHub path proves out?
- Should PyPI pre-releases be skipped by default even for PEP 440 projects?
- Should source adapters live behind optional extras to keep dependencies small,
  or use only stdlib HTTP like the existing GitHub helper?

## Out of scope for the first implementation

- Natural-language classification of arbitrary release note paragraphs.
- Rewriting historical prose to match project voice.
- Deleting or replacing existing changelog sections.
- Publishing GitHub/GitLab/PyPI releases.
- Ticket tracker enrichment; that belongs in a later integration spec.
