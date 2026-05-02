# Security Policy

## Reporting a Vulnerability

Please **do not** report security vulnerabilities through public GitHub issues.

Instead,
use [GitHub's private vulnerability reporting](https://github.com/matthewdeanmartin/keepachangelog-manager/security/advisories/new)
to submit a report confidentially.

Include as much of the following as possible:

- Description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- Affected versions
- Any suggested fix, if you have one

You can expect an acknowledgement within a few days and a resolution or status update within 30 days.

## Scope

This project's security scope includes:

- The published Python package and CLI in `changelogmanager/`
- Active GitHub Actions workflows in `.github/workflows/`
- Release and packaging automation used to build or publish artifacts
- Repository configuration that affects code execution, token handling, or dependency resolution

The highest-risk area for this repository is **code that runs on CI runners**. Any workflow that checks out repository
content and then executes commands from that checkout should be treated as a trust-boundary decision.

## CI / GitHub Actions guidance

When maintaining or adding workflows:

1. Treat `pull_request` jobs as execution of **untrusted code**. Keep permissions read-only, avoid repository secrets,
   and keep `persist-credentials: false` on checkout unless there is a documented reason not to.
1. Do **not** use `pull_request_target` to run code from a pull request checkout. If a privileged workflow must exist,
   keep it separate from untrusted PR execution and avoid consuming untrusted artifacts.
1. Pin third-party actions and CI tooling versions. Avoid floating `latest` or other unpinned package installs on
   runners when a pinned version or lockfile can be used instead.
1. Prefer environment variables or OIDC over passing secrets on the command line. Command-line arguments have a larger
   exposure surface in process listings, logs, and diagnostics.
1. Keep privileged automation limited to trusted events such as protected-branch pushes and release jobs, and require
   review for workflow changes.

## Supported Versions

Only the latest release receives security fixes.

| Version | Supported |
|---------|-----------|
| latest | Yes |
| older | No |
