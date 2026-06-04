# Config redesign: kill YAML, lean on TOML, make config earn its keep

This spec proposes a redesign of `changelogmanager`'s configuration system. The
goals, in priority order:

1. **Remove the `pyyaml` dependency entirely** — from both config storage and the
   `to-yaml` export.
1. **Store config in TOML** — `[tool.changelogmanager]` in `pyproject.toml`, or a
   standalone `changelogmanager.toml` for non-Python repos.
1. **Make config pull its weight** — delete dead knobs, and move genuinely useful,
   repeated CLI flags into config so the common workflows stop needing long switch
   clusters.
1. **Clarify the component model** and add real commit→component routing (the
   feature that was advertised as `component-is-substring` but never implemented).

Decisions already locked in (from review):

- **Drop config YAML _and_ the `to-yaml` export command.** `to-json` and `to-html`
  stay. `pyyaml` is removed from `dependencies`.
- **Config lives in `pyproject.toml` _or_ a standalone `changelogmanager.toml`.**
- **Components stay flat (no nesting), but commit→component routing gets designed and
  implemented.**

______________________________________________________________________

## 1. Current state (what we're replacing)

### 1.1 Where YAML is used today

`pyyaml` is a hard runtime dependency (`pyproject.toml` line 12). It is used in
**three** places, which are easy to conflate:

| Use | Location | Fate |
|--------------------|-------------------------------------------|-------------------------------|
| Config **load** | `config.py` `load_yaml` | **Removed** (TOML only) |
| Config **write** | `config.py` `write_yaml` | **Removed** (TOML only) |
| Config **display** | `cli.py:392` (`command_config` dumps YAML) | **Replaced** with TOML output |
| `to-yaml` export | `changelog.py` `to_yaml`/`write_to_yaml` | **Deleted** (command removed) |

TOML reading already exists (`load_pyproject` via `tomllib`/`tomli`); TOML writing
already exists as a hand-rolled string emitter (`serialize_pyproject_section` +
`replace_pyproject_section`). So pyproject support is real today — it is YAML that is
redundant.

### 1.2 What config currently controls — and what's dead

Live, actually-read keys:

| Key | Read by | Status |
|-------------------------------------------|---------------------------------------------------------------|--------|
| `project.components[]` (`name`, `changelog`) | `get_component_from_config`, `get_components_from_config` | Live |
| `project.validation.enforce_preamble` | `get_validation_options` → reader preamble enforcement | Live |
| `project.validation.format` / `formatter` / `mdformat_options` | `get_format_options` → `resolve_formatter` | Live |
| `project.versioning.scheme` | `get_versioning_scheme` → reader + preamble keywords | Live |

Dead / vestigial keys (stored, prompted, written — but **never read to change
behavior**):

| Key | Evidence |
|--------------------------------|--------------------------------------------------------------------------|
| `project.commits.style` | `get_commit_style` has **zero source callers** (only stale `.pyc`). |
| `component-is-substring` value | Appears only as a label in `config.py` and one line in `docs/workflows.md`; no consuming code. |

`from-commits` and `backfill` use a **separate `--commit-schema` CLI flag**
(`auto`/`conventional`/`gitmoji`/`keepachangelog`) instead of `commits.style`. So the
entire `commits` config block is currently theater.

### 1.3 The "config isn't paying for itself" problem

Many flags are typed on **every** invocation and would be natural config defaults:

- `--error-format {llvm,github}` — a per-repo/per-CI constant, retyped every call.
- `--schema-version` for `to-json` — a contract you pin once.
- `--commit-schema` for `from-commits`/`backfill` — a per-repo constant.
- `github-release` / `github-pr` `--repository`; `gitlab-release` `--project` and
  `--gitlab-url` — fixed per repo.
- `release --bump-versions` / `--pyproject-only` — a per-project policy.
- `--format` / `--no-format` — a per-project policy.

Today none of these can be defaulted from config, so CI invocations and local muscle
memory carry long flag tails. That is the concrete sense in which config "isn't paying
for itself": it stores things nobody reads (`commits.style`) and fails to store the
things everybody retypes.

______________________________________________________________________

## 2. Target config format (TOML)

### 2.1 Discovery order

`auto_detect_config()` is updated to search, in order:

1. `changelogmanager.toml` (cwd)
1. `.changelogmanager.toml` (cwd)
1. `pyproject.toml` — only if it contains a `[tool.changelogmanager]` table.

The four YAML candidates (`.changelogmanager.yml/.yaml`, `changelogmanager.yml/.yaml`)
are **dropped**. `--config <path>` still forces an explicit file; a `.toml` suffix (or
the name `pyproject.toml`) selects the TOML reader.

> Migration aid: if an old YAML config is found and no TOML config exists, emit a single
> `logging.Warning` pointing at `changelogmanager config migrate` (see §6). We do **not**
> silently read YAML — the dependency is gone.

### 2.2 Schema (standalone `changelogmanager.toml`)

```toml
# changelogmanager.toml  (or the same keys under [tool.changelogmanager] in pyproject.toml)

[versioning]
scheme = "semver"          # semver | pep440 | calver

[validation]
enforce_preamble = false
format = "auto"            # auto | true | false
# formatter = "mdformat"   # reserved; only mdformat supported
# [validation.mdformat_options]  # passed through to mdformat

[defaults]                 # NEW: defaults for repeated CLI flags (see §4)
error_format = "llvm"      # llvm | github
commit_schema = "auto"     # auto | conventional | gitmoji | keepachangelog
schema_version = "current" # to-json export schema
bump_versions = false      # release: bump pyproject/source versions
pyproject_only = false

[github]                   # NEW: per-repo remote defaults (token still via env/flag)
repository = "owner/repo"

[gitlab]                   # NEW
project = "group/project"
url = "https://gitlab.com"

[[components]]
name = "default"
changelog = "CHANGELOG.md"
# match = ["**"]           # NEW: commit→component routing globs (see §5)
```

The same content under `pyproject.toml` is the table-prefixed form:

```toml
[tool.changelogmanager.versioning]
scheme = "semver"

[tool.changelogmanager.validation]
enforce_preamble = false

[tool.changelogmanager.defaults]
error_format = "github"

[[tool.changelogmanager.components]]
name = "api"
changelog = "api/CHANGELOG.md"
match = ["api/**"]
```

### 2.3 Schema changes vs. today

- **Drop** the top-level `project` wrapper. Today everything is under
  `project.*`; the wrapper adds nothing. New top-level tables are `versioning`,
  `validation`, `defaults`, `github`, `gitlab`, and `[[components]]`.
  - (Back-compat reader: accept a `project` table if present and flatten it, so a
    machine-translated old config still loads. New writes never emit `project`.)
- **Delete** `commits.style` and the `component-is-substring` label. Dead today.
- **Add** `[defaults]`, `[github]`, `[gitlab]`, and per-component `match`.

______________________________________________________________________

## 3. Removing pyyaml

### 3.1 Config layer

- Delete `load_yaml`, `write_yaml`, and the YAML branch in `load_configuration` /
  `write_configuration`. `config_format_from_path` collapses to "is this pyproject.toml
  vs a standalone toml" — both go through the TOML path.
- `command_config` (display) renders the effective config **as TOML** instead of
  `yaml.safe_dump`. Reuse `serialize_pyproject_section`-style emission (strip the
  `[tool.changelogmanager]` prefix for standalone display) or render via a tiny emitter.
- Reading stays on `tomllib` (3.11+) / `tomli` (already a conditional dep). Writing
  stays hand-rolled (no new toml-writer dependency); the existing
  `serialize_pyproject_section` is generalized to emit the new schema and a standalone
  variant (no `tool.changelogmanager` prefix).

### 3.2 Export layer

- **Remove the `to-yaml` command** end-to-end: `command_to_yaml`, the `to-yaml`
  subparser, `Changelog.to_yaml` / `write_to_yaml`, and the `import yaml` in
  `changelog.py`. Update `SKILL.md`, README, and docs that mention `to-yaml`.
- `to-json` and `to-html` are untouched.

### 3.3 Dependency + tooling

- Remove `pyyaml>=6.0.2,<7` from `dependencies`.
- Remove `types-PyYAML` from the `lint` group.
- Grep the test suite for YAML fixtures/config and convert them to TOML (see §7).

> After this, `import yaml` should appear **nowhere** in `changelogmanager/`. A CI grep
> guard (`! grep -rn "import yaml" changelogmanager/`) is cheap insurance.

______________________________________________________________________

## 4. Making config pay for itself: `[defaults]`, `[github]`, `[gitlab]`

Introduce a single precedence rule, applied uniformly:

> **explicit CLI flag > environment variable (where one exists) > config value >
> built-in default.**

Mechanism: after parsing args and resolving config, a small `apply_config_defaults(args, config)` step fills any arg still at its built-in default with the config value. Tokens
remain **flag-or-env only** — never stored in config — for safety.

Flags that become config-backed:

| Flag | Config key | Notes |
|-------------------------------------|-----------------------------|-----------------------------------------|
| `-f/--error-format` | `defaults.error_format` | Global; today retyped every call. |
| `--commit-schema` | `defaults.commit_schema` | `from-commits`, `backfill`. |
| `--schema-version` (to-json) | `defaults.schema_version` | |
| `release --bump-versions` | `defaults.bump_versions` | Policy per project. |
| `release --pyproject-only` | `defaults.pyproject_only` | |
| `validate --format` / `--no-format` | `validation.format` | Already config-backed; document it. |
| `github-release/-pr --repository` | `github.repository` | Token stays flag/`GITHUB_TOKEN`. |
| `gitlab-release --project`/`--gitlab-url` | `gitlab.project`/`gitlab.url` | Token stays flag/`GITLAB_TOKEN`/`CI_JOB_TOKEN`. |

This is the core of "config earning its keep": the things people retype become
write-once, while the dead `commits.style` knob is removed.

______________________________________________________________________

## 5. Components and "subcomponents"

### 5.1 Is config the only place to talk about subcomponents? — yes, today

A "component" today is **only** a config concept: a `{name, changelog}` pair in
`project.components[]`. There is:

- **no nested subcomponent** model anywhere in the code,
- **no CLI** for components beyond `--component <name>` selecting one entry,
- **no commit routing** — the `component-is-substring` style is advertised but unused.

`--component` simply picks which changelog file a command operates on.
`validate --all` is the only fan-out: it loops over every configured component. So if
you have not used components yet, the mental model is: *"components = a flat list of
independently-versioned changelog files in one repo (monorepo packages),"* nothing more.

### 5.2 Decision: stay flat, add real routing

We **keep components flat** (no nesting) and instead implement the missing capability:
**commit→component routing**, so `from-commits` and `backfill` can fan a single git
history out across multiple components.

Add an optional `match` field per component:

```toml
[[components]]
name = "api"
changelog = "api/CHANGELOG.md"
match = ["api/**", "shared/api/**"]   # path globs

[[components]]
name = "web"
changelog = "web/CHANGELOG.md"
match = ["web/**"]

[[components]]
name = "default"
changelog = "CHANGELOG.md"
# no match → catch-all / fallback
```

Routing semantics:

- A commit is attributed to a component if **any file it touches** matches that
  component's `match` globs (via `git log --name-only`). A commit may land in multiple
  components if it spans them.
- A component with **no `match`** is the fallback for commits that match nothing.
  Exactly zero or one fallback is allowed (error if two unmatched-catchall components
  exist and there are unrouted commits).
- Substring matching (the original `component-is-substring` intent) is expressible as a
  glob (`["*name*"]`); we do not add a second matching mode.

New behavior:

- `from-commits --all` / `backfill --all` (mirroring `validate --all`): iterate
  components, route classified commits per `match`, and write each component's
  changelog. Without `--all`, behavior is unchanged (single `--component`).
- Routing only affects commit-derived flows; `add`/`remove`/`edit`/`release` remain
  single-component operations selected by `--component`.

### 5.3 Explicitly out of scope (documented as future)

- Nested subcomponents (component → child components with their own changelogs).
- Cross-component release coordination / version locking.
- Per-component versioning schemes (today scheme is global). Could become
  `components[].versioning.scheme` later; not now.

______________________________________________________________________

## 6. CLI surface changes

- `config` — display effective config as **TOML**.
- `config init` — interactive prompts updated:
  - **Remove** the commit-style prompt (dead).
  - Keep: config target (pyproject vs `changelogmanager.toml`), versioning scheme,
    preamble enforcement, default component name + changelog path.
  - Optionally add: `error_format` default prompt.
  - Writes TOML only.
- `config migrate` (**new**, optional but recommended) — one-shot: read a legacy YAML
  config (using a vendored micro-parser or a clearly-scoped temporary import behind a
  helpful error if pyyaml isn't present), translate to the new TOML schema, write
  `changelogmanager.toml` (or the pyproject table), and print a diff/summary. This keeps
  the "yaml is gone from runtime" promise while giving existing users an escape hatch.
  - If we want **zero** YAML code at all, `config migrate` instead prints the mapping
    instructions and refuses to parse — pick one in implementation (recommend the
    vendored micro-parser limited to the small known config shape).
- `to-yaml` — **removed**.
- `from-commits` / `backfill` — gain `--all` for component routing (§5.2).

______________________________________________________________________

## 7. Migration & testing

- Convert this repo's own usage: there is currently **no** `[tool.changelogmanager]`
  table in `pyproject.toml`; add one as the dogfood example (and as a routing example if
  we want to demo components).
- Tests:
  - Replace YAML config fixtures in `tests/test_basic/test_change_types_and_config.py`
    and `test_cli.py` with TOML equivalents.
  - Drop/replace `to-yaml` tests; assert the subcommand no longer exists.
  - Add precedence tests for `apply_config_defaults` (flag > env > config > default).
  - Add routing tests: commits touching `api/**` vs `web/**` land in the right
    component; unmatched commits hit the fallback; spanning commits land in both.
  - CI grep guard: no `import yaml` under `changelogmanager/`.
- Docs: update `docs/workflows.md` (the YAML multi-component example and the
  `component-is-substring` reference), README, and `SKILL.md`.

______________________________________________________________________

## 8. Suggested implementation order

1. **TOML-only config core**: drop YAML load/write, update discovery, generalize the
   TOML emitter for the new (unwrapped) schema, render `config` display as TOML. Keep
   reading the old `project.*` shape for back-compat.
1. **Remove `to-yaml`** and the `pyyaml` / `types-PyYAML` deps; add the CI grep guard.
1. **`[defaults]`/`[github]`/`[gitlab]` + `apply_config_defaults`** with the
   flag > env > config > default precedence; delete `commits.style` /
   `get_commit_style`.
1. **Component routing**: `match` globs, `from-commits --all` / `backfill --all`.
1. **`config migrate`** + docs/tests cleanup.

Linting, mypy, and the GUI are intentionally left to separate passes (the GUI still
builds argv and will need the new `--config` discovery, but no behavior here depends on
touching it).

______________________________________________________________________

## DONE

Implemented per the locked decisions. Existing test suite is green (**474 passed**);
additional tests are being added by another bot. Linting/mypy and the GUI were left to
separate passes as agreed.

### TOML-only config core — DONE

- `config.py`: removed `import yaml`, `load_yaml`, `write_yaml`. `load_configuration`
  is TOML-only (`read_toml` shared by `load_toml` for standalone files and
  `load_pyproject` for the pyproject table).
- Discovery (`CONFIG_FILE_CANDIDATES`) is now `changelogmanager.toml`,
  `.changelogmanager.toml`, then `pyproject.toml` (only with a `[tool.changelogmanager]`
  table). The four YAML candidates are gone.
- On-disk schema is **unwrapped** (top-level `versioning`/`validation`/`defaults`/
  `github`/`gitlab`/`[[components]]`). `wrap_unwrapped_schema` maps it into the internal
  `project.*` namespace so every existing reader is unchanged. A legacy `project` table
  is still accepted (back-compat), with the dead `commits` table dropped on read.
- `serialize_config_toml(config, prefix=...)` emits both the standalone file and the
  `[tool.changelogmanager.*]` pyproject section (round-trip verified for both). `config`
  display now renders TOML.

### Remove to-yaml + pyyaml — DONE

- Deleted the `to-yaml` command, its subparser, and `Changelog.to_yaml` /
  `write_to_yaml`. `to-json` and `to-html` untouched.
- Removed `pyyaml` from `dependencies` and `types-PyYAML` from the lint group. No
  `import yaml` remains anywhere in `changelogmanager/` (grep-clean).

### [defaults]/[github]/[gitlab] + precedence — DONE

- New accessors `get_defaults_options`/`get_github_options`/`get_gitlab_options`.
- `apply_config_defaults(args, config)` in `main()` fills any flag still at its built-in
  default from config, giving **flag > env > config > built-in default**. Applied before
  `configure_logging` so `--error-format` can be config-driven. Verified: a config
  `defaults.error_format = "github"` switches diagnostic format with no `-f` flag, and an
  explicit flag still wins over config.
- Config-backed flags: `error_format`, `commit_schema`, `schema_version`,
  `bump_versions`, `pyproject_only`, github `repository`, gitlab `project`/`url`. Tokens
  remain flag/env only.
- Deleted the dead `commits.style` knob, `get_commit_style`, `COMMIT_STYLE_LABELS`, and
  the `component-is-substring` label; removed the commit-style prompt from `config init`.

### Component routing (match globs + --all) — DONE

- New `commit_routing.py`: `git_log_with_files` (parses `git log --name-only` with a
  record separator), `file_matches` (glob match with `**` recursion), `route_commit`
  (files → component names; match-less component is the fallback), and
  `validate_routing_components` (≤1 fallback).
- `from-commits --all` routes each commit to every component whose `match` globs hit a
  touched file and seeds each component's `[Unreleased]`; spanning commits land in
  multiple components; unmatched commits hit the fallback. Verified end-to-end in a temp
  git repo. Per-component `match = [...]` globs round-trip through the TOML serializer.
- Note: `backfill --all` was **not** overloaded for routing — its `--all` already means
  the tags+commits *source* set. Component-routed backfill is a clean follow-up rather
  than a breaking reinterpretation of an existing flag.

### Docs

- Updated the bundled `SKILL.md` (TOML config, no `to-yaml`). The broader `docs/` and
  `README.md` still reference YAML/`to-yaml` in prose and are left for a docs pass (not
  test-affecting).
