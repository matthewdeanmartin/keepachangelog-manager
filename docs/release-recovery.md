# Recovering a failed GitHub release

Use a forward recovery commit when a failed release has already merged its version bump. The recovery command restores release metadata while keeping later fixes. It never rewrites shared branch history or removes packages from PyPI.

Preview an older release using its original bump commit (not the merge commit):

```bash
uv run kaclm --json release-rollback --tag v1.2.0 \
  --bump-commit <commit-sha> --restore-unreleased --restore-versions --dry-run
```

Run the same command with `--yes` instead of `--dry-run` to apply it. Add `--commit` to create a recovery commit and `--push` to push the current branch without force. Omit either restoration flag to select only the work you need. The existing `--no-github`, `--no-local-tag`, and `--no-remote-tag` options independently disable deletion; use all three for file-only recovery. Without restoration flags, the existing deletion-only interface is unchanged.

New `release-bump` commits include a manifest under `.kaclm/releases/`. It records the parent SHA, component, tag, repository, release ID when supplied, known tag SHA, changelog path, and version-file paths. The manifest's Git commit identifies the bump; before/after file contents and changelog link changes come from that commit and its parent. Recovery can discover it without `--bump-commit`. Releasing the same unpublished version again replaces the manifest in a new commit; the earlier provenance remains in Git history.

Recovery requires a clean tracked working tree. It merges the failed section into Unreleased without duplicating entries, retaining later fixes and existing historical releases. A manually restored heading is accepted when the original entries are still present. The restored Unreleased comparison URL comes from the pre-bump changelog. Strict validation runs before changes are written or remote artifacts deleted.

Version restoration changes only assignments changed by the bump. It preserves neighboring edits. Conflicting version changes, non-version changes in a version file, and ambiguous repeated assignments require manual resolution. For a single-component project, changed Cargo and uv lockfiles are considered alongside the normal version files; no dependency resolution or lockfile regeneration runs. Multi-component projects use their explicit version-file ownership. A bump must already be an ancestor of the current checkout; for an unmerged bump branch, check out that branch first.

Dry-run is offline and does not write a manifest, receipt, commit, or file. JSON includes before/after content and planned/skipped actions; human output includes a diff. Live recovery checks resource identities before mutation and again before deletion. Remote tag deletion uses a SHA lease. A tag or release changing during recovery stops the operation. Authentication and transport errors are failures, not missing resources.

To check package publication, add `--check-pypi PACKAGE`. A published version produces an instruction to use a new version for the next release; GitHub cleanup can still proceed. An unavailable index stops this optional check. Without the flag, publication status remains unchecked. A 404 or empty version response reports only current absence, not a guarantee that a deleted PyPI filename can be reused.

Each applied step saves its state in `.git/kaclm/recovery/`. After a failure, fix the reported problem and resume the printed receipt:

```bash
uv run kaclm release-rollback --resume <receipt-path> \
  --repository owner/repo --restore-unreleased --restore-versions --commit --push --yes
```

Repeat the original deletion, commit/push, repository, remote, and PyPI-check options. The tag comes from the receipt if omitted. Completed steps are not repeated. A changed HEAD or edited recovery file requires inspection instead of silently applying a stale plan. JSON receipts distinguish planned, succeeded, already absent, skipped, and failed steps. They contain file contents, so keep them local. GitHub deletions and Git pushes are not an atomic transaction; a crash immediately after a commit can require manual reconciliation of the receipt with HEAD.

A successful push may trigger your repository's draft-release workflow. Recovery does not publish that draft. In GitHub Actions, prefer `release-bump --github-output` or redirect JSON outside the checkout to `$RUNNER_TEMP/release-bump.json`.
