# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Static sample CI pipeline snippets for the Releases screen.

These are shown (copyable) when running outside CI so a user can paste a working
release step into their own pipeline rather than running a live API call locally.
"""

from __future__ import annotations

GITHUB_ACTIONS_RELEASE = """\
# .github/workflows/release.yml
name: Changelog Release
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
          python-version: "3.12"
      - run: pip install keepachangelog-manager-fork
      - name: Create GitHub release from CHANGELOG
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: changelogmanager github-release --repository ${{ github.repository }} --release
"""

GITHUB_ACTIONS_PR = """\
# .github/workflows/changelog-pr.yml
name: Changelog PR
on:
  workflow_dispatch:
jobs:
  changelog-pr:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install keepachangelog-manager-fork
      - name: Open changelog PR
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: changelogmanager github-pr --repository ${{ github.repository }} --head ${{ github.ref_name }} --base main
"""

GITLAB_CI_RELEASE = """\
# .gitlab-ci.yml
changelog_release:
  image: python:3.12
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
  script:
    - pip install keepachangelog-manager-fork
    - changelogmanager gitlab-release --project "$CI_PROJECT_ID"
  variables:
    GITLAB_TOKEN: $CI_JOB_TOKEN
"""

SAMPLES: dict[str, str] = {
    "github-release": GITHUB_ACTIONS_RELEASE,
    "github-pr": GITHUB_ACTIONS_PR,
    "gitlab-release": GITLAB_CI_RELEASE,
}
