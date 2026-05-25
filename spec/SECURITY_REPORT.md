# Security Review Report

## Executive summary

No critical application-level security bugs stood out in the Python package during this review. The primary risk is the
repository's **CI trust boundary**: GitHub Actions jobs execute repository-controlled code and, in some cases, run with
write-capable automation tokens on trusted events.

The workflows already do several important things right:

- third-party GitHub Actions are pinned to commit SHAs
- checkout steps use `persist-credentials: false`
- pull request validation uses `pull_request`, not `pull_request_target`
- the Python code uses argument lists for subprocess calls rather than shell interpolation
- YAML configuration is parsed with `yaml.safe_load`

The most important remaining work is to keep privileged workflows narrow and to avoid unnecessary code or secret
exposure on runners.

## Review scope

Reviewed:

- `.github/workflows/build_and_test.yml`
- `.github/workflows/quality_checks.yml`
- `.github/workflows/create_draft_release.yml`
- `.github/workflows/release.yml`
- `.github/workflows/zizmor.yml`
- `changelogmanager/cli.py`
- `changelogmanager/config.py`
- `changelogmanager/github.py`

## Findings

| Severity | Area | Finding | Evidence | Recommendation |
|---------------|-------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Low | Token handling | The draft release workflow passed `${{ github.token }}` on the command line even though the CLI already supports `GITHUB_TOKEN` from the environment. | `.github/workflows/create_draft_release.yml:50-51`, `changelogmanager/cli.py:824-828` | Pass the token via environment variables instead of CLI arguments. |
| Informational | CI trust boundary | Several workflows intentionally execute repository code after checkout. That is safe only while those workflows remain scoped to trusted events or read-only PR validation. | `.github/workflows/build_and_test.yml:18-124`, `.github/workflows/quality_checks.yml:18-61`, `.github/workflows/create_draft_release.yml:20-53`, `.github/workflows/release.yml:20-122` | Preserve the current pattern: read-only permissions for PR jobs, no `pull_request_target` for repo code, and narrow write permissions for release automation. |

## Detailed notes

### 2. Secret exposure surface was larger than necessary

The CLI already supports:

```python
token = args.github_token or os.environ.get("GITHUB_TOKEN", "").strip()
```

Using the environment path is preferable on CI because it avoids placing the token in the process argument list. This is
a low-severity issue in this repository, but it is worth fixing because the release workflow is privileged by design.

### 3. Current PR workflow design is mostly sound

The current workflows show good security posture for untrusted pull requests:

- `build_and_test.yml` and `quality_checks.yml` run on `pull_request`
- workflow permissions are read-only at the top level
- checkouts disable persisted credentials
- actions are pinned by SHA

That combination sharply reduces the risk of a pull request turning CI execution into a repository compromise. The main
thing to avoid in future workflow edits is mixing those PR checks with write-scoped tokens, secrets, or trusted
follow-up workflows that consume untrusted artifacts.

## Application code observations

I did not find a direct command-injection issue in the Python package during this review.

- `subprocess.run(...)` calls in `changelogmanager/cli.py` use argument arrays rather than `shell=True` (
  `cli.py:904-910`, `924-929`, `1036-1041`)
- configuration loading uses `yaml.safe_load(...)` (`config.py:112-116`)
- GitHub API access is constrained to the GitHub REST API helper in `github.py`

These are good defaults and lower the risk outside CI automation.

## Changes made as part of this review

1. Pinned the Zizmor package version in `.github/workflows/zizmor.yml`
1. Switched the draft release workflow to read `GITHUB_TOKEN` from the environment instead of passing it as a CLI
   argument
1. Expanded `SECURITY.md` with CI-specific maintainer guidance
