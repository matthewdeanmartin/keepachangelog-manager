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
2. Reads the current `[Unreleased]` section from `CHANGELOG.md`.
3. Infers the next SemVer version from the unreleased change types.
4. Creates a fresh draft GitHub release tagged like `v1.2.3`.
5. Uses the `[Unreleased]` entries as the release notes body, grouped by change type.

This workflow does **not** rewrite `CHANGELOG.md`. It only updates the GitHub draft release.

## What the `github-release` command does

`changelogmanager github-release` turns the current `[Unreleased]` section into a GitHub release payload.

```sh
changelogmanager github-release --repository owner/repo
```

By default it creates a **draft** release. With `--release`, it publishes the release immediately instead of leaving it in draft state.

Behavior summary:

1. Reads the GitHub token from `--github-token` or `GITHUB_TOKEN`.
2. Validates that `[Unreleased]` exists and can produce a future version.
3. Deletes all existing draft releases for the target repository.
4. Creates a new GitHub release named `Release vX.Y.Z`.
5. Generates release notes from `[Unreleased]` using the changelog categories and emoji headings.

Use `release` when you want to promote `[Unreleased]` inside `CHANGELOG.md`. Use `github-release` when you want to create or publish the corresponding GitHub release entry.

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

This repository currently uses an **opinionated** release workflow.

1. Merge unreleased changelog entries to `main`.
2. Let `.github/workflows/create_draft_release.yml` keep the GitHub draft release in sync from `[Unreleased]`.
3. Open the repository's **Releases** page in GitHub.
4. Open the draft release that was generated from `[Unreleased]`.
5. Review the title, notes, and target branch, then click **Publish release**.
6. Publishing the GitHub Release fires `.github/workflows/release.yml`.
7. That workflow builds from the published release tag, publishes to PyPI with GitHub OIDC, and opens a PR that updates `CHANGELOG.md` on the release target branch.

### Why this workflow is opinionated

- It separates **draft release generation** from **package publishing**.
- It uses GitHub's release UI as the approval step instead of requiring developers to push tags from a laptop.
- It uses the PyPI OIDC pattern via `pypa/gh-action-pypi-publish` with `id-token: write`, not a Twine upload step and not a long-lived PyPI API token stored in the repository.
- It updates `CHANGELOG.md` through a pull request instead of pushing directly to the branch.

### Release workflow example

1. Push changelog updates to `main`.
2. Wait for `Create Draft Release` to refresh the draft release.
3. In GitHub, go to **Releases** and open the draft.
4. Click **Publish release**.

GitHub then emits the `release` event with type `released`, which starts the `Release` workflow automatically. The workflow publishes the package using OIDC and opens a changelog PR titled like `docs: update CHANGELOG.md for release v1.2.3`.

### Roadmap

This GitHub-release-driven workflow is the current supported path. Other release strategies, such as publish-on-tag, fully manual package publishing, or different changelog synchronization flows, are possible but are not the documented default yet and are better treated as roadmap items.
