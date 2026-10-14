---
name: kaclm-release-recovery
description: Recover failed GitHub releases managed by keepachangelog-manager-fork (kaclm), restore unreleased development state, and validate changelog links.
---

# Recover a kaclm GitHub release

Inspect repository instructions, working-tree changes, release workflows, and the installed `kaclm --help` before choosing commands. Use the project's environment and Makefile; in this Windows workspace use Git Bash and `.venv/Scripts/python.exe -m changelogmanager` when direct CLI execution is needed.

## Establish the recovery target

- Fetch/pull without overwriting user changes. Identify the exact failed tag, release ID, bump commit, pre-bump versions, workflow failure, and any later fixes.
- Read GitHub release/run state and the package index. A deleted GitHub release does not unpublish PyPI files. If the version was uploaded, plan a new version instead of assuming it can be reused.
- Check remote tags separately: `git fetch` does not remove stale local tags. Do not invent historical tags just to silence link warnings.
- Existing authorization to recover the identified failed release covers its cleanup. Do not infer authorization to publish a replacement or delete unrelated releases.

## Recover only the failed attempt

Deletion-only recovery (also supported by 6.10.1):

```bash
kaclm release-rollback --tag vX.Y.Z --repository owner/repo --dry-run
kaclm release-rollback --tag vX.Y.Z --repository owner/repo --yes
```


Inspect current help for selective `--no-github`, `--no-local-tag`, and `--no-remote-tag` switches. The current source additionally supports `--restore-unreleased`, `--restore-versions`, `--bump-commit SHA` for older releases, and opt-in `--commit --push`. Use `--dry-run` to inspect the diff first. New release bumps commit provenance under `.kaclm/releases/`; recovery receipts live inside `.git/kaclm/recovery/`. Resume with `--resume PATH` and the original action/repository/remote flags. `--check-pypi PACKAGE` checks publication before applying recovery; dry-run remains offline. Published package versions require a new version for the next release, even after GitHub cleanup.

Run this checkout through `uv run kaclm`. Recovery tests use temporary repositories, never this project's changelog or real GitHub releases. Version restoration rejects ambiguous assignment changes, including repeated identical version lines in lockfiles, instead of guessing.

Restore version fields from the actual bump's parent, including lockfiles only if changed. Preserve later functional fixes and unrelated edits. Move the failed release's entries back into Unreleased, merging with any newer entries without duplication; preserve historical releases. If someone already restored Unreleased, finish that recovery rather than reverting the whole changelog. Prefer a forward recovery commit to rewriting shared history.

Repair comparison references using existing tags or historically justified commit hashes. For an initial release with no predecessor use its source tree/commit URL, not a self-comparison. Ensure Unreleased compares the last release baseline to HEAD. Run `kaclm validate --strict`; inspect diffs after any `validate --fix`, since generated tag links may reference nonexistent tags.

Prefer `release-bump --github-output` in GitHub Actions. For JSON redirection use `$RUNNER_TEMP/release-bump.json`; this also works with older releases whose clean-tree checks rejected untracked output files. Global `--json` goes before the subcommand. Check synchronized package/lock versions and workflow syntax. Commit/push when requested, then verify the remote commit and resulting checks. A push may automatically create a new draft release; do not publish it without authorization.

Read the [original recovery proposal](references/recovery-extension.md) for design context. Consult current command help and tests for the implementation; none of the restoration options are available in 6.10.1.
