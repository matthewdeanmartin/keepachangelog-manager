> ## ⚠️ Reality-check addendum (2026-06-26)
>
> The body below was a first-pass draft written **without access to this repo's
> actual fragment specs**. It invented a `.katl/` directory with **YAML front
> matter**. That format is **not** what this project uses and is **not** what the
> `web/` app implements. Treat the rest of this file as background/aspiration only;
> the sections that are now authoritative live elsewhere:
>
> - **Task fragments** are `tickets/*.md` with a **rigid markdown head**
>   (`- **Key:** value` bullets, H1 `# <id> — <title>`, body split on the first
>   column-0 `---` outside a code fence) + a free body — see
>   [`spec/TASK_FRAGMENTS_AND_UI.md`](TASK_FRAGMENTS_AND_UI.md). **No YAML front matter.**
> - **Changelog fragments** are `changelog.d/<slug>.<type>.md` — see
>   [`spec/fragments.md`](fragments.md).
> - **Categories** come from `changelogmanager/change_types.py`: six *shipping*
>   KAC types + five *non-shipping* (`internal`, `chore`, `docs`, `test`, `spike`).
>
> **What was actually built** (`web/`, Angular 19, browser-only, local-first):
> a Jira-like **Board** (tickets by status), a **Ticket** editor (rigid-head form +
> free-body markdown + live rendered-file preview + lint), a **Changelog**
> fragment manager, and a **Release preview** of the `[Unreleased]` section that
> `fragments collect` would produce (excluding non-shipping categories) with a
> consistency report. Parser/writer round-trip with the Python CLI and are unit
> tested. The GitHub PAT/Octokit PR layer described below is the next layer; the
> first build uses bundled fixtures + `localStorage` so non-developers need no
> GitHub setup. The end-to-end flow: **PMs/BAs write tickets → merge to `develop`
> every ~3 weeks → devs turn tickets into changelog fragments → release assembles
> `CHANGELOG.md`.** See [`web/README.md`](../web/README.md).

---

Below is a first-pass product/implementation spec for **KATL**. I’m assuming **KATL = Keep A Task Log** and that the
free version is a **static Angular app on GitHub Pages**.

I found the upstream `tomtom-international/keepachangelog-manager` docs, but not your specific fork’s task-fragment docs
in search. So I’m grounding the changelog pieces in the public manager behavior and Keep a Changelog conventions, then
defining a compatible task-fragment layer on top. The upstream tool supports validating, adding entries, releasing
`[Unreleased]`, JSON export, GitHub draft releases, and multiple `CHANGELOG.md` files via config. ([GitHub][1]) Keep a
Changelog’s standard change categories are `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, and `Security`; it also
recommends an `[Unreleased]` section for upcoming changes. ([Keep a Changelog][2])

# KATL — Keep A Task Log

## 1. Product summary

**KATL** is a repo-native task and changelog fragment manager.

The free version is a browser-only Angular application hosted on GitHub Pages. It authenticates to GitHub using a
user-supplied token or browser OAuth flow, lets the user select a repository, scans a predetermined folder for Markdown
task/changelog fragments, provides a structured UI for editing those fragments, and commits changes back to GitHub
through a branch and pull request.

The paid version, later, is a GitHub App with backend automation, webhooks, scheduled scans, status reports, and
release/changelog intelligence.

## 2. Goals

KATL should let a developer manage lightweight task and changelog fragments without leaving GitHub.

Primary goals:

```text
- Make Markdown task fragments editable through a friendly UI.
- Keep task state in the repository, not in a proprietary database.
- Create clean branches, commits, and pull requests.
- Support changelog categories compatible with Keep a Changelog.
- Work as a static GitHub Pages app for the free version.
- Avoid SaaS infrastructure in Phase 1.
```

Non-goals for the free version:

```text
- No backend.
- No app-wide secret.
- No background jobs.
- No webhook processing.
- No centralized database.
- No cross-repo dashboard.
- No billing.
- No team permission model beyond GitHub token permissions.
```

## 3. Core concept

A repository contains a folder of fragments, for example:

```text
.katl/
  tasks/
    KATL-0001.md
    KATL-0002.md
  changelog/
    KATL-0001.added.md
    KATL-0002.fixed.md
  config.yml
```

Or, if aligning more directly with changelog fragment tools:

```text
.keepachangelog.d/
  KATL-0001.added.md
  KATL-0002.fixed.md
  KATL-0003.task.md
```

KATL reads these files, parses front matter and Markdown body, displays them as cards/table rows, lets users edit them,
and writes the updated files back through GitHub.

## 4. Suggested file format

### 4.1 Task fragment

```markdown
---
id: KATL-0001
title: Add OAuth mock server demo
status: todo
type: task
priority: normal
assignee: matthewdeanmartin
created: 2026-06-26
updated: 2026-06-26
changelog_type: added
release: unreleased
labels:
  - oauth
  - testing
links:
  issues: []
  prs: []
---

## Summary

Add a minimal OAuth mock server demo for unattended tests.

## Acceptance Criteria

- [ ] Angular demo app can authenticate against mock server.
- [ ] Spring Boot demo app validates mock token.
- [ ] Gatling script runs without human SSO interaction.

## Notes

Keep it minimal. This is a PoC.
```

### 4.2 Changelog fragment

```markdown
---
id: KATL-0001
type: changelog
changelog_type: added
release: unreleased
task: KATL-0001
---

Added an OAuth mock server demo for unattended authentication tests.
```

### 4.3 Combined task + changelog fragment

For the first version, this may be simpler:

```markdown
---
id: KATL-0001
title: Add OAuth mock server demo
status: todo
type: task
changelog_type: added
release: unreleased
---

## Task

Add a minimal OAuth mock server demo for unattended tests.

## Changelog

Added an OAuth mock server demo for unattended authentication tests.

## Acceptance Criteria

- [ ] Angular demo app can authenticate against mock server.
- [ ] Spring Boot demo app validates mock token.
- [ ] Gatling script runs without human SSO interaction.
```

Recommendation: **start with combined fragments**. Separate task/changelog fragments can come later.

## 5. Status model

Initial statuses:

```text
todo
doing
blocked
done
wontdo
```

Optional later statuses:

```text
backlog
ready
review
released
archived
```

Rules:

```text
- New fragments default to todo.
- Done fragments may still be unreleased.
- Released fragments are read-only by default unless user enables historical editing.
- Blocked fragments should include a blocker note.
```

## 6. Changelog model

KATL should use Keep a Changelog-compatible categories:

```text
added
changed
deprecated
removed
fixed
security
```

These map to rendered headings:

```text
added      -> Added
changed    -> Changed
deprecated -> Deprecated
removed    -> Removed
fixed      -> Fixed
security   -> Security
```

This aligns with Keep a Changelog’s documented categories. ([Keep a Changelog][2])

KATL should treat `release: unreleased` as the default. Keep a Changelog explicitly recommends an `Unreleased` section
for upcoming changes, which can later be moved into a release section. ([Keep a Changelog][2])

## 7. Phase plan

# Phase 0 — Repository conventions and parser spike

## Purpose

Define the fragment format and prove KATL can parse real files.

## Features

```text
- Define .katl/config.yml.
- Define task fragment Markdown schema.
- Define changelog category mapping.
- Parse YAML front matter.
- Parse Markdown body sections.
- Validate required fields.
- Render parsed fragments as JSON in dev console.
```

## Config file

```yaml
version: 1

project:
  name: Example Project

github:
  default_base_branch: main

katl:
  fragment_globs:
    - ".katl/*.md"
    - ".katl/tasks/*.md"
    - ".keepachangelog.d/*.md"

  id_prefix: KATL
  default_status: todo
  default_release: unreleased

changelog:
  file: CHANGELOG.md
  categories:
    - added
    - changed
    - deprecated
    - removed
    - fixed
    - security
```

## Acceptance criteria

```text
- Given a checked-in sample folder, parser returns structured objects.
- Invalid fragments produce human-readable validation errors.
- Keep a Changelog categories are recognized.
- Unknown fields are preserved when writing files back.
```

# Phase 1 — Static Angular app shell on GitHub Pages

## Purpose

Create the free browser-only app.

## Features

```text
- Angular app deployable to GitHub Pages.
- Landing page explaining browser-only security model.
- Token entry screen.
- Store token only in memory by default.
- Optional "remember token" mode using localStorage, with warning.
- Repository picker.
- Basic settings screen.
```

## Authentication

Phase 1 should support **fine-grained PAT paste-in**.

Required GitHub token permissions:

```text
- Repository metadata: read
- Repository contents: read/write
- Pull requests: read/write
```

Security posture:

```text
- Default: token kept in memory only.
- Optional: persist token in localStorage.
- User can clear token.
- App must not send token anywhere except GitHub API.
- No analytics in Phase 1.
```

## Acceptance criteria

```text
- App works when hosted from GitHub Pages.
- User can paste token and verify identity.
- User can list accessible repositories.
- User can select owner/repo/base branch.
- App can persist non-secret preferences.
```

# Phase 2 — Read-only repo scanner

## Purpose

Scan a selected repo and show task fragments.

## Features

```text
- Read .katl/config.yml if present.
- Fall back to default globs if config missing.
- List matching files.
- Fetch raw Markdown content.
- Parse front matter and sections.
- Show task table.
- Show validation panel.
- Show raw preview.
```

## UI views

```text
Repository Home
- repo name
- default branch
- configured fragment paths
- scan button
- last scan time

Task List
- ID
- title
- status
- changelog type
- release
- assignee
- updated date

Task Detail
- structured fields
- Markdown body preview
- raw source view

Validation
- missing required fields
- invalid status
- invalid changelog category
- duplicate IDs
- malformed front matter
```

## Acceptance criteria

```text
- User can scan a repo without writing anything.
- Duplicate IDs are detected.
- Unknown Markdown sections are preserved.
- App handles empty folder gracefully.
- App handles missing config gracefully.
```

# Phase 3 — Edit fragments in browser

## Purpose

Make KATL useful as a free editor.

## Features

```text
- Create new task fragment.
- Edit existing task fragment.
- Change status.
- Change changelog category.
- Edit title, assignee, labels, release.
- Edit Markdown body.
- Add/remove acceptance criteria checkboxes.
- Preview final Markdown.
- Track dirty files.
```

## Editing behavior

```text
- Preserve unknown front matter fields.
- Preserve unknown Markdown sections.
- Normalize known fields.
- Update updated date on save.
- Do not reorder files unnecessarily.
```

## Acceptance criteria

```text
- User can create a valid new fragment.
- User can edit an existing fragment.
- Markdown preview matches saved content.
- Dirty state is obvious.
- User can discard local edits before committing.
```

# Phase 4 — Branch, commit, pull request

## Purpose

Handle the GitHub write path.

## Features

```text
- Create branch from selected base branch.
- Commit all changed fragments.
- Support creating, updating, and deleting files.
- Open pull request.
- Show link to created PR.
```

## Branch naming

Default branch pattern:

```text
katl/update-fragments-YYYYMMDD-HHMMSS
```

Example:

```text
katl/update-fragments-20260626-171500
```

## Commit message

Default:

```text
Update KATL task fragments
```

Detailed body:

```text
Updated by KATL.

Changed fragments:
- KATL-0001: Add OAuth mock server demo
- KATL-0002: Update Gatling acceptance criteria
```

## PR title

```text
Update KATL task fragments
```

## PR body

```markdown
## Summary

This PR updates KATL task/changelog fragments.

## Changed fragments

- KATL-0001 — Add OAuth mock server demo
- KATL-0002 — Update Gatling acceptance criteria

## Generated by

KATL static editor.
```

## Implementation note

For the first implementation, use **Octokit plus `octokit-plugin-create-pull-request`**. If it gets in the way, drop
down to raw GitHub REST calls.

## Acceptance criteria

```text
- User can commit multiple file edits in one PR.
- User can create new files in the PR.
- User can update existing files in the PR.
- User can delete files in the PR.
- App never writes directly to base branch by default.
- PR link opens correctly.
```

# Phase 5 — Changelog preview and release helper

## Purpose

Make the tool feel like Keep a Changelog Manager, not just a task editor.

## Features

```text
- Group unreleased fragments by changelog category.
- Preview generated CHANGELOG.md Unreleased section.
- Show tasks without changelog text.
- Show changelog fragments without linked tasks.
- Optional: update CHANGELOG.md in PR.
```

## Changelog preview

Example:

```markdown
## [Unreleased]

### Added

- Added an OAuth mock server demo for unattended authentication tests.

### Fixed

- Fixed branch creation when the selected base branch is protected.
```

## Acceptance criteria

```text
- User can preview Unreleased grouped by category.
- Changelog categories match Keep a Changelog categories.
- User can choose whether to update CHANGELOG.md.
- Existing CHANGELOG.md content is preserved below Unreleased.
```

# Phase 6 — GitHub Pages release

## Purpose

Make KATL publicly usable.

## Features

```text
- GitHub Actions workflow builds Angular app.
- Deploy to GitHub Pages.
- Version shown in footer.
- Demo repository linked from landing page.
- Sample .katl folder included.
- Security warning documented.
```

## Documentation pages

```text
- Getting started
- Token permissions
- Fragment format
- Config file
- GitHub Pages deployment
- Security model
- Known limitations
```

## Acceptance criteria

```text
- Fresh user can open hosted app and edit a demo repo.
- README explains that the token is never sent to a KATL backend.
- README explains that browser-only tokens are still risky.
- App is usable without any paid service.
```

# Phase 7 — Hardening

## Purpose

Make the free version less embarrassing and more trustworthy.

## Features

```text
- Conflict detection before PR creation.
- Better validation messages.
- Branch already exists handling.
- Retry failed GitHub calls.
- Rate limit display.
- Import/export local draft.
- Keyboard-friendly UI.
- Screen-reader-friendly labels.
- No hidden network calls except GitHub.
```

## Acceptance criteria

```text
- If base branch changes, app warns before commit.
- If a file changed remotely since scan, app warns.
- If GitHub API rate limit is low, app shows clear error.
- App passes basic accessibility checks.
```

# Phase 8 — Paid GitHub App backend

## Purpose

Start the SaaS.

## Features

```text
- GitHub App installation.
- Backend stores installation metadata.
- Backend mints short-lived installation tokens.
- Webhook receiver.
- Scheduled repo scans.
- Automatic stale task detection.
- Automatic changelog fragment validation.
- Optional PR comments/checks.
- Weekly status report.
```

## Paid-only capabilities

```text
- No pasted PAT.
- Org installation.
- Cross-repo dashboard.
- Audit history.
- Release readiness report.
- Required-fragment check.
- Task/changelog consistency check.
- Slack/email summaries.
```

## Acceptance criteria

```text
- User can install GitHub App on selected repos.
- Backend scans repos without user’s browser open.
- Backend posts check result on PR if fragments are invalid.
- Backend can generate weekly status report.
```

# Phase 9 — Repo-native project management

## Purpose

Turn KATL from a fragment editor into Jira-lite for Git-native teams.

## Features

```text
- Board view by status.
- Sprint/release field.
- Milestone/release grouping.
- Assignee workload summary.
- Blocked/stale work report.
- PR/task linkage.
- Issue/task linkage.
- Commit/task linkage.
- “What changed since last release?” report.
```

## Acceptance criteria

```text
- Team can see active work without reading raw Markdown.
- Manager can get a status report without Jira.
- Developer can update task state through PR workflow.
- Release notes can be generated from reviewed fragments.
```

## 8. Angular app architecture

Suggested modules:

```text
core/
  github/
    github-auth.service.ts
    github-repo.service.ts
    github-contents.service.ts
    github-pr.service.ts
  config/
    katl-config.service.ts

katl/
  parser/
    frontmatter-parser.ts
    fragment-parser.ts
    fragment-writer.ts
    validation.ts
  models/
    katl-fragment.ts
    katl-config.ts
    changelog-category.ts
    task-status.ts

features/
  auth/
  repo-picker/
  repo-scan/
  task-list/
  task-detail/
  changelog-preview/
  pr-create/
  settings/
```

Recommended libraries:

```text
- Angular
- Octokit
- octokit-plugin-create-pull-request
- yaml
- marked or markdown-it
- dompurify
```

Testing:

```text
- Unit tests for parser/writer.
- Golden-file tests for Markdown round trips.
- Mock GitHub API service for UI tests.
- Sample repo fixture files.
```

## 9. Data model

```ts
export type KatlStatus =
    | "todo"
    | "doing"
    | "blocked"
    | "done"
    | "wontdo";

export type KatlChangelogType =
    | "added"
    | "changed"
    | "deprecated"
    | "removed"
    | "fixed"
    | "security";

export interface KatlFragment {
    path: string;
    sha?: string;

    id: string;
    title: string;
    type: "task" | "changelog" | "combined";

    status?: KatlStatus;
    changelogType?: KatlChangelogType;
    release: string;

    assignee?: string;
    labels: string[];

    created?: string;
    updated?: string;

    summaryMarkdown?: string;
    taskMarkdown?: string;
    changelogMarkdown?: string;
    acceptanceCriteriaMarkdown?: string;
    notesMarkdown?: string;

    rawFrontMatter: Record<string, unknown>;
    unknownSections: KatlMarkdownSection[];

    validationErrors: KatlValidationError[];
}
```

## 10. GitHub API write strategy

### Simple route

Use the plugin:

```text
octokit-plugin-create-pull-request
```

Inputs:

```text
- owner
- repo
- base branch
- head branch
- files to create/update/delete
- commit message
- PR title/body
```

### Fallback route

Use raw GitHub API:

```text
- Get base ref.
- Create branch ref.
- Create/update file contents.
- Open PR.
```

### Later route

Use Git Data API for one true multi-file commit:

```text
- Get base commit/tree.
- Create blobs.
- Create tree.
- Create commit.
- Update branch ref.
- Open PR.
```

## 11. Security model for free version

KATL static/free version has no backend and no SaaS key.

Principles:

```text
- User owns their GitHub token.
- Token is used only against GitHub API.
- Token is not sent to KATL servers because no KATL server exists.
- Token is memory-only by default.
- Persistent token storage is opt-in.
- App should work with fine-grained PATs.
- App should request/write only selected repos where possible.
```

Security warnings:

```text
- Browser-based GitHub tokens are exposed to XSS risk.
- Users should prefer fine-grained PATs.
- Users should restrict tokens to specific repos.
- Users should revoke tokens after testing.
- Hosted KATL should avoid third-party scripts.
```

## 12. Pricing/product split

Free:

```text
- Static Angular editor.
- Manual token.
- Manual scan.
- Manual PR creation.
- Single selected repo per session.
```

Paid:

```text
- GitHub App.
- No pasted PAT.
- Background scans.
- Webhooks.
- PR checks.
- Release readiness.
- Weekly status reports.
- Cross-repo/project dashboard.
```

Suggested paid tier:

```text
Team: $1000/year
- Up to 5 active repos or 3 maintained projects.
- GitHub App automation.
- Release/changelog/status reports.
```

This avoids pure per-repo pricing that encourages monorepos too aggressively.

## 13. MVP definition

The MVP is complete when:

```text
- KATL runs from GitHub Pages.
- User can paste fine-grained PAT.
- User can select a repo.
- User can scan .katl/*.md or .keepachangelog.d/*.md.
- User can see parsed task fragments.
- User can edit a fragment.
- User can create a new fragment.
- User can create a branch, commit changes, and open a PR.
- User can preview the Unreleased changelog section.
```

## 14. Recommended first implementation order

```text
1. Create sample repo with .katl fragments.
2. Build parser/writer with golden tests.
3. Build Angular static shell.
4. Add token auth.
5. Add repo picker.
6. Add read-only scanner.
7. Add task list/detail UI.
8. Add edit/create.
9. Add PR creation.
10. Add changelog preview.
11. Publish to GitHub Pages.
```

## 15. One-sentence positioning

> **KATL is a free GitHub Pages app for editing repo-native task and changelog fragments, with a future paid GitHub App
that automates the boring release/status bookkeeping teams currently do by hand.**

[1]: https://github.com/tomtom-international/keepachangelog-manager "GitHub - tomtom-international/keepachangelog-manager: Python package allowing you to manage your CHANGELOG.md files · GitHub"

[2]: https://keepachangelog.com/en/1.1.0/ "Keep a Changelog"
