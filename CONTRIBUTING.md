# Contributing to keepachangelog-manager

:+1::tada: Thanks for taking the time to contribute! :tada::+1:

The following is a set of guidelines for contributing to `keepachangelog-manager`. These are mostly guidelines, not rules.
Use your best judgment, and feel free to propose changes to this document in a pull request.

## How Can I Contribute?

### Your First Code Contribution

Feel free to make a branch on the repository for your personal contributions.

## Development workflow

Use the `Makefile` as the primary developer entry point instead of memorizing raw commands.
Start with:

```sh
make help
make sync
```

Common targets:

- `make format` / `make format-check`
- `make lint`
- `make test`
- `make validate` — validates `CHANGELOG.md` with `keepachangelog-manager`
- `make quality` — runs the normal pre-PR checks
- `make prerelease` — runs the full prerelease flow, including changelog validation, version checks, docs sync, and build

## Changelog and releases

We dogfood `keepachangelog-manager` in this repository.

- Use `keepachangelog-manager` / `changelogmanager` to update `CHANGELOG.md`
- Validate changelog changes with `make validate`
- Do not hand-roll release sections when the tool can do the change for you

Releases are handled by GitHub Actions, not by ad-hoc local release steps.
The draft release is kept in sync from `[Unreleased]`, and publishing the GitHub Release triggers the repository release workflow.
See [docs/github.md](docs/github.md) for the current automation flow.

Before creating a Pull Request, please ensure:

- You synced the local environment with `make sync`
- You updated the changelog with `keepachangelog-manager` when the change is user-facing
- You ran `make quality`

Before cutting or preparing a release, run:

- `make prerelease`
