# keepachangelog-manager

**keepachangelog-manager** is a CLI tool and Python library for managing
`CHANGELOG.md` files that follow the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

This project is a fork of the original `keepachangelog-manager`, and it also
vendors a small subset of the upstream `keepachangelog` parser internally. If
you want that implementation split explained, see [Vendored code and forks](vendored.md).

## What keepachangelog-manager adds

On top of the base parser/serializer, this tool provides:

- **Validation + autofix** with `validate` and `validate --fix`
- **Interactive and scripted editing** of `[Unreleased]`
- **Automatic version calculation** for `semver`, `pep440`, and `calver`
- **Release promotion** from `[Unreleased]` into dated version sections
- **Version string syncing** with `release --bump-versions`
- **Backfill from local and online sources** including git tags, commit intervals, GitHub Releases, merged GitHub PRs, and PyPI history
- **Commit-message linting** with `lint-commits`
- **Unpushed rewrite planning** with `rewrite-messages`
- **Task and fragment staging workflows** using `TASKS.md`, `changelog.d/`, and `tickets/`
- **JSON and HTML export**
- **Bundled skill export**
- **GitHub and GitLab release automation**
- **Stored credential support** through the OS keyring
- **Multi-component repository support**
- **Tkinter GUI** for editing, staging, auditing, backfill, release, and export flows

## Next steps

- [Quick start](quickstart.md)
- [Installation](installation.md)
- [Key Workflows](workflows.md)
- [Releasing](releases.md)
- [Changelog fragments](fragments.md)
- [Tasks and fragments](tasks.md)
- [Scripting and CI integration](scripting.md)
- [CLI reference](cli.md)
- [Desktop GUI](gui.md)
- [Pre-commit](precommit.md)
- [Generic CI](CI.md)
- [GitHub automation](github.md)
- [GitLab automation](gitlab.md)
- [Vendored code and forks](vendored.md)
- [Contributing](contributing.md)
