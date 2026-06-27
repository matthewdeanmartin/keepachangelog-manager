# KATL web app — remaining phases

Status: **active** · Owner: TBD · Last updated: 2026-06-26

> **This document supersedes [`spec/web_gui.md`](web_gui.md).** That earlier draft
> was written without access to this repo's real fragment specs and invented a
> `.katl/` YAML-front-matter format. Ignore it for the format; keep it only as
> background on the browser-only security posture and GitHub write strategy. The
> authoritative format specs remain
> [`spec/TASK_FRAGMENTS_AND_UI.md`](TASK_FRAGMENTS_AND_UI.md) (task fragments) and
> [`spec/fragments.md`](fragments.md) (changelog fragments).

## 1. What exists today (the baseline)

The app lives in [`web/`](../web) — Angular 19, standalone components, browser-only,
no backend. It is **local-first**: it ships sample tickets and persists edits to
`localStorage`, so a non-developer can use it with zero GitHub setup.

Built and shipping:

- **Domain model + parser/writer** (`web/src/app/core/`) faithful to the real
  on-disk formats, so files round-trip with the Python CLI:
  - `tickets/*.md` — rigid markdown head (`- **Key:** value`, H1 `# <id> — <title>`,
    body split on the first column-0 `---` outside a code fence) + free body.
  - `changelog.d/<slug>.<type>.md` — bullet text, type in filename.
  - Categories mirror `changelogmanager/change_types.py`: six **shipping** KAC
    types + five **non-shipping** (`internal`, `chore`, `docs`, `test`, `spike`).
- **Screens** (`web/src/app/features/`): **Board** (tickets by status), **Ticket**
  editor (rigid-head form + free-body markdown + live rendered-file preview +
  lint), **Changelog** fragment manager, **Release preview** ([Unreleased]
  section `fragments collect` would produce, excluding non-shipping, plus a
  consistency report).
- **`RepoService`** — a signal-based workspace abstraction that already tracks
  **dirty files** (`dirtyPaths()`), the seam the write-path adapters plug into.
- **Tests** — **Vitest** (`npm test`), pure-logic specs in Node. **No Karma, no
  puppeteer, no browser** — that toolchain was removed deliberately; do not
  reintroduce it. Specs live next to the code as `core/**/*.spec.ts`.
- **CI/deploy** — `.github/workflows/web-pages.yml` builds, tests, and deploys to
  GitHub Pages.

## 2. The end-to-end workflow this serves

```
PMs / BAs                         every ~3 wks        Developers              Release date
write task fragments  ──merge──▶  tickets/ on   ──fork & edit──▶  add a       ──CI/CLI──▶  CHANGELOG.md
on the Board (no git)             develop          changelog.d/   changelog      fragments collect /
                                                   fragment       fragment       tasks assemble
```

- **Non-developers are first-class authors.** They never see git or raw markdown
  unless they ask for it (see §5).
- **Developers** turn a `done` shipping ticket into a `changelog.d/*` fragment
  (the Ticket editor already has a "Create changelog fragment" shortcut).
- **CI / the Python CLI** owns the final assembly into `CHANGELOG.md`; the web app
  only *previews* it. The web app never writes `CHANGELOG.md` directly.

## 3. Decisions that pin the remaining work

| Question | Decision |
| --- | --- |
| Write path to `tickets/` and `changelog.d/` | **Both adapters behind one interface** — a GitHub PAT + PR adapter *and* a local-filesystem adapter, selectable at runtime (§4). |
| Hosting | **One shared GitHub Pages instance.** Non-devs visit a URL, paste their own PAT, pick a repo. One deploy serves all repos. |
| Non-dev authoring UX | **Form-first; markdown hidden** behind an "advanced" toggle (§5). |

## 4. Phase W1 — pluggable backends (the write path)

> **Progress (2026-06-27): W1 complete (W1a ✅ W1b ✅ W1c ✅).** `RepoBackend`
> lives in `web/src/app/core/backend/`; `RepoService` delegates IO to it. The
> **Workspace** screen offers all three backends — sample (localStorage),
> **local folder** (File System Access API, feature-detected/Chromium-only), and
> **GitHub** (PAT in memory only) — and a **commit bar** opens the PR for the
> GitHub backend. All backends are unit-tested in Node with fakes (a fake
> `fetch` for GitHub, in-memory handle fakes for the filesystem) — no live token,
> no browser. Quality gates (`make check`: eslint + prettier + vitest + knip) and
> the production build are green. **Next: W2 (form-first authoring).**

`RepoService` no longer hard-wires storage: it owns parsing + dirty-tracking and
delegates IO to a **`RepoBackend`** with three implementations, the UI unchanged.

```ts
interface RepoBackend {
  readonly id: 'local-storage' | 'github' | 'filesystem';
  scan(): Promise<RawFile[]>;            // load tickets/* and changelog.d/*
  save(changes: FileChange[]): Promise<SaveResult>;  // create/update/delete
  capabilities: { pullRequest: boolean; directWrite: boolean };
}
```

`RepoService` keeps the parse/dirty-tracking logic and delegates IO to the chosen
backend. A **Workspace picker** screen chooses the backend (and its config) and
persists the *non-secret* choice.

### W1a — local-storage backend (exists, formalize)

The current behavior, recast as a backend. Keeps the zero-setup demo working.

### W1b — GitHub backend (PAT + PR)

Browser-only, per the security model in `spec/web_gui.md §11` (still valid):

- **Auth:** fine-grained PAT paste-in. Default **memory-only**; opt-in
  `localStorage` persistence with a clear warning. "Clear token" button. The token
  is sent **only** to `api.github.com`.
- **Required token scopes:** Contents read/write, Pull requests read/write,
  Metadata read.
- **Scan:** read `tickets/*.md` + the configured `changelog.d/` via the Contents
  API (or Git Trees for one round trip); record each file's `sha`.
- **Save:** create a branch off the base, commit all `dirtyPaths()` (create /
  update / delete), open a PR. Use the **Git Data API** (blobs → tree → commit →
  ref) for one true multi-file commit; fall back to `octokit-plugin-create-pull-request`.
  - Branch: `katl/update-fragments-YYYYMMDD-HHMMSS`.
  - The app **never writes the base branch directly.**
  - Show the created PR link.
- **Conflict guard:** before committing, re-check each file's `sha`; warn if it
  changed remotely since scan.

### W1c — filesystem backend (File System Access API)

For a developer working in a local clone:

- `showDirectoryPicker()` → grant access to the repo root.
- Scan/save read and write `tickets/` and `changelog.d/` **in place**; the dev
  commits via their own git. `capabilities.pullRequest = false`.
- Feature-detect the API (Chromium-only); hide this backend where unsupported.

**Acceptance (W1):** the Board/Ticket/Changelog/Preview screens work unchanged
against any backend; switching backend is a config choice, not a code path the UI
knows about; the GitHub backend opens a real PR from edited fragments; the FS
backend round-trips files on disk that the Python CLI then parses.

## 5. Phase W2 — form-first authoring for non-developers

> **Progress (2026-06-27): W2 ✅.** The Ticket editor is form-first: Details
> (title, type, status, assignees, labels) plus structured **Summary**,
> **Acceptance Criteria** (add/remove checkbox rows), and **Notes** editors, an
> **Advanced** toggle that reveals the raw markdown body + rendered-file preview,
> and **templates** (feature / bug / chore) for new tickets. The body stays the
> single source of truth: structured edits go through a tested
> `body-sections` parse/serialize layer, so **unknown sections survive verbatim**
> and editing is a proven fixed point (no cursor jumps / data loss). Lint shows as
> friendly "Hints". `core/body-sections.ts` + `core/templates.ts`; 12 new tests.
> **Next: W3 (board interactions).**

The rigid head is already a form. This phase makes the **whole ticket** feel like
a ticket tool, not a markdown editor:

- **Guided ticket form.** Title, Category (dropdown with KAC titles + emoji,
  shipping vs non-shipping made obvious), Status, Assignees, Labels, Milestone —
  no markdown syntax visible.
- **Structured body sections instead of a raw textarea.** Render the free body as
  editable sections (Summary, Acceptance Criteria as add/remove checkbox rows,
  Notes). On save, serialize back to the markdown the CLI expects; **unknown
  sections are preserved verbatim** (the format's escape hatch).
- **Templates.** "New bug", "New feature", "New chore" scaffold a head + section
  skeleton (uses the CLI's `tasks new` conventions).
- **Advanced toggle.** A single switch reveals the raw markdown body + the
  rendered-file preview (today's view) for power users. Hidden by default.
- **Inline validation as guidance**, not errors: surface lint as friendly hints
  ("This ticket has no category — it won't appear in the changelog").

**Acceptance (W2):** a non-developer can create a valid ticket end to end without
seeing raw markdown; round-trip still lossless (`render(parse(x)) == x` modulo
trailing newline); custom fields and unknown body sections survive a form edit.

## 6. Phase W3 — board as a tool, not a list

- **Drag-and-drop between status columns** (writes `Status` in the head; marks
  dirty).
- **Filters / grouping:** by assignee, category (shipping vs not), milestone,
  label; search.
- **Milestone / release lane:** group tickets by `Milestone` to preview a release.
- **Quick-add** card in a column.

**Acceptance (W3):** changing a card's column updates the underlying
`- **Status:**` value; filters never mutate files; a milestone view lists the
tickets that would ship.

## 7. Phase W4 — release preview & PR for changelog assembly

The app previews `[Unreleased]` today. Extend toward the release ceremony,
without ever owning `CHANGELOG.md` assembly (the CLI does that):

- **"Open release PR"**: bundle the changelog fragments (and optionally a
  generated `[Unreleased]` block for human review) into a single PR, so CI's
  `fragments collect` runs on merge.
- **Readiness report:** done shipping tickets missing a changelog fragment;
  changelog fragments with no linked ticket; tickets stuck in a status.
- Make explicit in the UI that **non-shipping categories never reach the
  changelog** and **unknown categories are non-shipping by default**.

**Acceptance (W4):** preview matches what `fragments collect` produces for the
same inputs (golden test against CLI output); readiness report is accurate;
release PR contains exactly the fragment files, not a hand-assembled changelog.

## 8. Phase W5 — Pages hardening & docs

- The shared GitHub Pages deploy exists; finish: version in footer, SPA 404
  fallback (done in workflow), demo repo linked from a landing page, sample
  `tickets/` + `changelog.d/` fixtures.
- **Docs pages:** getting started, token permissions, fragment format (link the
  real specs), security model, known limitations.
- **Accessibility & resilience:** keyboard-navigable board and forms,
  screen-reader labels, GitHub rate-limit display, retry on transient API errors,
  "no hidden network calls except GitHub".

**Acceptance (W5):** a fresh non-dev opens the hosted app, pastes a PAT, picks a
repo, authors a ticket, and opens a PR — entirely from the browser.

## 9. Phase W6 — paid GitHub App (unchanged, later)

The SaaS direction from `spec/web_gui.md §Phase 8/12` still stands and is out of
scope here: GitHub App installation, backend installation tokens, webhooks,
scheduled scans, PR checks that validate fragments, cross-repo dashboard, weekly
status reports. Nothing in W1–W5 should block it; the `RepoBackend` interface
gives the App a natural place to add an "installation token" backend.

## 10. Non-negotiable constraints (carry into every phase)

- **Round-trip fidelity with the Python CLI.** Any file the web app writes must
  parse identically in `changelogmanager`. This is the whole reason the app exists
  rather than a generic markdown editor.
- **Total, forgiving parsing.** Garbage input never throws; worst case is an
  `uncategorized` fragment with lint warnings. Matches `canonical_change_type()`.
- **The web app never assembles `CHANGELOG.md`.** It previews and opens PRs; the
  CLI / CI own assembly.
- **Browser-only, no backend** through W5. Token is the user's; sent only to
  GitHub; memory-only by default.
- **Tests are Vitest in Node.** Pure-logic specs under `core/`. No browser test
  runner. UI logic that needs testing should be extracted into pure functions
  rather than pulling in a DOM test harness.
- **Stay on Angular 19** unless a concrete need forces an upgrade (Angular 22+
  requires Node ≥ 22.22, which the dev environment does not yet have).

## 11. Suggested order

```
W1a  formalize local-storage backend behind RepoBackend
W1b  GitHub PAT + PR backend  ──┐ (the MVP unlock)
W1c  filesystem backend          │
W2   form-first authoring        │ can proceed in parallel with W1c
W3   board interactions
W4   release preview → PR
W5   Pages hardening + docs
W6   (later) paid GitHub App
```

## 12. Open questions

- Should the GitHub backend default to **one fragment per PR** (clean review) or
  **batch all dirty fragments** into one PR (fewer PRs)? Leaning batch, with an
  option.
- For the form-first body (§5), do we standardize on fixed sections (Summary /
  Acceptance Criteria / Notes), or let `[tasks]` config declare the section set?
- Should the filesystem backend (W1c) also offer to **run** `tasks assemble` /
  `fragments collect` via a local helper, or stay strictly file-IO and leave
  assembly to the dev's terminal? Leaning strictly file-IO.
- Where does the **repo + base-branch config** for the shared Pages instance live
  — purely in the URL/localStorage per user, or also discoverable from a
  `.changelogmanager`/config file in the selected repo?
