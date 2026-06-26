# GitLab automation

This page covers GitLab-specific usage. For generic changelog validation gates that work in any CI system, see
[Generic CI](CI.md).

## `gitlab-release`

`changelogmanager gitlab-release` turns the current `[Unreleased]` section into a GitLab release.

```sh
changelogmanager gitlab-release --project group/project
```

`--project` accepts either a numeric project ID or a URL path such as `group/subgroup/project`.

Useful variants:

```sh
changelogmanager gitlab-release --project "$CI_PROJECT_ID" --ref "$CI_COMMIT_SHA"
changelogmanager gitlab-release --project group/project --gitlab-url https://gitlab.example.com
```

Unlike GitHub, GitLab has no draft-release concept. The command is therefore an idempotent upsert:

- if the computed tag already has a release, it updates that release
- otherwise it creates a new release and lets GitLab create the tag from `--ref`

If `[Unreleased]` has no entries, the command prints a clear skip notice and exits `0`.

## Authentication and the `CI_JOB_TOKEN` caveat

Token lookup order is:

1. `--gitlab-token`
1. `GITLAB_TOKEN`
1. `CI_JOB_TOKEN`

**Heads up:** the default `CI_JOB_TOKEN` is intentionally restricted and typically **cannot** create releases. The
Releases API often responds with `401 Unauthorized` or `403 Forbidden`.

When that happens, supply a token with the `api` scope instead:

- a [Project access token](https://docs.gitlab.com/ee/user/project/settings/project_access_tokens.html)
- a [Group access token](https://docs.gitlab.com/ee/user/group/settings/group_access_tokens.html)
- a [Personal access token](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html)

Expose it to CI as a masked variable named `GITLAB_TOKEN`.

## Example `.gitlab-ci.yml`

```yaml
stages:
  - validate
  - release

validate-changelog:
  stage: validate
  image: python:3.14
  script:
    - pip install uv
    - uv sync --frozen
    - uv run changelogmanager validate

release:
  stage: release
  image: python:3.14
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
  before_script:
    - pip install uv
    - uv sync --frozen
  script:
    - >
      uv run changelogmanager gitlab-release
      --project "$CI_PROJECT_ID"
      --gitlab-url "$CI_SERVER_URL"
      --ref "$CI_COMMIT_SHA"
  variables:
    # CI_JOB_TOKEN usually cannot create releases; use a project/group/personal token.
    GITLAB_TOKEN: $RELEASE_TOKEN
```

For self-hosted GitLab, pass `--gitlab-url "$CI_SERVER_URL"` so the API calls target the correct instance.
