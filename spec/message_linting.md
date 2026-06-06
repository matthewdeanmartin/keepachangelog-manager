# Commit message linting design

Status: **Phases 1–3 implemented (Phase 3 apply intentionally stubbed)** · Owner: TBD · Last updated: 2026-06-06

> **Implementation progress.** Phase 1 (core + pre-commit hook), Phase 2 (the
> read-only `lint-commits` audit), and Phase 3 (the `rewrite-messages` plan path,
> scoped to unpushed commits, with `--apply` left as a deliberate fail-fast stub)
> are implemented and tested; see the "Implementation status" section at the end
> of this spec. Phase 4 (GUI rewriter) remains proposed.

## Goal

`backfill --source commits` and `from-commits` are only as good as the commit
messages they read. Both rely on a *commit-message schema*
(`conventional`, `gitmoji`, `keepachangelog`, or `auto`) to map a subject line
onto a Keep a Changelog change type. When a commit subject does not match any
schema, backfill silently falls back to `("changed", <raw subject>)` at low
confidence — which is exactly the garbage we want to keep out of a changelog.

This spec adds **commit message linting**: tooling that checks a commit subject
against the project's configured schema *before* it lands, plus an audit mode
for past commits and an (opt-in, dangerous) history-rewrite helper to fix old
messages. The aim is to make the input to backfill trustworthy so the output
needs less hand-editing.

**Audience split:** the CLI surfaces (`lint-commits`, and especially the
`rewrite-messages` history-rewriter) are designed for **LLMs/agents** —
non-interactive, JSON-first, deterministic flags. **Humans drive the message
rewriter through the GUI** (Feature 4), which wraps the same core in
review-and-confirm ergonomics. The pre-commit hook serves both.

The validation rule, stated plainly:

> A commit subject either declares a **valid KAC change type** via a recognized
> schema prefix (e.g. `Added: …`, `feat: …`, `🐛 …`), **or** it is recognized as
> an intentionally **non-changelog** commit (e.g. `chore:`, `docs:`, `refactor:`).
> Anything else — a bare `do formatting again` with no recognizable prefix —
> fails the lint.
>
> Critically: `Word: something` only passes when `Word` resolves to a valid KAC
> category. `Frobnicate: the widget` fails because `Frobnicate` is not a KAC
> category and not a known skip-type — it would otherwise be backfilled as a
> bogus `changed` entry.

## Non-goals

- Enforcing message *content* quality (grammar, imperative mood, length caps,
  ticket references). This spec is about *classifiability*, not prose style.
- Replacing `commitlint`, `gitlint`, or `commitizen`. We integrate with
  `pre-commit` and reuse our own schema; we do not reimplement a general commit
  linter.
- Being a general-purpose history-rewriting tool. The rewrite helper is a thin,
  guarded convenience around `git filter-repo`, not a BFG successor.
- Changing how backfill classifies commits. Linting reuses the *exact* parser
  registry in `changelogmanager/backfill.py` so "lint passes" ⇔ "backfill can
  classify it". The two must never drift.

## Background: the schema this validates against

The single source of truth already lives in `changelogmanager/backfill.py` and
`changelogmanager/change_types.py`. Linting must call into these, not duplicate
them.

- **Valid KAC change types** — `change_types.TYPES_OF_CHANGE`:
  `added`, `changed`, `deprecated`, `removed`, `fixed`, `security`.
- **Schema parsers** — `backfill.commit_parsers_for_schema(schema)` returns the
  ordered parser callables for `conventional` / `gitmoji` / `keepachangelog` /
  `auto`. Each parser returns `(change_type, message)` or `None`.
- **Conventional → KAC map** — `backfill.CONVENTIONAL_TO_KAC`. Note the entries
  whose value is `None`: `refactor`, `docs`, `style`, `test`, `tests`, `build`,
  `ci`, `chore`. These are the **recognized non-changelog types**. A
  Conventional Commit `chore: do formatting again` parses successfully but maps
  to `None`, meaning "valid, intentionally excluded from the changelog".

This produces a three-way classification for any subject, which the linter
surfaces directly:

| Outcome | Meaning | Lint result (default) |
|---|---|---|
| `CHANGELOG` | matched a schema, mapped to a KAC type | **pass** |
| `SKIP` | matched a schema, but type is non-user-facing (`chore:`, `docs:`…) | **pass** |
| `UNCLASSIFIED` | matched no schema, or `Word:` where `Word` is unknown | **fail** |

The crucial gap today: `backfill.entries_from_commits` treats `UNCLASSIFIED` as
`("changed", subject)` at low confidence rather than rejecting it. Linting
closes that gap at commit time so the `UNCLASSIFIED` case rarely reaches
backfill at all.

## Classification API (new shared core)

Add a small, dependency-free module `changelogmanager/message_lint.py` that the
pre-commit hook, the audit command, and the rewrite planner all share. It must
not perform any I/O of its own beyond what git helpers already provide.

```python
from enum import Enum
from dataclasses import dataclass

class LintOutcome(Enum):
    CHANGELOG = "changelog"        # maps to a KAC change type
    SKIP = "skip"                  # recognized non-changelog type
    UNCLASSIFIED = "unclassified"  # matched nothing → would be a bogus entry

@dataclass(frozen=True)
class LintResult:
    subject: str
    outcome: LintOutcome
    change_type: str | None        # set when outcome == CHANGELOG
    matched_schema: str | None     # which parser matched (conventional/gitmoji/kac)
    reason: str                    # human explanation, esp. for UNCLASSIFIED

def classify_subject(subject: str, *, schema: str = "auto") -> LintResult: ...
```

`classify_subject` is the seam between linting and `backfill`. Its decision tree:

1. Strip a known *skip-only* prefix first. Run the subject through the
   Conventional parser's type extraction (`CONVENTIONAL_RE`); if the type is a
   key in `CONVENTIONAL_TO_KAC` whose value is `None`, return `SKIP`. This is
   what lets `chore: do formatting again` pass while a prefix-less
   `do formatting again` fails.
2. Otherwise call `backfill.classify_commit_subject(subject, schema=schema)`.
   - non-`None` → `CHANGELOG` with the returned `change_type`.
   - `None` → `UNCLASSIFIED`.
3. For the explicit `keepachangelog` schema, a `Word:` prefix whose `Word` is
   not in `TYPES_OF_CHANGE` must yield `UNCLASSIFIED` with a reason naming the
   valid categories (this is the headline requirement). Because
   `KEEPACHANGELOG_RE` only matches the six valid categories, an unknown `Word:`
   already fails to match — `classify_subject` just needs to produce a helpful
   `reason` for it.

### Behavior table (must be covered by tests)

| Subject | `auto` | `keepachangelog` | `conventional` |
|---|---|---|---|
| `Added: dark mode` | CHANGELOG/added | CHANGELOG/added | UNCLASSIFIED |
| `feat: dark mode` | CHANGELOG/added | UNCLASSIFIED | CHANGELOG/added |
| `🐛 fix npe` | CHANGELOG/fixed | UNCLASSIFIED | UNCLASSIFIED |
| `chore: do formatting again` | SKIP | UNCLASSIFIED\* | SKIP |
| `docs: tidy readme` | SKIP | UNCLASSIFIED\* | SKIP |
| `Frobnicate: the widget` | UNCLASSIFIED | UNCLASSIFIED | CHANGELOG/changed† |
| `do formatting again` | UNCLASSIFIED | UNCLASSIFIED | UNCLASSIFIED |
| `Merge branch 'main'` | UNCLASSIFIED‡ | UNCLASSIFIED‡ | UNCLASSIFIED‡ |

\* Under the *explicit* `keepachangelog` schema there is no Conventional parser
to recognize `chore:`/`docs:` as a skip-type. To avoid punishing teams that
legitimately mix in `chore:` commits, the skip-prefix detection in step 1 runs
**regardless of the selected schema** (it is a recognition concern, not a
classification one). With that, the `chore:`/`docs:` rows are `SKIP` under every
schema; the column is shown without the asterisk in the final implementation.
This footnote records why.

† `Frobnicate:` looks like a Conventional type (`word:` shape) and
`CONVENTIONAL_TO_KAC.get("frobnicate", "changed")` defaults to `changed`. This
is the existing "unknown conventional type ⇒ changed" behavior. The linter has a
config knob, `allow_unknown_conventional_types` (default **false**), that
escalates this row to `UNCLASSIFIED` so novel made-up types are caught rather
than silently changelog'd. When `true`, it stays `CHANGELOG/changed` to match
backfill's current leniency.

‡ Merge commits: `backfill` already passes `--no-merges` to git, so merges never
reach it. The linter must mirror that — merge commits (detected by >1 parent in
audit/rewrite modes, or a `Merge ` subject heuristic in the pre-commit hook
where parents aren't yet known) are **exempt** from linting entirely, never
`UNCLASSIFIED`.

## Configuration

Linting reads a new `[validation]` (internal `project.validation`) sub-area so
it lives next to `enforce_preamble` and `format`. Surface via a
`get_message_lint_options(config)` reader in `changelogmanager/config.py`
mirroring `get_format_options`.

On-disk (unwrapped schema), e.g. in `pyproject.toml`:

```toml
[tool.changelogmanager.validation.message_lint]
enabled = true                          # master switch (default false)
schema = "auto"                         # auto|conventional|gitmoji|keepachangelog
allow_unknown_conventional_types = false
allow_skip_types = true                 # treat chore/docs/etc. as pass (SKIP)
exempt_patterns = [                     # regexes; matching subjects always pass
  "^Merge ",
  "^Revert ",
  "^fixup! ",
  "^Bump version",
]
```

Defaults are chosen so that enabling the feature on an existing repo is the only
deliberate step; the schema default (`auto`) matches `backfill`/`from-commits`.
When `schema` is unset here, fall back to any existing project-level commit
schema default before `auto`.

Validation of the config block: `schema` must be one of the four known names
(reuse the `choices` already used by the parser); `exempt_patterns` must compile
as regexes (a bad pattern is a config error surfaced via `logging.Error`, not a
crash mid-hook).

## Feature 1 — pre-commit hook (validate at commit time)

### Console-script entry point

Add a dedicated, fast-starting entry point so the hook does not pay for the full
CLI import graph (argparse tree, GUI, github/gitlab/pypi modules):

- `changelogmanager-lint-message FILE` — reads a commit message file (the path
  pre-commit passes for `commit-msg`), lints its **subject line** (first
  non-comment line), prints a diagnostic on failure, exits non-zero.

Wire it in `pyproject.toml` `[project.scripts]` alongside the existing console
script. It imports only `config`, `message_lint`, and the relevant `backfill`
helpers.

Exit codes: `0` pass (CHANGELOG or SKIP or exempt), `1` lint failure,
`2` usage/config error. Honor `--error-format llvm|github` so CI annotations
work, matching the existing CLI convention.

### `.pre-commit-hooks.yaml`

Ship a hook definition at the repo root so downstream users can reference this
project as a pre-commit repo:

```yaml
- id: changelog-message-lint
  name: Keep a Changelog commit message lint
  entry: changelogmanager-lint-message
  language: python
  stages: [commit-msg]
  always_run: true
```

`commit-msg` stage is required: that is the only stage where pre-commit passes
the message file. Document that `--hook-stage commit-msg` / installing the
`commit-msg` hook type is necessary (`pre-commit install --hook-type
commit-msg`).

### Example failure output (llvm format)

```
<commit-msg>:1: error: commit subject is not classifiable by the 'auto' schema
  subject: do formatting again
  hint: prefix with a Keep a Changelog category (Added:, Changed:, Deprecated:,
        Removed:, Fixed:, Security:) or a Conventional type
        (feat:, fix:, …, or chore:/docs:/refactor: to intentionally skip).
```

### Non-changelog commits must be easy

Because `SKIP` outcomes pass, a developer doing real non-changelog work writes
`chore: do formatting again` (or `docs:`, `refactor:`, etc.) and the hook is
satisfied. The hook never forces a changelog category onto a commit that should
not have one — it only rejects subjects that are *ambiguous* (neither a category
nor an explicit skip).

## Feature 2 — audit past commits (`backfill lint` / `lint-commits`)

A read-only command that walks history and reports unclassifiable subjects, so a
team can gauge how much cleanup adoption needs and which commits would become
junk `changed` entries on backfill.

### Command shape

Add a subcommand. Two reasonable homes; recommend a top-level `lint-commits`
mirroring `from-commits` so it composes with the same range flags:

```sh
changelogmanager lint-commits [--since REF] [--until REF] [--all-history]
                              [--commit-schema auto|conventional|gitmoji|keepachangelog]
                              [--max-commits N] [--show pass|skip|fail|all]
                              [--json]
```

- Reuses `backfill.git_log_all_decorated` / `git_log_between` and
  `enforce_commit_budget` for the walk and the runaway guard — no new git
  plumbing.
- Default range mirrors `from-commits`: since the last tag unless
  `--all-history`.
- `--show fail` (default) lists only `UNCLASSIFIED` commits; `all` is a full
  classification dump.

### Output

Human mode — a grouped summary plus the offending commits:

```
Scanned 312 commits since v1.2.0
  changelog : 180   skip : 121   unclassified : 11   (exempt : 6 merges)

Unclassified (would become low-confidence 'changed' entries on backfill):
  a1b2c3d  do formatting again
  d4e5f6a  wip
  ...
Fix these with `changelogmanager rewrite-messages` or amend interactively.
```

JSON mode (`--json`) emits a machine-readable object: per-outcome counts and an
array of `{sha, subject, outcome, change_type, matched_schema, reason}`. This is
the CI gate shape — a job can fail when `unclassified > 0`. Exit code is `1`
when any non-exempt `UNCLASSIFIED` commit is found and `--strict`/CI mode is
set; otherwise `0` (audit is informational by default).

## Feature 3 — rewrite old messages (`rewrite-messages`)

The dangerous one — so it is **deliberately scoped down and the apply path is
left unimplemented** until full safeties are in place. Rewriting history that has
already been pushed corrupts collaborators' clones and is irreversible; we refuse
to ship that risk on a convenience command.

### Hard scope: unpushed commits only

`rewrite-messages` will **only ever** consider commits that are **not yet
pushed** to any remote-tracking branch. Concretely the candidate range is
bounded by the upstream:

```
@{upstream}..HEAD      # or @{push}..HEAD when configured
```

Commits reachable from any remote-tracking ref are **out of scope, permanently**
— the command must refuse to include them, not merely warn. This bounds the blast
radius to local-only history a developer can safely amend, and sidesteps the
"force-push + everyone re-clones" catastrophe entirely. If there is no upstream
(a brand-new local branch), the range is still bounded and the command states
clearly that it is operating on local-only commits.

This makes `rewrite-messages` a *bulk local cleanup* tool — the safe middle
ground between `git commit --amend` (last commit only) and
`git rebase -i`/`filter-repo` over shared history (out of scope). For the most
recent commit, the docs should still recommend plain `git commit --amend`.

### Confirmation is mandatory

Even within the unpushed-only scope, applying requires explicit consent:

- **`--yes`** on the CLI (the agent/non-interactive path), **or**
- an interactive **`input()` confirmation** in a TTY (the human-at-a-terminal
  path), reusing the existing `release` confirmation pattern.

A bare apply attempt in a non-TTY without `--yes` is a usage error (exit 2) that
names the missing flag — never a hang, never an implicit "yes".

### Apply is UNIMPLEMENTED for now

The **plan/preview path is implemented**; the **apply path is an explicit
fail-fast stub**, following this project's established "hide until real" pattern
for not-yet-safe branches (see the future-phase backfill branches in
`spec/fill_gaps.md`). Until the full safety envelope below is built and tested,
`--apply` raises a handled error explaining that history rewriting is not yet
implemented and pointing at `git commit --amend` / `git rebase -i` for now.

Reasons the apply path stays stubbed until later:

- The actual rewrite must be proven to never touch pushed commits, never touch
  bodies, never touch merge commits, and to refuse on a dirty tree — each needs
  isolated tests against throwaway repos.
- `git filter-repo` (the intended engine) is an external optional dependency
  that still needs runtime detection + an install hint.
- Re-lint-before-write (fail-closed) and a verified post-rewrite state need to
  be in place so a rewrite can't land history in a *still-wrong* state.

### Command shape (LLM-facing CLI)

```sh
changelogmanager rewrite-messages [--commit-schema …]
                                  [--plan-out FILE]       # write mapping plan (default action)
                                  [--auto-prefix changed] # bulk-prefix unclassified in the plan
                                  [--apply]               # UNIMPLEMENTED: fail-fast stub
                                  [--yes]                 # consent for a future apply path
                                  [--json]                # machine-readable plan
```

Note there is **no `--since`/`--until`**: the range is fixed to unpushed commits
(`@{upstream}..HEAD`) and is not user-overridable, by design. There is **no
`--force`**: nothing about this command may reach pushed history, so there is
nothing to force past.

**Plan mode (default; implemented; no history touched).** Runs the audit over the
unpushed range and, for each non-exempt `UNCLASSIFIED` commit, proposes a
rewritten subject (prepend `Changed: `, or a keyword-guessed category). Writes a
mapping plan to `--plan-out` (or stdout under `--json`). The record shape is
stable and round-trippable:

```
sha<TAB>old_subject<TAB>suggested_subject<TAB>outcome_after
```

Under `--json`, the same as an array of objects plus the audit counts and the
`unpushed_range` it was computed over. This is the artifact an LLM reads, reasons
over, and edits — and, once apply lands, re-feeds. **No history is touched in
plan mode, ever**, so it is always safe to run.

**Apply mode (`--apply`; UNIMPLEMENTED).** Currently a fail-fast stub as above.
When built, it will: re-verify the range is still entirely unpushed; require
`--yes` or an `input()` confirmation; re-lint each proposed subject and refuse
the batch if any is still `UNCLASSIFIED` (fail-closed); refuse on a dirty tree;
and only then run `git filter-repo --message-callback` over the unpushed range,
editing subjects only and never merge commits.

### Future tooling choice (when apply is built)

The intended engine is **`git filter-repo`** (the modern successor to
`git filter-branch` / BFG) via `--message-callback`, as an **optional**
dependency (like `jiggle-version` for `--bump-versions`): detected at runtime
with an install hint, never a traceback. Plan mode never needs it.

### Testing constraint

Per `CLAUDE.md`, the `isolate_cwd` fixture `chdir`s tests into temp dirs. Any
future rewrite test must build a throwaway git repo in `tmp_path` (with a fake
"remote" to exercise the pushed/unpushed boundary) and operate only there; smoke
scripts under `scripts/` must confine any rewrite to their `build/` temp dirs.
The repo must never rewrite its own history during a test run.

## Feature 4 — GUI message rewriter (the human path)

**Division of labor:** the CLI `rewrite-messages` command is the LLM/agent
surface; **humans rewrite messages in the GUI.** Both call the same
`message_lint` + rewrite core, so behavior can't diverge — but the GUI wraps it
in the review-and-confirm ergonomics a person needs before rewriting history.

### Why not just reuse the CLI runner

The existing GUI batch screens (`BackfillScreen`) drive the CLI in-process via
`gui/cli_runner.run_cli`, which captures stdout/stderr and shows a transcript.
That fire-and-forget model is wrong for a destructive, review-heavy operation:
it can't surface a per-commit editable plan, and it can't host a real
confirmation gate. The rewriter therefore gets a **dedicated, model-driven
screen** (closer to `EditScreen`'s live model than to `BackfillScreen`'s CLI
transcript), calling the rewrite core's plan/apply functions directly rather
than shelling argv through `run_cli`.

Like the CLI, the GUI is scoped to **unpushed commits only** and its **apply
path stays unimplemented** until the full safety envelope ships. The screen is a
review-and-suggest surface for now; the Apply button is present but disabled with
an explanatory note.

### Screen shape

Add `gui/screens/rewrite.py` (`RewriteMessagesScreen(Screen)`, registered in
`app.SCREEN_CLASSES` and the Screens menu) following the existing `Screen`
contract (`build_body`, left `CommandList`, shared `app_state`). Layout:

- **Scope banner** — states "unpushed commits only (`@{upstream}..HEAD`)" so the
  user understands the command can never touch shared history. A commit-schema
  combo (reusing the `combo` helper, factored into `gui/widgets.py`) is the only
  range control; there is intentionally no since/until.
- **Scan** button → runs **plan mode** of the core (read-only) and populates a
  table.
- **Plan table** — one row per non-exempt `UNCLASSIFIED` unpushed commit: short
  sha, old subject, and an **editable** "new subject" cell (default = the core's
  suggestion). The human fixes each line in place; live re-lint colors the row
  green (now `CHANGELOG`/`SKIP`) or red (still `UNCLASSIFIED`).
- **Apply** button → **disabled (unimplemented)** with an inline note that
  history rewriting is not yet enabled and pointing at `git commit --amend` /
  `git rebase -i`. When apply is eventually built, the button enables only when
  every row is green (fail-closed) and the working tree is clean.

### Future human confirmation gate (when apply is built)

The eventual apply path will, in addition to being unpushed-only, require a
deliberate confirmation (e.g. typing the branch name — the GUI analog of the
CLI's `--yes`/`input()`), refuse on a dirty working tree, and call
`controller.reload()` afterward. None of this is wired while apply is stubbed.

### Respecting GUI dry-run

While apply is unimplemented the screen is effectively always "plan only". The
shared top-panel **Dry run** checkbox remains consistent with that: scanning and
suggesting never write anything.

## Cross-cutting: keep lint and backfill in lockstep

The whole feature's correctness rests on one invariant:

> `classify_subject(s, schema=X).outcome == UNCLASSIFIED`
> ⇔ `backfill.classify_commit_subject(s, schema=X) is None`

(modulo the `SKIP` refinement and the `allow_unknown_conventional_types` knob).

Enforce it with a property test (hypothesis is already a dev dependency, per
`CLAUDE.md`) that feeds generated subjects to both code paths and asserts the
equivalence. If a future change to `backfill`'s parsers breaks this, the test
fails — preventing drift between "what the hook accepts" and "what backfill can
actually use".

## Surfaces at a glance

| Surface | Who uses it | What it does |
|---|---|---|
| `changelogmanager-lint-message` (pre-commit) | commit-msg hook | reject `UNCLASSIFIED` subjects at commit time |
| `lint-commits` (CLI) | humans + agents + CI | read-only audit of past commits |
| `rewrite-messages` (top-level CLI) | **LLMs / agents** | plan/suggest over **unpushed** commits; apply is an unimplemented stub |
| Rewrite Messages GUI screen | **humans** | review-and-suggest over the same core; apply disabled until safe |

## Phasing

1. **Phase 1 — core + hook.** `message_lint.py`, config reader,
   `changelogmanager-lint-message` entry point, `.pre-commit-hooks.yaml`,
   property test for the lockstep invariant. Highest value, lowest risk.
2. **Phase 2 — audit.** `lint-commits` command (read-only) reusing the git
   walk; JSON output for CI gating.
3. **Phase 3 — rewrite plan/suggest core + LLM CLI (apply stubbed).** Shared
   plan core scoped to **unpushed commits only** (`@{upstream}..HEAD`); top-level
   `rewrite-messages` command with the LLM-facing plan-mode default. **`--apply`
   ships as an explicit fail-fast stub** requiring `--yes`/`input()` consent in
   its eventual form; the real rewrite (via `git filter-repo`, fail-closed
   re-lint, dirty-tree/pushed-commit refusal) is deferred until full safeties
   and isolated tests are in place.
4. **Phase 4 — GUI rewriter (apply stubbed).** `RewriteMessagesScreen` on top of
   the Phase 3 core: editable plan table, live re-lint, unpushed-only scope
   banner. The Apply button is present but disabled until the apply path is real.

## Open questions

- Should the pre-commit hook lint **only the subject**, or also reject a missing
  blank line / over-long subject? Proposed: subject classifiability only;
  defer style to `gitlint`. (Stated as a non-goal above.)
- For `--auto-prefix`, is a keyword→category guesser (e.g. "fix"→`fixed`) worth
  it, or should we always prefix `Changed:` and let the human re-bucket?
  Proposed: default `Changed:`, offer the guesser as a later enhancement.
- Do we want a `from-commits --strict` parity flag on backfill so that, with
  linting adopted, backfill can be told to *drop* `UNCLASSIFIED` commits rather
  than emit low-confidence `changed` entries? Likely yes; tracks with the
  lockstep invariant and would make backfill output strictly cleaner once
  messages are linted. (See `from-commits --strict`, which already does this for
  the seeding path.)

## Implementation status

### Phase 1 — core + hook — DONE (2026-06-06)

Implemented and covered by tests (`tests/test_basic/test_message_lint.py` and
`tests/test_hypothesis/test_message_lint_properties.py`). The full suite is now
green; a pre-existing, date-sensitive release snapshot time-bomb that surfaced
during this work was fixed separately (see "Snapshot determinism fix" below).

- **`changelogmanager/message_lint.py`** — the shared core. `LintOutcome`,
  `LintResult` (with `.ok`), `LintOptions`, and `classify_subject`. Reuses
  `backfill`'s parser registry and `change_types.TYPES_OF_CHANGE`; skip-type
  detection (`chore:`/`docs:`/…) runs regardless of selected schema; the
  `allow_unknown_conventional_types` knob escalates made-up `Word:` types to
  `UNCLASSIFIED`; exempt patterns (merge/revert/fixup/squash/bump) short-circuit
  to `SKIP`. `subject_of()` extracts the subject from a commit-msg file.
- **`changelogmanager/config.py`** — `get_message_lint_options(config)` reads
  `[validation.message_lint]`, validates the `schema` choice and compiles
  `exempt_patterns`, returning a resolved `LintOptions`. Bad schema/regex raise
  a handled `logging.Error`.
- **`changelogmanager/lint_message_cli.py`** + `[project.scripts]` entry
  `changelogmanager-lint-message` — fast-start linter for the `commit-msg`
  stage (does not import the full CLI/GUI graph). Exit codes 0/1/2; honors
  `--config`, `--error-format llvm|github`, and `--schema`.
- **`.pre-commit-hooks.yaml`** — `changelog-message-lint` hook at the
  `commit-msg` stage.
- **Lockstep property test** — asserts
  `classify_subject(...).outcome == UNCLASSIFIED ⇔ backfill.classify_commit_subject(...) is None`
  (modulo `SKIP` and `allow_unknown_conventional_types`), preventing drift
  between what the hook accepts and what backfill can use.

#### Refinement vs. the original behaviour table

The spec's behaviour table listed `Added: …` under the *explicit* `conventional`
schema as `UNCLASSIFIED`. In practice `added`/`fixed`/`removed`/… are themselves
keys in `CONVENTIONAL_TO_KAC`, so the Conventional parser maps `Added: …` to
`added` — a harmless, correct classification. The implementation and tests
reflect this; the table cell was over-strict.

### Phase 2 — audit (`lint-commits`) — DONE (2026-06-06)

Implemented and covered by `tests/test_basic/test_lint_commits.py` (11 tests,
including a real throwaway-repo integration test).

- **`message_lint.audit_commits()`** + `AuditReport` / `CommitLint` dataclasses
  — walks a commit range via `backfill.git_log_between`, guarded by
  `backfill.enforce_commit_budget` (same `--no-merges` + runaway-budget
  behaviour backfill uses), classifies each subject, and returns per-outcome
  counts, the unclassified subset, and a `to_json()` report shape.
- **`command_lint_commits` + `lint-commits` subparser** — flags `--since`,
  `--until`, `--all-history`, `--commit-schema`, `--show {fail,skip,pass,all}`,
  `--strict`, `--max-commits`. Default range mirrors `from-commits` (since the
  last tag). Human summary + offending-commit list; `--json` emits the machine
  report. `--strict` exits 1 when any non-exempt commit is unclassified (CI
  gate), emitting the JSON payload first on the `--json --strict` path.
- **Entry dispatch** — `lint-commits` is wired as a read-only branch in
  `cli/entry.py`: it never loads or touches the changelog (placeholder
  `<commits>` context), so it works in repos with no `CHANGELOG.md`.

### Phase 3 — rewrite plan core + LLM CLI (apply stubbed) — DONE (2026-06-06)

Implemented and covered by `tests/test_basic/test_rewrite_messages.py` (22 tests,
including a real repo + fake-remote test proving pushed commits are excluded).
Per the user's safety request, the command is **scoped to unpushed commits only**
and the **apply path is a deliberate fail-fast stub**.

- **`message_lint.resolve_unpushed_range()`** + `UnpushedRange` — bounds the range
  to `@{push}..HEAD` (then `@{upstream}..HEAD`), or `HEAD` for a branch with no
  upstream (all local-only). Pushed commits are provably excluded; errors cleanly
  outside a work tree.
- **`message_lint.plan_rewrite()`** + `RewritePlan`/`RewriteEntry`, plus
  `suggest_subject()`/`guess_category()` — audits the unpushed range, proposes a
  classifying subject per unclassified commit (keyword-guessed category or
  `--auto-prefix`), re-lints each suggestion (`outcome_after`), and renders a
  round-trippable TSV / JSON plan. **Touches no history.**
- **`command_rewrite_messages` + `rewrite-messages` subparser** — plan mode is the
  default (`--plan-out` / `--json`); `--commit-schema`, `--auto-prefix`,
  `--max-commits`. Intentionally **no `--since/--until/--force`** (range is fixed
  to unpushed). `--apply` enforces consent (`--yes` or interactive `input()`),
  then fails fast: missing consent in a non-TTY → exit 2 naming the flag; with
  consent → exit 1 "not yet implemented" pointing at `git commit --amend` /
  `git rebase -i`. Wired as a no-changelog-load branch in `cli/entry.py`.

#### Incidental fix

`tests/test_llvm_diagnostics/test_messages.py` had a latent ordering bug: those
tests render via the process-global diagnostics formatter and assumed Llvm, so any
prior `--error-format github` test could break them. Added an autouse fixture that
pins/restores the default formatter, making them order-independent.

### Snapshot determinism fix — DONE (2026-06-06)

`tests/test_snapshots/test_cli_snapshots.py::TestReleaseSnapshot::test_release_writes_file`
had been failing on every calendar day after its last regeneration. Root cause:
the `release` command stamps `datetime.now()` into the changelog
(`changelog.py:350` → `## [1.3.0] - <today>`), but the snapshot is a committed
static file and the snapshot normalisers did not mask the date, so the frozen
value (`2026-06-05`) only matched on that one day. It was the *only*
nondeterministic snapshot (every other date is a `2024-*` fixture value).

Fix (two independent layers, in `tests/test_snapshots/conftest.py`):

1. **Freeze time** — an autouse `freeze_time(FROZEN_TODAY)` fixture (using the
   already-present `freezegun` dev dep) pins `now()` for every snapshot test, so
   the released date is deterministic.
2. **Mask the frozen date** — `normalise_md`/`normalise_paths` replace the frozen
   value with a `<TODAY>` placeholder. This is defence-in-depth: the snapshot
   passes regardless of the specific frozen date (verified by temporarily setting
   it to `2099-12-31` — still green), while the static `2024-*` fixture dates stay
   unmasked so those snapshots still pin exact content.

The affected `.ambr` snapshot was regenerated once (one line:
`## [1.3.0] - 2026-06-05` → `## [1.3.0] - <TODAY>`).

### Phase 4 — not yet started

The GUI rewriter remains as specified above (and, like the CLI, its apply path
stays disabled until the full rewrite engine is built).
