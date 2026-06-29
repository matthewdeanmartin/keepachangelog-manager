# Bug: missing `[Unreleased]` link reference — error UX and autofix gap

Status: **implemented** · Owner: Matthew · Last updated: 2026-06-29

Implementation: `derive_unreleased_url()` + `unreleased_url_backfill()` /
`advise_missing_unreleased_url()` in `changelogmanager/changelog_reader.py`, wired
into `autofix(...)` (backfill under `--fix`) and `validate_contents(...)` (advisory
on plain `validate`). Regression tests in `tests/test_bug_unreleased_link.py`.

Note on mdformat casing: the `--fix` mdformat pass lowercases link labels
(`[Unreleased]` -> `[unreleased]`) and re-sorts them. This is spec-correct CommonMark
behavior (reference labels are case-folded). **Verified harmless:** real `kacl-cli
verify` (python-kacl 0.7.3) accepts the lowercased `[unreleased]:` label and still
resolves the Unreleased link, so `--fix` output passes strict verification with *or*
without the mdformat pass. `--no-format` is therefore only needed if you want to
preserve the exact source casing/order for cosmetic reasons, not for kacl compliance.

## Summary

A `CHANGELOG.md` whose **released** versions carry bottom-of-file link references
(`[0.6.1]: …/compare/v0.6.0...v0.6.1`) but whose **`## [Unreleased]`** heading has
**no matching `[Unreleased]:` reference** is a recurring source of friction.

Two distinct issues, one of which is ours:

1. **Not our validator (context).** The error a user actually hits in the wild —

   ```
   CHANGELOG.md:8:3: error: Version "Unreleased" is linked, but no link reference
   found in changelog file.
   ## [Unreleased]
      ^~~~~~~~~~~
   1 error(s) generated.
   ```

   is emitted by **upstream `python-kacl` (`kacl-cli verify`)**, *not* by this
   fork. `changelogmanager validate` accepts the same file with **0 errors** (see
   reproduction). So our layout validator is already lenient here, which is good.

2. **Our autofix gap (the actual ask).** Because we don't treat the missing
   `[Unreleased]:` reference as a problem, `changelogmanager validate --fix` will
   **not** add it either. A user who *must* satisfy a strict consumer (CI that
   shells out to `kacl-cli`, e.g. `troml-dev-status`'s changelog check) therefore
   cannot get a clean, convention-preserving fix from our tool. The only existing
   autofix (`kacl-cli link generate -m`) is lossy — it rewrites *every* link with
   a hardcoded template, stripping the `v` tag prefix and corrupting the
   initial-version link. So today the safe fix is fully manual.

## Reproduction

Fixture `CHANGELOG.md` — released versions have link refs, `[Unreleased]` does not:

```markdown
## [Unreleased]

### Added

- A new thing

## [0.2.0] - 2026-01-02
### Added
- Second release

## [0.1.0] - 2026-01-01
### Added
- Initial release

[0.2.0]: https://github.com/acme/proj/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/acme/proj/releases/tag/v0.1.0
```

```bash
# Our tool — accepts it:
$ changelogmanager --input-file CHANGELOG.md validate ; echo $?
0

# Upstream kacl-cli on the SAME file — errors:
$ kacl-cli -f CHANGELOG.md verify ; echo $?
CHANGELOG.md:8:3: error: Version "Unreleased" is linked, but no link reference found in changelog file.
1

# Our --fix does NOT add the missing [Unreleased]: ref (only an mdformat pass):
$ changelogmanager --input-file CHANGELOG.md validate --fix --dry-run
would fix: formatted CHANGELOG.md with mdformat
Dry run: would write 1 fix(es) to CHANGELOG.md
```

Real-world hit: `troml_dev_status/CHANGELOG.md`. Adding a new `## [Unreleased]`
entry made `kacl-cli verify` fail in that project's build until a hand-written
`[Unreleased]: …/compare/v0.6.1...HEAD` line was added at the bottom. This is the
2nd report of `[Unreleased]`-link noise.

## Where this lives in our code

- **Parse:** `vendor/keepachangelog/__init__.py` `LINK_PATTERN` (line ~32) reads
  `[name]: url` refs into `metadata['url']` per version (lines ~129–154). An
  `[Unreleased]:` ref, if present, is parsed and round-trips fine.
- **Serialize:** same file, `from_dict(...)` (lines ~190–226) emits a link ref
  **only when** `metadata.get("url")` is set (line ~220). It never *synthesizes*
  a missing one — so a project with no `[Unreleased]:` ref simply gets none back.
- **Validate:** `changelog_reader.py` layout validation does not flag the missing
  `[Unreleased]:` ref (correctly — it's optional per Keep a Changelog).
- **Fix:** `ChangelogReader.autofix(...)` + the `--fix` glue in `cli/commands.py`
  do structural + mdformat passes only; no link-reference backfill.

## Proposed fix

Make the missing `[Unreleased]:` reference a **mechanically fixable** item, gated
behind `--fix` (do **not** turn it into a hard `validate` error — keep our lenient
default and stay Keep-a-Changelog-compliant).

1. **Detect (advisory, not an error).** During `validate`, if `## [Unreleased]`
   exists, has entries, and ≥1 *released* version has a link ref but there is no
   `[Unreleased]:` ref, surface an **info/warning** with the exact remediation
   (the fix command and the line that would be added) — not a non-zero exit by
   default. This directly addresses "give a better error that explains how to
   fix."

2. **Backfill under `--fix` (convention-preserving).** Derive the `[Unreleased]:`
   URL from the **existing released-version links**, not a hardcoded template:
   - Detect the host/repo and the compare-URL shape from the most recent released
     ref (e.g. `…/compare/v0.6.0...v0.6.1`).
   - Detect the tag prefix from those refs (here `v`) instead of assuming none —
     this is exactly what `kacl-cli link generate` gets wrong.
   - Emit `[Unreleased]: <host>/<repo>/compare/<vPREFIX><latest>...HEAD`
     (prefer `HEAD` over a branch name like `master`/`main` so it is
     branch-agnostic; or make the unreleased target configurable).
   - Set this as the Unreleased section's `metadata['url']` so the existing
     `from_dict` serializer (line ~220) emits it with **zero** changes to the
     other link lines.

3. **Only add, never rewrite.** The fix must add the single missing
   `[Unreleased]:` line and leave all hand-curated released-version links byte-for-byte
   unchanged (the opposite of `kacl-cli link generate -m`, which clobbered them).

### Expected `--fix` result on the fixture above

```diff
+[Unreleased]: https://github.com/acme/proj/compare/v0.2.0...HEAD
 [0.2.0]: https://github.com/acme/proj/compare/v0.1.0...v0.2.0
 [0.1.0]: https://github.com/acme/proj/releases/tag/v0.1.0
```

## Acceptance criteria

- [ ] `validate` (no `--fix`) still exits `0` on a file missing only the
      `[Unreleased]:` ref, but prints an actionable info/warning naming the fix.
- [ ] `validate --fix` adds a single `[Unreleased]:` ref derived from existing
      released-version links, preserving the detected tag prefix (`v…`).
- [ ] No existing link-reference line is modified or reordered by the fix.
- [ ] `--fix --dry-run` previews the added line without writing.
- [ ] After `--fix`, the file passes strict upstream `kacl-cli verify`.
- [ ] No-op (and no spurious warning) when there are no released link refs at all
      (a brand-new changelog), or when `[Unreleased]:` already exists.
- [ ] Regression test using the reproduction fixture above.

## Notes / non-goals

- Do **not** make missing `[Unreleased]:` a default hard error — Keep a Changelog
  treats version links as optional; only strict consumers require them.
- This is independent of the upstream `python-kacl` behavior; we can't change
  `kacl-cli`, but we can make our `--fix` produce output that satisfies it.
