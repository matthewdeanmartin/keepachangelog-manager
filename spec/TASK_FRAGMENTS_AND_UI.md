# Task fragments & the assembled `TASKS.md`

Status: **proposed** · Owner: TBD · Last updated: 2026-06-25

## Where this sits relative to existing specs

This repo already has two adjacent designs:

- [`spec/tasks.md`](tasks.md) — `TASKS.md` as a flat, KAC-sectioned checklist
  (`- [ ]` / `- [x]`), parsed into `TaskItem` (`changelogmanager/tasks.py`).
- [`spec/fragments.md`](fragments.md) — *changelog* fragments as
  `<slug>.<type>.md` files in `changelog.d/`, collected into `[Unreleased]`.

This spec defines a **third, richer artifact: the task fragment** — one ticket
per file in `tickets/`, with **rigid structured markdown on top and freeform
markdown on the bottom**, assembled into `TASKS.md` the way `fragments collect`
assembles changelog fragments into `CHANGELOG.md`.

The relationship, end to end:

```
tickets/*.md   ──assemble──▶  TASKS.md   ──tasks promote──▶  [Unreleased]
(rich task                   (KAC-grouped               (changelog entries,
 fragments)                   checklist, today's          existing flow)
                              spec/tasks.md format)
```

A task fragment is a *superset* of a `TaskItem`: a fragment with only a title and
a `Category` degrades exactly to one `- [ ]` line. So this feature **does not
replace** `spec/tasks.md` — it feeds it. The assembler can emit the existing
flat `TASKS.md` schema verbatim (so `tasks promote` keeps working unchanged), and
optionally a richer grouped view.

## Why fragments at all (the merge-conflict argument)

The same reasoning behind `spec/fragments.md`: a single shared `TASKS.md` is a
merge-conflict magnet — every branch that adds a task edits the same lines. One
file per ticket in `tickets/` means two branches adding two tasks never conflict;
`TASKS.md` becomes a **generated artifact**. This mirrors the
`changelog.d/`-then-`collect` pattern the project already endorses, just for tasks
rather than changelog bullets.

```
tickets/
  0001-fragment-parser.md          <- one ticket, hand-edited
  0002-assembler.md
  0003-gui-panel.md
        │  changelogmanager tasks assemble   (parse → group → render)
        ▼
TASKS.md                            <- generated; structured part not hand-edited
```

## Anatomy of a fragment: rigid head, free body

Each `tickets/*.md` file is two regions separated by the **first** column-0 `---`
line that is not inside a fenced code block:

```
┌─────────────────────────────┐
│  RIGID HEAD                 │  structured markdown — a small fixed DOM,
│  (parsed, validated)        │  the "KAC schema"-style rigid part
├─────────────────────────────┤
│  ---                        │  the divider
├─────────────────────────────┤
│  FREE BODY                  │  any markdown the author wants;
│  (passed through verbatim)  │  never parsed, never able to fail the build
└─────────────────────────────┘
```

We use a **markdown head, not YAML front matter**, on purpose — consistent with
`spec/fragments.md`, which defers front matter to "a later phase" and keeps the
file readable without tooling. The head is a fixed sequence of well-known blocks,
intentionally rigid (think "KAC schema") so it is trivial to parse and to diff.

### The rigid head — a small fixed DOM

```markdown
# 0042 — Add a Network Config dialog

- **Category:** added            <!-- a CATEGORIES key, or a non-shipping type -->
- **Status:** in-progress        <!-- proposed | accepted | in-progress | blocked | done | wontfix -->
- **Tracker:** github#128        <!-- optional; see "Issue-tracker fields" -->
- **Labels:** ui, networking     <!-- optional, comma-separated -->
- **Assignees:** @matthew        <!-- optional, comma-separated -->
- **Milestone:** 6.2.0           <!-- optional -->
```

Head rules:

- **H1 is the title**, convention `# <id> — <summary>`. `<id>` is the filename
  stem; the assembler cross-checks them (lint warning on mismatch, never fatal).
- Metadata is a **single bullet list** of `- **Key:** value` pairs — trivially
  parseable and readable. Order-insensitive.
- **`Category` is the only required field.** A file with no usable head still
  assembles: it lands in `uncategorized` with a lint warning rather than failing
  the build — the same forgiving spirit as the existing
  `canonical_change_type()` (which already tolerates plurals and title-case).

### The divider and the free body

After the first real `---`, everything is verbatim markdown: acceptance
criteria, design notes, checklists, mermaid, screenshots, links — whatever. The
assembler copies it through untouched (only shifting heading depth so it nests
under its task). It is never validated and can never break a build. This is the
"markdown on the bottom" escape hatch that keeps the rigid head from feeling like
a straitjacket.

## Categories — reuse `CATEGORIES`, add non-shipping types

The six KAC types already live in `changelogmanager/change_types.py` as
`CATEGORIES` (each with `emoji`, `title`, `bump`). Fragments reuse that table
verbatim as the **shipping** categories — the ones eligible to reach
`CHANGELOG.md` via `tasks promote` / `fragments collect`:

| Key | `CATEGORIES` title | Ships to changelog? |
| --- | --- | --- |
| `added` | New Features | ✅ |
| `changed` | Updated Features | ✅ |
| `deprecated` | Deprecation | ✅ |
| `removed` | Removed | ✅ |
| `fixed` | Bug Fixes | ✅ |
| `security` | Security Changes | ✅ |

We then add **non-shipping categories** — real, tracked work that must *not* leak
into a user-facing changelog (the explicit "valid categories that don't get
included in the final changelog" requirement):

| Key | Meaning | Ships? |
| --- | --- | --- |
| `internal` | refactors, code-health, no user-visible effect | ❌ |
| `chore` | deps, CI, build, release plumbing | ❌ |
| `docs` | documentation-only work | ❌ |
| `test` | tests, fixtures, coverage | ❌ |
| `spike` | research/investigation, may produce no code | ❌ |

Implementation: rather than scatter a second list, extend the existing model with
a sibling table that carries the shipping flag, e.g.

```python
# change_types.py
@dataclass
class Category:
    emoji: str
    title: str
    bump: VersionCore
    ships_to_changelog: bool = True      # new; existing six default True

NON_SHIPPING: dict[str, Category] = {
    "internal": Category("hammer_and_wrench", "Internal", VersionCore.PATCH, ships_to_changelog=False),
    "chore":    Category("broom",             "Chores",   VersionCore.PATCH, ships_to_changelog=False),
    "docs":     Category("book",              "Docs",     VersionCore.PATCH, ships_to_changelog=False),
    "test":     Category("test_tube",         "Tests",    VersionCore.PATCH, ships_to_changelog=False),
    "spike":    Category("microscope",        "Spikes",   VersionCore.PATCH, ships_to_changelog=False),
}
ALL_CATEGORIES = {**CATEGORIES, **NON_SHIPPING}
```

`tasks promote` and `fragments collect` already gate on KAC type; they additionally
**skip any category whose `ships_to_changelog` is False**. **Unknown category
values are kept** (rendered under their own heading) and treated as *non-shipping
by default* — safer: an unrecognized or typo'd category never silently reaches the
public changelog. Teams opt a custom category *in* by adding it to the table.

## Custom fields — "without the app barfing"

Any `- **Key:** value` pair whose key is not one of the known keys is captured
into a `custom: dict[str, str]` bag. The parser:

- never raises on an unknown key,
- preserves the original key casing,
- preserves insertion order,
- round-trips custom fields back out on re-render.

So `**Story Points:** 5`, `**Epic:** EP-12`, `**Customer:** ACME` all just work.
Tools that don't understand a field ignore it; the field survives. This is the
"no two teams are alike" requirement, and it's consistent with `spec/fragments.md`
choosing not to require a rigid metadata schema.

## Issue-tracker fields, out of the box

This repo already speaks to GitHub (`changelogmanager/github.py`) and GitLab
(`changelogmanager/gitlab.py`). A fragment can carry the standard fields of an
issue so it round-trips with a tracker. Two profiles ship; both map onto the same
head where possible and overflow into `custom` where they don't. The on-disk
format is identical regardless of profile — the profile only governs
import/export mapping.

### GitHub Issues (default profile)

| Head key | GitHub issue field | Notes |
| --- | --- | --- |
| H1 title | `title` | |
| free body | `body` | the whole bottom region |
| `Status` | `state` + `state_reason` | `done`→closed/completed, `wontfix`→closed/not_planned, else open |
| `Labels` | `labels[].name` | comma-separated |
| `Assignees` | `assignees[].login` | `@`-stripped |
| `Milestone` | `milestone.title` | |
| `Tracker` | `number` / `html_url` | e.g. `github#128` |

### GitLab Issues (built-in alternate profile)

| Head key | GitLab issue field | Notes |
| --- | --- | --- |
| H1 title | `title` | |
| free body | `description` | |
| `Status` | `state` | `done`/`wontfix`→closed, else open |
| `Labels` | `labels` | comma-separated |
| `Assignees` | `assignees[].username` | |
| `Milestone` | `milestone.title` | |
| `Weight` | `weight` | GitLab-only; lands in `custom` under the GitHub profile |
| `Due Date` | `due_date` | ISO 8601 |
| `Confidential` | `confidential` | `true`/`false` |

An unmapped tracker-specific field (GitLab `Weight` under the GitHub profile) is
simply a custom field — it survives, it just doesn't map. This dovetails with the
existing `refs` concept in `TaskItem`/`ChangelogFragment` (`#123`, `GH-123`,
URLs), which `Tracker` generalizes.

## Data model

```python
@dataclass
class TaskFragment:
    task_id: str                      # filename stem; cross-checked vs H1
    title: str                        # H1 text after the id
    category: str                     # raw key; may be unknown
    status: str = "proposed"
    tracker: str | None = None
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    milestone: str | None = None
    custom: dict[str, str] = field(default_factory=dict)   # unknown head keys
    body_md: str = ""                 # verbatim free body
    lint: list[str] = field(default_factory=list)          # non-fatal warnings

    def to_task_item(self) -> TaskItem: ...    # the bridge to spec/tasks.md
```

Invariants:

- **Total parsing.** Any markdown file is a valid fragment; worst case is an
  `uncategorized`, all-in-`custom`/`body` fragment with lint warnings. The
  assembler never aborts on content (matches `spec/fragments.md` validation tone
  and the forgiving `canonical_change_type`).
- **Lossless round-trip.** `render(parse(text))` preserves title, every known
  field, every custom field (casing + order), and the body byte-for-byte (modulo
  trailing-newline normalization).
- **Data-driven schema.** Categories, statuses, and tracker profiles are tables,
  so teams extend by config, not by patching the parser.

## How `TASKS.md` is assembled

`changelogmanager tasks assemble` mirrors `fragments collect`:

1. **Discover** `tickets/*.md` (ignore `tickets/_*.md`, `tickets/README*`). Dir is
   configurable via `[tasks].tickets_directory`, defaulting to `tickets/`.
2. **Parse** each into a `TaskFragment`; lint but never fail.
3. **Group** by `Status`, then by `Category` (KAC order from `CATEGORIES`,
   non-shipping after, unknown last).
4. **Render.** Default output is the **existing flat `TASKS.md` schema** from
   `spec/tasks.md` (so `tasks promote` is unaffected): each fragment becomes a
   `- [ ]`/`- [x]` line under its KAC `##` heading, `done` status → checked with a
   `<!-- done: … -->` comment. A `--rich` flag instead emits a grouped view with
   the one-line summary plus the nested, depth-shifted free body.
5. **Preserve epilogue.** Content after a sentinel `---` near the end of an
   existing `TASKS.md` is carried forward (rigid-top/free-bottom, recursively).
6. **Write deterministically** (stable sort) so a no-op rebuild is a no-op diff —
   the same CI-friendliness `fragments collect` aims for.

`tasks assemble --changelog [--version X.Y.Z]` emits a KAC section containing
**only shipping categories of `done` fragments** — the bridge from task tracking
to `CHANGELOG.md`, reusing the existing collection/render path.

## CLI surface (extends the existing `tasks` group)

`spec/tasks.md` already defines `changelogmanager tasks {list,add,check,uncheck,edit,promote}`.
This adds:

| Command | Description |
| --- | --- |
| `tasks assemble` | (Re)write `TASKS.md` from `tickets/`. `--rich`, `--changelog`, `--dry-run`. |
| `tasks new "<summary>" [--category added]` | Scaffold `tickets/NNNN-<slug>.md` with a valid empty head. |
| `tasks fragments lint` | Report head problems without writing; `--strict` exits non-zero. |
| `tasks fragments import --profile github\|gitlab` | Future: build fragments from tracker issues. |
| `tasks fragments export --profile github\|gitlab` | Future: serialize a fragment to an issue payload. |

Import/export are explicitly **later phases** (consistent with `spec/fragments.md`
deferring live API sync); v1 ships the format, parser, assembler, and lint.

## GUI / TUI (the "& UI" in the filename)

The existing GUI (`changelogmanager/gui/`, `screens/`, `widgets.py`) already opens
task and changelog files. Add a **Tickets** surface:

- A read-mostly list of `tickets/*.md` grouped by Status → Category, reusing the
  existing screen/widget patterns (no new framework).
- Selecting a ticket shows the rendered head (as a small form) above the freeform
  body (as markdown/preview) — visually the same rigid-top/free-bottom split.
- An **Assemble** button runs `tasks assemble` and refreshes the `TASKS.md` view
  already present in the GUI.
- Editing in v1 is "open the file"; inline form editing of the head is a
  follow-up. Keep parity with how `spec/tasks.md` describes GUI task editing.

Nothing in the *format* depends on the GUI; the GUI is a view over it.

## Testing plan

Reuse the project's discipline (`AGENTS.md`): `uv run pytest`, the autouse
`isolate_cwd` fixture, `tmp_path`, never touch the repo's real `CHANGELOG.md`.

- **Total-parsing fuzz** (hypothesis): random/garbage bytes never raise.
- **Round-trip** (hypothesis): title, known fields, custom fields (casing +
  order), and body survive `parse → render → parse`.
- **Assembler determinism**: two runs produce byte-identical `TASKS.md`.
- **Bridge fidelity**: `assemble` default output parses cleanly via the existing
  `tasks.py` `TaskItem` parser, and `tasks promote` behaves identically to today.
- **Non-shipping exclusion**: `--changelog` excludes every non-shipping category
  and every non-`done` fragment; unknown categories treated as non-shipping.
- **Divider edge case**: `---` inside a head code fence does not split.
- **Tracker mapping**: GitHub vs GitLab profiles map the documented fields;
  unmapped fields (GitLab `Weight` under GitHub) fall through to `custom`.

## Open questions

- Should `blocked` get its own top-level `TASKS.md` group, or fold under
  `in-progress` with a 🚧 marker? (Leaning: own group, for visibility.)
- `Priority` as a known field, or leave to `custom`? GitHub has no native
  priority; GitLab fakes it with labels. (Leaning: `custom`.)
- Should `tasks assemble` default to the flat schema (safest for `promote`) or the
  `--rich` view? (Leaning: flat default, `--rich` opt-in.)
- Reuse `changelog.d/`-style date-stamped archiving for consumed/`done` tickets,
  or leave tickets in place once `done`? (Ties into `spec/tasks.md`'s archive
  question.)

---

## Author's scratch notes (free body of this very spec)

Dog-fooding: everything below this `---` is the freeform region — exactly the kind
of content a fragment's bottom half holds.

- The rigid-top/free-bottom shape is recursive: fragments have it, and the
  assembled `TASKS.md` has it. Pleasing, and intentional.
- This design deliberately makes a `TaskFragment` a superset of the existing
  `TaskItem` so we extend rather than fork `spec/tasks.md`.
- Sources consulted: Keep a Changelog 1.1.0 categories & structure
  (<https://keepachangelog.com/en/1.1.0/>); GitHub REST issue object fields
  (<https://docs.github.com/en/rest/issues/issues>); fragment-collection prior art
  (<https://pawamoy.github.io/git-changelog/>, <https://github.com/orhun/git-cliff>)
  and this repo's own `spec/fragments.md`.
