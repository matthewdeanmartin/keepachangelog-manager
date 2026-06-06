# Online Backfill — Implementation Spec

Fills the gap between the CLI flags that already exist (`--source github-releases`,
`github-prs`, `pypi`) and the fast-fail that currently fires for anything not in
`{tags, commits, all}`.

---

## Background / Current State

| File                                     | What it does today                                                                                                                                                                                                                  |
|------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `changelogmanager/cli/parser.py:354–429` | Declares `--source` choices including `github-releases`, `github-prs`, `pypi`; `--repository`; `--package`. Marks them "reserved for future phases". `all` currently means local sources only. No `local` source choice exists yet. |
| `changelogmanager/services.py:390–414`   | `validate_backfill_options` rejects any source outside `{tags, commits, all}` with a hard error.                                                                                                                                    |
| `changelogmanager/backfill.py:741–785`   | `plan_backfill` dispatches only `tags`, `commits`, `all`; the `else` branch raises.                                                                                                                                                 |
| `changelogmanager/github.py`             | Has `GitHub` client with `get_releases()` (paginated), `get_pull_requests()`. Uses `urllib` + `orjson`. Token taken as constructor arg.                                                                                             |
| `changelogmanager/gitlab.py`             | Has `GitLab` client with `get_release()`. Same transport.                                                                                                                                                                           |
| `changelogmanager/cli/commands.py:851`   | `command_backfill` calls `services.plan_changelog_backfill` — no online path yet.                                                                                                                                                   |

The existing `GitHub` and `GitLab` clients are sync `urllib` wrappers. They already
handle pagination for releases. There is **no PyPI client** yet.

---

## `--source` choices — revised set

| Value             | Sources used                                  | Network? | Requires       |
|-------------------|-----------------------------------------------|----------|----------------|
| `tags`            | local git tags                                | no       | —              |
| `commits`         | local git commits                             | no       | —              |
| `local`           | tags + commits (old `all` behaviour)          | no       | —              |
| `github-releases` | GitHub Releases API                           | yes      | `--repository` |
| `github-prs`      | GitHub PRs API                                | yes      | `--repository` |
| `pypi`            | PyPI JSON API                                 | yes      | `--package`    |
| `all`             | tags + commits + github-releases + github-prs | yes      | `--repository` |

**Migration note:** `all` now implies network access when `--repository` is configured.
Users who want the old no-network `all` should switch to `--source local`. The parser
help text must document this clearly. `all` without `--repository` (and without a
`repository` key in config) falls back to `local` behaviour with a deprecation warning
so existing scripts don't silently break.

### Parser change

In `changelogmanager/cli/parser.py:360`, update `choices` to:

```python
choices = ["tags", "commits", "local", "github-releases", "github-prs", "pypi", "all"],
```

Update the `default` from `"all"` to `"local"` to keep existing installs safe.

### `plan_backfill` dispatch for `all`

```python
elif source == "all":
# local sources always run
releases, skipped = discover_commit_releases(...)
if repository:
    gh_releases, gh_skipped = discover_github_releases(repository, token, ...)
    gh_prs, pr_skipped = discover_github_prs(repository, token, ...)
    releases = _merge_releases(releases, gh_releases, gh_prs)
    skipped += gh_skipped + pr_skipped
sources = ["tags", "commits", "github-releases", "github-prs"]
```

`_merge_releases` deduplicates entries: same version + same section + same text →
keep one. Add this helper in `changelogmanager/backfill.py`.

---

## Credential Strategy

**Guiding principle:** a PAT must never live in a `.env` file that can be accidentally
committed. The resolution chain for each token is:

```
CLI flag  →  OS keyring  →  env var (CI/CD only, not recommended locally)  →  error
```

### Keyring integration

`keyring` is a **hard dependency** (not optional). It backs onto the OS native store
(macOS Keychain, Windows Credential Manager, libsecret on Linux). Lower friction is
more important than a lighter install.

```
service name  :  "keepachangelog-manager"
username key  :  "github_token"  |  "gitlab_token"
```

Add to `pyproject.toml` `[project.dependencies]`:

```toml
"keyring>=25.0,<27",
```

Helper in `changelogmanager/credentials.py` (new file):

```python
def get_token(service_key: str, cli_value: str | None, env_var: str) -> str | None:
    """Returns the first non-empty token from: CLI flag → keyring → env var."""
    if cli_value:
        return cli_value
    import keyring
    val = keyring.get_password("keepachangelog-manager", service_key)
    if val:
        return val
    return os.environ.get(env_var, "").strip() or None
```

New CLI verb `changelogmanager credentials set/clear/check` to drive
`keyring.set_password` / `keyring.delete_password` / `keyring.get_password`.
Defined in `changelogmanager/cli/parser.py` (new `credentials` subparser) and
`changelogmanager/cli/commands.py` (`command_credentials`).

### PyPI

PyPI's JSON API (`https://pypi.org/pypi/{package}/json`) is fully public — no token
needed. The PyPI simple API (`https://pypi.org/simple/{package}/`) is also public.

---

## Concurrency / Performance Model

The sources need **I/O concurrency** (network), not CPU parallelism.
`threading.Thread` + a `concurrent.futures.ThreadPoolExecutor` is the right fit:

- No new async runtime to manage (`asyncio` would require rewriting the whole CLI
  dispatch loop).
- `urllib` is thread-safe for independent requests.
- GitHub paginates releases at 100/page; a repo with 200 releases needs 2 HTTP
  round-trips — these can fire in parallel when multiple sources are active.
- The executor is **not** exposed publicly; it lives inside the online source
  fetch functions and is torn down before results are returned.

Rate-limit handling per source:

| Source                        | Rate limit               | Mitigation                                                                |
|-------------------------------|--------------------------|---------------------------------------------------------------------------|
| GitHub REST (authenticated)   | 5 000 req/hr             | Check `X-RateLimit-Remaining` header; back off / warn when < 10 remaining |
| GitHub REST (unauthenticated) | 60 req/hr                | Warn loudly; recommend token                                              |
| GitLab                        | 2 000 req/min (per-user) | Same header pattern (`RateLimit-Remaining`)                               |
| PyPI JSON                     | None documented          | Single request per package; no guard needed                               |

Add a `_check_rate_limit(headers: Mapping[str, str], source: str)` helper in
`changelogmanager/github.py` (and equivalent in `gitlab.py`) that logs a
`WARNING` when remaining < 10 and raises `logging.Error` when remaining == 0.

---

## Phase 1 — `github-releases` source

### What it produces

GitHub Releases → one changelog version entry per release. The release `tag_name`
becomes the version key. The release `body` (Markdown) is stored verbatim as a single
`changed` entry — no AI-assisted parsing. This gives users a useful starting point to
hand-edit rather than a structurally empty entry.

### New / changed files

| File                                   | Change                                                                                                                                                                                                            |
|----------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `changelogmanager/credentials.py`      | **New.** `get_token()` helper (see above).                                                                                                                                                                        |
| `changelogmanager/github.py`           | Add `get_releases_for_backfill()` that returns a list of `dict` already shaped like `{"version": str, "body": str, "date": str \| None}`. Re-use existing `get_releases()` pagination. Add `_check_rate_limit()`. |
| `changelogmanager/backfill.py`         | Add `discover_github_releases(repository, token, since, until, versioning_scheme)` → `tuple[list[Release], list[str]]` matching the signature of `discover_tag_releases`.                                         |
| `changelogmanager/services.py:390`     | Remove `github-releases` from the rejection set in `validate_backfill_options`. Add validation that `--repository` is provided (non-None, `owner/repo` format) when `source == "github-releases"`.                |
| `changelogmanager/backfill.py:764`     | Add `elif source == "github-releases":` branch in `plan_backfill`.                                                                                                                                                |
| `changelogmanager/cli/commands.py:851` | Pass `repository=args.repository` and token (resolved via `get_token`) down to `services.plan_changelog_backfill`.                                                                                                |
| `changelogmanager/cli/parser.py:368`   | Remove "reserved for future phases" note from `--repository` help text; update help string to say it is required for `github-releases`.                                                                           |

### Token resolution in `command_backfill`

```python
# changelogmanager/cli/commands.py  (inside command_backfill)
from changelogmanager.credentials import get_token

token = get_token(
    service_key="github_token",
    cli_value=getattr(args, "github_token", None),
    env_var="GITHUB_TOKEN",
)
```

The `--github-token` argument already exists on the `backfill` subparser
(`parser.py:364–373` area). Verify it is wired; if not, add it.

### Data flow

```
command_backfill
  → services.plan_changelog_backfill(source="github-releases", repository=…, token=…)
    → backfill.plan_backfill(source="github-releases", …)
      → backfill.discover_github_releases(repository, token, since, until, scheme)
        → GitHub(repository, token).get_releases_for_backfill()
        → filter by since/until
        → parse tag_name → Version
        → return list[Release], skipped_tags
```

### `Release` dataclass note

`discover_tag_releases` returns `(list[tuple[Version, Release]], list[str])` —
confirm the exact type in `backfill.py` and match the shape in the new function.
(Around `backfill.py:600–650` is where `Release` and the tag discovery helpers live.)

---

## Phase 2 — `github-prs` source

Fetch merged PRs targeting the default branch between `since` and `until`. Group by
date window to assign a version.

### Grouping strategy

PRs are grouped into versions by a **date-window** approach, not by tag proximity.
"Enclosing tag" grouping (find the tag released after a PR merged) fails when tags are
sparse or missing — exactly the scenario backfill is meant to fix.

Date-window algorithm:

1. Fetch all tags with their dates (via local git or the GitHub tags API).
2. Build a timeline: `[(tag_date, version), ...]` sorted ascending.
3. For each PR, assign it to the version whose tag date is the earliest date on or
   after the PR's `merged_at`. If no tag follows the PR (it merged after the last
   release), assign to `[Unreleased]`.
4. When no tags exist at all, fall back to calendar-month windows
   (`YYYY-MM` as a synthetic version string with a warning).

This is the same date-window logic whether or not a tag exists; the tag just anchors
the window boundary.

### Deduplication

Exact-duplicate entries (same section + same text) within a single version are
silently dropped. This covers the case where `all` combines local commits and
GitHub PRs and both sources produce the same description.

### New / changed files

| File                                         | Change                                                                                                                                                                                                                                                                  |
|----------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `changelogmanager/github.py`                 | Add `get_merged_prs(since_date, until_date)` — paginated, uses `GET /repos/{owner}/{repo}/pulls?state=closed&sort=updated&direction=desc`. Filter `merged_at` client-side. Add label-to-KAC-category mapping (same approach as `CONVENTIONAL_TO_KAC` in `backfill.py`). |
| `changelogmanager/backfill.py`               | Add `discover_github_prs(repository, token, since, until, versioning_scheme)`. Calls `get_merged_prs`, groups by date-window using `_assign_version_by_date`.                                                                                                           |
| `changelogmanager/backfill.py`               | Add `_assign_version_by_date(merged_at, tag_timeline)` helper.                                                                                                                                                                                                          |
| `changelogmanager/services.py`               | Allow `github-prs`; require `--repository`.                                                                                                                                                                                                                             |
| `changelogmanager/backfill.py:plan_backfill` | Add `elif source == "github-prs":` branch.                                                                                                                                                                                                                              |

### PR label → KAC category mapping

```python
GITHUB_LABEL_TO_KAC = {
    "bug": "fixed",
    "fix": "fixed",
    "enhancement": "added",
    "feature": "added",
    "breaking change": "changed",
    "deprecation": "deprecated",
    "security": "security",
    "removed": "removed",
}
```

Unmapped labels → `"changed"` (fallback). PR title is used as the entry text.

---

## Phase 3 — `pypi` source

Fetch all published versions of a package from the PyPI JSON API and synthesise
minimal changelog entries (version + release date only — no commit or PR text).
Useful for bootstrapping a changelog from a long PyPI history.

### New file

`changelogmanager/pypi.py`:

```python
import urllib.request, orjson

PYPI_API = "https://pypi.org/pypi/{package}/json"


def get_pypi_releases(package: str) -> list[dict]:
    """Returns list of {version, date} dicts sorted newest-first."""
    url = PYPI_API.format(package=package)
    with urllib.request.urlopen(url) as resp:  # nosec
        data = orjson.loads(resp.read())
    releases = []
    for version, files in data.get("releases", {}).items():
        if not files:
            continue
        upload_time = files[0].get("upload_time", "")[:10]
        releases.append({"version": version, "date": upload_time})
    return sorted(releases, key=lambda r: r["version"], reverse=True)
```

### New / changed files

| File                                         | Change                                                                                                                                                                                                                                       |
|----------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `changelogmanager/pypi.py`                   | **New.** `get_pypi_releases(package)`.                                                                                                                                                                                                       |
| `changelogmanager/backfill.py`               | Add `discover_pypi_releases(package, since, until, versioning_scheme)`. Calls `get_pypi_releases`, filters, returns `list[Release]`. Entries will be empty (no text) — just the version + date stub so the version appears in the changelog. |
| `changelogmanager/services.py`               | Allow `pypi`; require `--package`.                                                                                                                                                                                                           |
| `changelogmanager/backfill.py:plan_backfill` | Add `elif source == "pypi":` branch.                                                                                                                                                                                                         |
| `changelogmanager/cli/parser.py:372`         | Remove "reserved" note from `--package`.                                                                                                                                                                                                     |

---

## Phase 4 — `credentials` subcommand

A UX convenience so developers never have to remember `keyring` API calls.

```
changelogmanager credentials set github    # prompts for token, stores in keyring
changelogmanager credentials set gitlab    # same for GitLab
changelogmanager credentials clear github
changelogmanager credentials check         # prints which tokens are configured
```

### New / changed files

| File                               | Change                                                                                                                                                                        |
|------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `changelogmanager/cli/parser.py`   | Add `credentials` subparser with `{set, clear, check}` sub-subparsers and `{github, gitlab}` positional.                                                                      |
| `changelogmanager/cli/commands.py` | Add `command_credentials(args, ctx)`. Uses `getpass.getpass` for secret input, calls `keyring.set_password / delete_password / get_password`. Prints a human-readable status. |
| `changelogmanager/credentials.py`  | Add `set_token`, `clear_token`, `check_token` wrappers.                                                                                                                       |

---

## Error handling contract

All network errors must surface as `logging.Error` (same pattern as `github.py` and
`gitlab.py`) so the llvm-diagnostics formatter can render them consistently. Do not
let raw `urllib.error.HTTPError` or `urllib.error.URLError` escape to the top level.

Rate-limit exhaustion should print a clear actionable message:

```
Error: GitHub rate limit exhausted (0 requests remaining).
  Tip: pass --github-token or run `changelogmanager credentials set github` to get
  5 000 requests/hour instead of 60.
```

---

## Config file integration

The `[github]` and `[gitlab]` tables already exist in `config.py`
(`DEFAULT_CONFIG["project"]["github"]` etc.). Extend them to accept:

```toml
[tool.changelogmanager.github]
repository = "owner/repo"     # used as default for --repository

[tool.changelogmanager.gitlab]
project = "group/project"

[tool.changelogmanager.pypi]
package = "my-package"        # used as default for --package
```

`config.py` needs a `get_pypi_options` function analogous to `get_github_options`.
`UNWRAPPED_TABLES` (line 71) needs `"pypi"` added.
`DEFAULT_CONFIG` (line 40) needs `"pypi": {}` added.
`serialize_config_toml` (line 439) needs a `pypi` table serialization block.

These become fallback values in `command_backfill` so the user does not have to pass
`--repository` on every run if it is already in config.

---

## Testing requirements

- Unit tests must not make real network calls. Use `pytest-mock` to patch
  `GitHub.get_releases_for_backfill`, `get_pypi_releases`, etc.
- The `isolate_cwd` fixture in `tests/conftest.py` already protects against
  clobbering the repo's own `CHANGELOG.md` — new tests follow the same pattern.
- One integration-style smoke test per source (guarded by a
  `@pytest.mark.skipif(not os.environ.get("GITHUB_TOKEN"), reason="no token")`)
  in `tests/test_online_backfill.py`.
- Test that `validate_backfill_options` now accepts `github-releases`, `github-prs`,
  `pypi` and still rejects unknown strings.
- Test the `get_token` resolution order in `credentials.py`.

---

## Dependency additions

Add to `[project.dependencies]` in `pyproject.toml`:

```toml
"keyring>=25.0,<27",
```

`orjson` and `urllib` (stdlib) already present — no extra deps needed for PyPI or
GitHub fetching beyond `keyring`.

---

## Implementation order

1. `changelogmanager/credentials.py` — token resolution helper (no deps, easy to test)
2. Phase 1 (`github-releases`) — highest value, uses existing `GitHub` client
3. Phase 3 (`pypi`) — simplest network call, no auth
4. Phase 4 (`credentials` subcommand) — developer UX polish
5. Phase 2 (`github-prs`) — most complex grouping logic, build on phase 1

