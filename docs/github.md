# GitHub automation

This page covers GitHub-specific commands and the repository's current GitHub
Actions release flow. For generic validation gates, see [Generic CI](CI.md).

## `github-release`

`changelogmanager github-release` turns the current `[Unreleased]` section into
a GitHub release payload.

```sh
changelogmanager github-release --repository owner/repo
```

By default it creates or updates a **draft** release. With `--release`, it
publishes immediately instead.

Behavior summary:

1. reads the GitHub token from `--github-token` or `GITHUB_TOKEN`
1. validates that `[Unreleased]` exists and can produce a future version
1. finds the release with the exact selected tag and updates it in place, or creates it
1. preserves attached assets, existing titles and provider metadata
1. generates release notes from `[Unreleased]` using grouped category sections

If `[Unreleased]` has no entries, the command exits `0` with a skip notice unless
`--version` selects an existing release section.

Generated notes are enclosed by `<!-- kaclm:release-notes:start -->` and
`<!-- kaclm:release-notes:end -->`. Refresh replaces only that block. Put human
notes outside it. An older release without markers keeps its existing body and
gets a generated block appended; remove duplicated legacy notes once if desired.
Assets and other versions' drafts are never deleted by refresh. A background
`--draft` run leaves an already published release unchanged. An explicit
`--release` can publish an existing draft or refresh a published release.

### Python prereleases

Select PEP 440 explicitly in `pyproject.toml`:

```toml
[tool.changelogmanager.versioning]
scheme = "pep440"
```

```sh
kaclm github-release --repository owner/repo --version 1.4.0rc2
```

An existing numbered section supplies its own notes. Otherwise the command uses
`[Unreleased]` and validates the requested version before calling GitHub. Creating
a PEP 440 alpha/beta/rc/dev release sets GitHub's prerelease flag. Refresh preserves
existing prerelease/latest choices from GitHub's UI. Version syntax still comes
from configuration; the checkbox cannot distinguish alpha, beta, rc, or dev.

GitHub `published` is the event for publishing either a stable release or a
prerelease, including from a draft. It means the GitHub release is published,
not that an upload to PyPI has succeeded. The repository's workflow listens for
`published` and retains the intentional subsequent version-bump PR.

### Actions outputs

`release-bump --github-output` writes `version`, `branch`, `component`, `tag_name`,
`commit_sha`, and available PR details directly to `$GITHUB_OUTPUT`, removing
JSON extraction from workflow shell. Use `${{ steps.release.outputs.branch }}`
in subsequent steps. Dry runs do not write outputs. Git author and remote push
credentials remain the workflow's responsibility.


## `github-pr`

`changelogmanager github-pr` opens or updates a pull request for a changelog or
release branch.

```sh
changelogmanager github-pr \
  --repository owner/repo \
  --head release/bump-123 \
  --base main \
  --title "chore: release 1.2.3"
```

If a matching open PR already exists for the same `head` and `base`, the command
updates its title/body instead of opening a duplicate.

## Example GitHub Actions step

The smallest useful example is keeping a draft release synced from
`[Unreleased]`:

```yaml
name: Create Draft Release
on:
  push:
    branches: [main]

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - uses: astral-sh/setup-uv@v8
      - run: uv sync --frozen
      - env:
          GITHUB_TOKEN: ${{ github.token }}
        run: uv run changelogmanager github-release --repository ${{ github.repository }}
```

## Workflows in this repository

### `create_draft_release.yml`

This workflow runs on pushes to `main` and manual dispatch.

It:

1. checks out the repository with full history
1. installs Python 3.14 and `uv`
1. runs `uv sync --frozen`
1. runs `uv run changelogmanager github-release --repository ${{ github.repository }}`

It does **not** rewrite `CHANGELOG.md`. It only keeps the GitHub draft release
in sync with the current `[Unreleased]` section.

### `release.yml`

This workflow runs when a GitHub Release is published.

It is intentionally split into three jobs:

1. `bump`
1. `build`
1. `publish`

#### `bump`

- checks out the release target branch, not the tag
- syncs with the `jiggle` extra
- runs `uv run changelogmanager release --override-version "$VERSION" --bump-versions --yes`
- commits the updated changelog/version files to `release/bump-<release-id>`
- pushes that branch
- opens or updates the release PR with `github-pr`

This is the only place the workflow writes the released version back into the
repository.

#### `build`

- checks out the bump branch
- builds the wheel and sdist with `uv build --no-sources`
- verifies the wheel filename contains the expected release version
- uploads `dist/` as the `packages` artifact

#### `publish`

- downloads the `packages` artifact
- publishes to PyPI via OIDC using `pypa/gh-action-pypi-publish`

No long-lived PyPI token is stored in the repository.

## Why the job order matters

`pyproject.toml` contains a static version string. The bump job must happen
before the build job so built artifacts carry the same version number that was
released in the changelog and on GitHub.

## Triggering a release in this repository

1. merge unreleased changelog entries to `main`
1. let `create_draft_release.yml` refresh the GitHub draft release
1. open **Releases** on GitHub
1. open the current draft release
1. click **Edit**
1. review the title, notes, and target branch
1. save any edits to the draft
1. click **Publish release**

Publishing the release fires the `release` event and starts `release.yml`.

If you are new to GitHub Releases, this UI flow is easy to miss: the draft must
be opened from the Releases page and published there. Creating the draft alone
does not trigger the release workflow.

## Other GitHub Actions in this repository

Not all workflows are release workflows:

- `build_and_test.yml`: full CI on pushes to `main`, pull requests, and manual dispatch
- `quality_checks.yml`: PR changelog validation
- `zizmor.yml`: workflow safety analysis when `.github/**` changes

## GitHub Actions permission prerequisite

The release workflow opens a pull request with the repository `GITHUB_TOKEN`.
Besides the YAML permissions, the repository-level Actions setting must also
allow this:

**Settings -> Actions -> General -> Workflow permissions -> Allow GitHub Actions to create and approve pull requests**

If that setting is disabled, branch push can succeed while the PR creation call
fails with `403 Resource not accessible by integration`.

## Failure recovery

| Job that fails | State of the world | Recovery |
|---|---|---|
| `bump` | Nothing built, nothing published, no PR branch to merge | Fix the issue and publish the GitHub Release again |
| `build` | PR branch exists, nothing published | Close the PR, delete the GitHub Release, fix the build issue, and publish again |
| `publish` | PR branch exists and artifacts were built, nothing on PyPI | Re-run `publish`, or close the PR, delete the release, fix the issue, and publish again |

## Independent packages in a monorepo

For configuration, ownership rules, and the overall release process, see
[Component Workflows](components.md). Each component publishes a separate GitHub
release using its own changelog and tag namespace.

With the `core`/`plugin` configuration in that guide and pending plugin notes:

```shell
# Preview the next draft and its component-specific tag.
kaclm --component plugin --json github-release --repository owner/repo --dry-run

# Publish/update only this component's draft release.
kaclm --component plugin github-release --repository owner/repo

# After publication, prepare its version bump and PR.
# Replace this example tag with the tag actually published.
kaclm --component plugin --json release-bump \
  --version plugin-v0.1.0 --base main \
  --repository owner/repo --open-pr --yes
```

The second command creates or refreshes a draft; publish it in GitHub, or add
`--release` to publish immediately. The release-bump step promotes the selected
component's local `[Unreleased]` notes and changes its owned version files.

`github-release` refreshes the selected tag in place and preserves sibling drafts.
`release-bump` accepts either the matching tag or a bare version. Its generated branch
name includes the component in multi-component projects, so independent releases of the
same version do not collide. The JSON result includes `component`, `tag_name`, `branch`,
`commit_sha`, and `changed_files` for CI checkout and inspection.

`release --bump-versions` and both commands' dry runs use the same file selection. A release
bump refuses pre-existing tracked edits and stages only its changelog and changed version
files, rather than every tracked modification. Untracked log/output files are not committed.
Run release commands from inside the intended Git repository. Shared lockfiles and changes
to dependency constraints are not updated by this feature.

If you already promoted a local changelog section, publish those notes explicitly
with `--version VERSION`. For PEP 440 prereleases, set the shared versioning scheme
to `pep440`; either a bare version such as `1.4.0rc2` or the selected component's
matching tag such as `plugin-v1.4.0rc2` is accepted.
