# Contributing to keepachangelog-manager

:+1::tada: Thanks for taking the time to contribute! :tada::+1:

The following is a set of guidelines for contributing to `keepachangelog-manager`. These are mostly guidelines, not rules.
Use your best judgment, and feel free to propose changes to this document in a pull request.

## How Can I Contribute?

### Your First Code Contribution

Feel free to make a branch on the repository for your personal contributions.
Before creating a Pull Request, please ensure:

- You synced the local environment with `make sync`
- You ran `make format-check` to ensure consistency of coding standards
- All unit tests are passing via `make test`
- Both `flake8` and `pylint` pass via `make lint`

### Pull Requests

- Please ensure that you apply the [Conventional Commits] standard to the commits in your Pull Request
- We keep a linear history, please rebase your changes against the `main` branch (and do *NOT* use merge commits)

[conventional commits]: https://www.conventionalcommits.org/en/v1.0.0/
