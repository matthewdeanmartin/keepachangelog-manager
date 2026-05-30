# CI and GitHub Actions

## What the draft release GitHub Action does

The repository's `Create Draft Release` workflow lives at `.github/workflows/create_draft_release.yml`.

It runs on every push to `main`, installs the project with `uv`, and then runs:

```sh
uv run changelogmanager github-release \
  --github-token "${{ github.token }}" \
  --repository "${{ github.repository }}"
```

Because `github-release` defaults to `--draft`, the workflow:

1. Deletes any existing draft releases in the repository.
1. Reads the current `[Unreleased]` section from `CHANGELOG.md`.
1. Infers the next SemVer version from the unreleased change types.
1. Creates a fresh draft GitHub release tagged like `v1.2.3`.
1. Uses the `[Unreleased]` entries as the release notes body, grouped by change type.

This workflow does **not** rewrite `CHANGELOG.md`. It only updates the GitHub draft release.

## What the `github-release` command does

`changelogmanager github-release` turns the current `[Unreleased]` section into a GitHub release payload.

```sh
changelogmanager github-release --repository owner/repo
```

By default it creates a **draft** release. With `--release`, it publishes the release immediately instead of leaving it in draft state.

Behavior summary:

1. Reads the GitHub token from `--github-token` or `GITHUB_TOKEN`.
1. Validates that `[Unreleased]` exists and can produce a future version.
1. Deletes all existing draft releases for the target repository.
1. Creates a new GitHub release named `Release vX.Y.Z`.
1. Generates release notes from `[Unreleased]` using the changelog categories and emoji headings.

Use `release` when you want to promote `[Unreleased]` inside `CHANGELOG.md`. Use `github-release` when you want to create or publish the corresponding GitHub release entry.

If `[Unreleased]` has no entries (for example, the first push after a release landed), `github-release` prints a clear skip notice and exits `0`. The CI step shows as a clean success that did nothing, instead of either a confusing silent success or a red failure.

## GitLab: create a release

`changelogmanager gitlab-release` turns the current `[Unreleased]` section into a GitLab release. GitLab has no "draft release" concept, so the command is idempotent: it **updates** the release if one already exists for the computed tag (`PUT`), otherwise it **creates** it (`POST`), letting GitLab create the tag from `--ref` when needed.

```sh
changelogmanager gitlab-release --project group/repo
```

`--project` accepts a numeric project ID or a URL path like `group/subgroup/project`. For self-hosted instances pass `--gitlab-url` (defaults to `https://gitlab.com`). Like `github-release`, it skips cleanly with exit `0` when there are no `[Unreleased]` entries.

### Authentication and the `CI_JOB_TOKEN` caveat

The token is read from `--gitlab-token`, then `GITLAB_TOKEN`, then `CI_JOB_TOKEN`.

**Heads up:** the default `CI_JOB_TOKEN` is intentionally restricted and typically **cannot** create releases — the Releases API answers with `401 Unauthorized` or `403 Forbidden`. If you hit that, supply a token with the `api` scope instead:

- a [Project access token](https://docs.gitlab.com/ee/user/project/settings/project_access_tokens.html), or
- a [Group access token](https://docs.gitlab.com/ee/user/group/settings/group_access_tokens.html), or
- a [Personal access token](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html).

Expose it as a masked CI/CD variable named `GITLAB_TOKEN`. See GitLab's [CI/CD job token docs](https://docs.gitlab.com/ee/ci/jobs/ci_job_token.html) for why `CI_JOB_TOKEN` differs.

### Example `.gitlab-ci.yml`

```yaml
release:
  image: python:3.13
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
  before_script:
    - pip install uv && uv sync --frozen
  script:
    - >
      uv run changelogmanager gitlab-release
      --project "$CI_PROJECT_ID"
      --gitlab-url "$CI_SERVER_URL"
      --ref "$CI_COMMIT_SHA"
  variables:
    # CI_JOB_TOKEN usually cannot create releases; use a project/group token.
    GITLAB_TOKEN: $RELEASE_TOKEN
```

## Using the tool as a quality gate in GitHub Actions

The simplest quality gate is to fail CI when the changelog is malformed:

```yaml
name: Changelog quality gate

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  changelog:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v6
        with:
          persist-credentials: false

      - uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - uses: astral-sh/setup-uv@v8
        with:
          enable-cache: true

      - name: Sync dependencies
        run: uv sync --frozen

      - name: Validate changelog
        run: uv run changelogmanager --error-format github validate
```

Why this works well as a gate:

- `validate` exits with code `1` on errors, so the workflow fails automatically.
- `--error-format github` emits GitHub Actions annotations, so errors show inline in the PR UI.
- The command is read-only unless you add `--fix`.

### Multi-component repositories

If you use a config file with multiple changelogs, validate all configured components:

```yaml
- name: Validate configured changelogs
  run: uv run changelogmanager --config .changelogmanager.yml --error-format github validate --all
```

If you only want to gate files that changed in the current checkout:

```yaml
- name: Validate changed changelogs only
  run: uv run changelogmanager --config .changelogmanager.yml --error-format github validate --all --changed-only
```

## Typical release automation

This repository uses an **opinionated** release workflow built around three jobs that run
in strict sequence: **bump → build → publish**.

### Why this order matters

`pyproject.toml` contains a static `version = "x.y.z"` string that `uv build` reads
directly. If a build runs before that string is updated, the wheel ends up carrying the
*previous* version number and PyPI gets the wrong release. The bump job runs first so
every subsequent step sees the correct version.

### Triggering a release

1. Merge unreleased changelog entries to `main`.
1. Let `.github/workflows/create_draft_release.yml` keep the GitHub draft release in sync
   from `[Unreleased]`.
1. Open the repository's **Releases** page in GitHub and open the current draft.
1. Review the title, notes, and target branch, then click **Publish release**.

Publishing fires the `release` event, which starts `.github/workflows/release.yml`
automatically.

### What the three jobs do

**`bump`** (runs first)

Checks out the release's target branch (not the tag), installs the `[jiggle]` extra, and
calls:

```sh
uv run changelogmanager release \
  --override-version "$VERSION" \
  --bump-versions \
  --yes
```

This promotes `[Unreleased]` in `CHANGELOG.md` and writes the same version into
`pyproject.toml` (and any `__version__` strings in the source tree) atomically. The
changed files are committed to a new branch named `release/bump-<release-id>`, pushed,
and a pull request is opened targeting `target_commitish`.

The branch name is passed to the `build` job as an output.

**`build`** (runs after `bump`)

Checks out the **bump branch** — not the tag — so `pyproject.toml` already carries the
correct version. Runs `uv build --no-sources` and verifies the wheel filename contains
the expected version string before uploading the dist artifact.

**`publish`** (runs after `build`)

Downloads the dist artifact and pushes to PyPI using OIDC (`id-token: write`). No API
tokens are stored in the repository.

### Failure recovery

| Job that fails | State of the world | Recovery |
|---|---|---|
| `bump` | Nothing built, nothing published, no PR. | Fix the issue and re-publish the GitHub Release. |
| `build` | PR branch exists. Nothing published. | Close the PR, delete the GitHub Release, fix the build, re-publish. |
| `publish` | PR branch + dist artifact exist. Nothing on PyPI. | **Option A:** re-run just the `publish` job from the GitHub Actions UI. **Option B:** close the PR, delete the release, fix the issue, re-publish. |

A publish failure is the trickiest case because the PR branch is already open with the
correct committed version. If you choose Option B (full restart), also reset `pyproject.toml`
back to its pre-bump version on `main` before re-publishing, or the bump step will find
nothing to commit.

### Why this workflow is opinionated

- It separates **draft release generation** (continuous, on every push to `main`) from
  **package publishing** (one-shot, triggered by a human clicking Publish).
- It uses GitHub's release UI as the approval step instead of requiring developers to push
  tags from a laptop.
- The PR is the audit trail: you can see exactly what CHANGELOG.md and pyproject.toml
  looked like at publish time, and merging it keeps `main` up to date.
- It uses the PyPI OIDC pattern via `pypa/gh-action-pypi-publish` with `id-token: write`,
  not a Twine upload step or a long-lived PyPI API token stored in the repository.
