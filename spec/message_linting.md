# Commit message linting design

Status: **Phases 1–2 implemented** · Owner: TBD · Last updated: 2026-06-06

> **Implementation progress.** Phase 1 (core + pre-commit hook) and Phase 2
> (the read-only `lint-commits` audit) are implemented and tested; see the
> "Implementation status" section at the end of this spec. Phases 3–4 remain
> proposed.

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

The dangerous one. Help maintainers fix historical subjects so backfill
classifies them. This rewrites commit hashes for every descendant commit — it is
the "successor to BFG" piece and must be treated with the same caution.

`rewrite-messages` is a **top-level CLI command**, designed for **LLM/agent
consumption**: deterministic flags, no interactive prompts on the LLM path, a
JSON-first contract, and a mapping file as the unit of work an agent can read,
edit, and re-feed. **Humans are expected to drive the rewriter from the GUI**
(Feature 4), not from the bare CLI. The CLI is therefore optimized for
scriptability; the safety ergonomics that a human needs (preview, per-commit
review, confirmation) live in the GUI on top of the same core.

### Tooling choice

Use **`git filter-repo`** (the modern, Git-project-recommended successor to
`git filter-branch` and the spiritual successor to BFG) via its
`--message-callback`. Do **not** shell out to `git filter-branch` (slow, footgun
defaults) and do **not** depend on `bfg` (Java, jar distribution, aimed at blob
removal not message edits).

`git filter-repo` is an external dependency. Treat it like `jiggle-version` for
`--bump-versions`: an **optional** extra. Detect it at runtime; if absent, fail
with an actionable install hint (`pip install git-filter-repo`) rather than a
traceback. Add a `rewrite` optional-dependency group / document the requirement.

### Command shape (LLM-facing CLI)

```sh
changelogmanager rewrite-messages [--since REF] [--until REF]
                                  [--commit-schema …]
                                  [--plan-out FILE]       # write mapping plan (default action)
                                  [--mapping FILE]        # apply this (edited) mapping
                                  [--auto-prefix changed] # bulk-prefix unclassified in the plan
                                  [--apply]               # actually rewrite history
                                  [--force]               # bypass dirty/unsafe-repo refusal
                                  [--yes]                 # skip the confirmation gate (non-TTY)
                                  [--json]                # machine-readable plan/result
```

Two complementary modes — the split is deliberate so an agent does the
**read → propose → (human-or-agent edits) → apply** loop with two discrete,
inspectable CLI calls:

1. **Plan mode (default; no history touched).** Runs the audit and, for each
   non-exempt `UNCLASSIFIED` commit, proposes a rewritten subject (prepend
   `Changed: `, or a keyword-guessed category). Writes a mapping plan to
   `--plan-out` (or stdout under `--json`). The record shape is stable and
   round-trippable:

   ```
   sha<TAB>old_subject<TAB>suggested_subject<TAB>outcome_after
   ```

   Under `--json`, the same as an array of objects plus the audit counts. This
   is the artifact an LLM reads, reasons over, and rewrites before applying.
   **No history is touched in this mode**, so it is always safe to run.
2. **Apply mode (`--apply --mapping FILE`).** Consumes a (possibly edited)
   mapping file and runs `git filter-repo --message-callback` to apply exactly
   those subject rewrites, leaving bodies untouched. Re-lints each rewritten
   subject *before* applying and refuses the whole batch if any proposed
   subject is still `UNCLASSIFIED` (fail-closed: never rewrite history into a
   state that is still wrong).

The two-call contract matters for agents: the plan is a checkpoint the LLM (or a
human in the GUI) can diff and approve, and apply is a separate, explicit,
auditable step. Never fold plan+apply into one call.

### Safety requirements (shared core)

History rewriting is irreversible from the tool's perspective, so the **core**
enforces — regardless of caller (CLI or GUI):

- **Apply is opt-in.** Without `--apply` the command only ever produces a plan.
  There is no "do everything" default.
- **Refuse on a dirty working tree** (uncommitted changes) and on a repo
  `git filter-repo` considers unsafe (not a fresh clone), mirroring its own
  `--force`-gated check. `--force` forwards that override; surface
  filter-repo's guidance rather than suppressing it.
- **Re-lint before write, fail-closed** as above.
- **Only edit subjects, never bodies**, and never touch merge commits.
- **`git filter-repo` is an optional dependency.** Plan mode must work without
  it (pure audit + suggestion). Apply mode detects it and fails with an install
  hint (`pip install git-filter-repo`) when missing — never a traceback.
- **Never run against a real repo in this project's own tests.** Per
  `CLAUDE.md`, the `isolate_cwd` fixture `chdir`s tests into temp dirs; rewrite
  tests must build a throwaway git repo in `tmp_path` and operate only there.
  Smoke scripts under `scripts/` must confine any rewrite to their `build/`
  temp dirs.

### CLI-specific (LLM) ergonomics

- **No interactive prompt on the CLI apply path.** The LLM path is
  non-interactive: apply requires `--apply` *and* (`--force` to clear the
  dirty/unsafe gate when applicable) *and* `--yes` to clear the
  confirmation gate. A bare `--apply` in a non-TTY without `--yes` is a usage
  error (exit 2) that prints exactly which flags are missing — so an agent gets
  a deterministic, recoverable failure rather than a hang.
- **Print/emit the blast radius** in both plan and apply output: number of
  commits whose hash will change, plus the standard "this rewrites shared
  history; collaborators must re-clone or force-pull" warning. Under `--json`
  this is a `blast_radius` field, not prose, so an agent can gate on it.
- The human confirmation experience (preview, per-commit review, "type the
  branch name to confirm") is **not** in the CLI; it is the GUI's job
  (Feature 4). The CLI's confirmation is the single `--yes` flag.

### Why not just amend?

For the most-recent commit, `git commit --amend` is simpler and the docs should
recommend it. `rewrite-messages` exists for *bulk* historical cleanup where
amend/`rebase -i` across hundreds of commits is impractical — which is precisely
the BFG-style use case.

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

### Screen shape

Add `gui/screens/rewrite.py` (`RewriteMessagesScreen(Screen)`, registered in
`app.SCREEN_CLASSES` and the Screens menu) following the existing `Screen`
contract (`build_body`, left `CommandList`, shared `app_state`). Layout:

- **Range controls** — Since / Until / "all history" / commit-schema combo,
  reusing the same widgets as `BackfillScreen` (factor the `combo` helper into
  `gui/widgets.py` so both screens share it).
- **Scan** button → runs **plan mode** of the core (read-only) and populates a
  table.
- **Plan table** — one row per non-exempt `UNCLASSIFIED` commit: short sha,
  old subject, and an **editable** "new subject" cell (default = the core's
  suggestion). The human fixes each line in place; live re-lint colors the row
  green (now `CHANGELOG`/`SKIP`) or red (still `UNCLASSIFIED`). The Apply button
  stays disabled while any row is red — the GUI enforces the same fail-closed
  rule the CLI does, but visibly.
- **Apply** button → the destructive step, gated by an explicit confirmation
  dialog described below. Disabled entirely when `git filter-repo` is not
  installed, with an inline "install git-filter-repo to enable" note (parallel
  to how `--bump-versions` surfaces the missing `jiggle-version`).

### Human confirmation gate (GUI only)

Before applying, the GUI must show a modal that:

- States the **blast radius** (N commits will get new hashes) and the
  shared-history warning verbatim.
- Refuses if the working tree is dirty (reuse the core's dirty-tree check) and
  explains how to clean it, rather than letting filter-repo error mid-run.
- Requires a deliberate confirmation stronger than a single OK — e.g. typing the
  current branch name (the analog of the CLI's `--yes`, but human-proofed). This
  is the GUI counterpart to the CLI's `--force`/`--yes` flags and is where the
  "are you sure" weight lives.

After a successful apply the screen calls `controller.reload()` so downstream
screens see the rewritten state, and shows the new HEAD plus a reminder that a
force-push / re-clone is now required.

### Respecting GUI dry-run

The shared top-panel **Dry run** checkbox (`app_state.dry_run`) maps to "plan
only, never apply": when set, the Apply button is replaced by a "Preview apply
(dry run)" that runs filter-repo's own dry-run / prints the planned callback
without writing, so a cautious user can exercise the whole flow harmlessly.

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
| `rewrite-messages` (top-level CLI) | **LLMs / agents** | plan→apply history rewrite, JSON contract, no prompts |
| Rewrite Messages GUI screen | **humans** | review-and-confirm rewrite over the same core |

## Phasing

1. **Phase 1 — core + hook.** `message_lint.py`, config reader,
   `changelogmanager-lint-message` entry point, `.pre-commit-hooks.yaml`,
   property test for the lockstep invariant. Highest value, lowest risk.
2. **Phase 2 — audit.** `lint-commits` command (read-only) reusing the git
   walk; JSON output for CI gating.
3. **Phase 3 — rewrite core + LLM CLI.** Shared plan/apply core; top-level
   `rewrite-messages` command with the LLM-facing plan-mode default and
   `--apply` mode behind `git filter-repo`. Optional dependency, fail-closed
   re-lint, isolated tests only.
4. **Phase 4 — GUI rewriter.** `RewriteMessagesScreen` on top of the Phase 3
   core: editable plan table, live re-lint, human confirmation gate. This is the
   primary human entry point; ships after the core it depends on.

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
`tests/test_hypothesis/test_message_lint_properties.py`; full suite green apart
from one pre-existing, date-sensitive release snapshot unrelated to this work).

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

### Phases 3–4 — not yet started

`rewrite-messages` (LLM CLI) and the GUI rewriter remain as specified above.
