# GitHub automation

This page covers the GitHub-specific commands and the repository's GitHub Actions release flow. For generic validation
gates that work anywhere, see [Generic CI](CI.md).

## `github-release`

`changelogmanager github-release` turns the current `[Unreleased]` section into a GitHub release payload.

```sh
changelogmanager github-release --repository owner/repo
```

By default it creates a **draft** release. With `--release`, it publishes immediately instead of leaving the release in
draft state.

Behavior summary:

1. Reads the GitHub token from `--github-token` or `GITHUB_TOKEN`.
2. Validates that `[Unreleased]` exists and can produce a future version.
3. Deletes all existing draft releases for the target repository.
4. Creates a new GitHub release named `Release vX.Y.Z`.
5. Generates release notes from `[Unreleased]` using the changelog categories and emoji headings.

If `[Unreleased]` has no entries, the command prints a clear skip notice and exits `0`.

## Draft release workflow in this repository

The repository's `Create Draft Release` workflow lives at `.github/workflows/create_draft_release.yml`.

It runs on every push to `main`, installs the project with `uv`, and runs:

```sh
uv run changelogmanager github-release \
  --github-token "${{ github.token }}" \
  --repository "${{ github.repository }}"
```

This workflow does **not** rewrite `CHANGELOG.md`. It only keeps the GitHub draft release in sync with the current
`[Unreleased]` section.

## `github-pr`

`changelogmanager github-pr` opens or updates a pull request for a release branch.

```sh
changelogmanager github-pr \
  --repository owner/repo \
  --head release/bump-123 \
  --base main \
  --title "chore: release 1.2.3"
```

If a matching open PR already exists for the same `head` and `base`, the command updates its title/body instead of
opening a duplicate.

## Release automation in this repository

This repository uses an opinionated **bump -> build -> publish** workflow in `.github/workflows/release.yml`.

### Why this order matters

`pyproject.toml` contains a static `version = "x.y.z"` string that `uv build` reads directly. If a build runs before
that string is updated, the wheel carries the previous version number and PyPI gets the wrong release. The bump job runs
first so every later step sees the correct version.

### Triggering a release

1. Merge unreleased changelog entries to `main`.
2. Let the draft-release workflow keep the GitHub draft in sync from `[Unreleased]`.
3. Open the repository's **Releases** page in GitHub and open the current draft.
4. Review the title, notes, and target branch, then click **Publish release**.

Publishing fires the `release` event, which starts `.github/workflows/release.yml`.

### What the three jobs do

**`bump`**

Checks out the release target branch, installs the `jiggle` extra, and runs:

```sh
uv run changelogmanager release \
  --override-version "$VERSION" \
  --bump-versions \
  --yes
```

It then commits the updated changelog/version files to `release/bump-<release-id>`, pushes that branch, and opens or
updates a pull request with `github-pr`.

**`build`**

Builds from the bump branch so `pyproject.toml` already carries the released version, then uploads `dist/` as an
artifact.

**`publish`**

Downloads the dist artifact and publishes to PyPI via OIDC. No long-lived PyPI token is stored in the repository.

### GitHub Actions permission prerequisite

The release workflow opens a pull request with the repository `GITHUB_TOKEN`. Besides the workflow YAML permissions, the
repository-level Actions setting must also allow this. In **Settings -> Actions -> General -> Workflow permissions**,
enable **Allow GitHub Actions to create and approve pull requests**.

If that setting is disabled, the branch push can succeed while the PR API call fails with a `403` such as
`Resource not accessible by integration`.

### Failure recovery

| Job that fails | State of the world | Recovery |
|---|---|---|
| `bump` | Nothing built, nothing published, no PR. | Fix the issue and re-publish the GitHub Release. |
| `build` | PR branch exists. Nothing published. | Close the PR, delete the GitHub Release, fix the build, re-publish. |
| `publish` | PR branch + dist artifact exist. Nothing on PyPI. | Re-run just `publish`, or close the PR, delete the release, fix the issue, and re-publish. |
