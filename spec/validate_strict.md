# Feature: `validate --strict` (strictest community standard)

Status: **implemented** · Owner: Matthew · Last updated: 2026-06-29

## Summary

Our default `validate` is intentionally lenient and Keep-a-Changelog-compliant:
version links are optional, and several content problems (ordering, empty
sections, duplicate entries, missing preamble) are *warnings*, not errors.

`validate --strict` opts into the strictest community standard, treating those as
**hard errors** (non-zero exit). It is the inverse policy knob to our lenience: use
it in CI or when a downstream consumer (e.g. upstream `kacl-cli verify`) demands a
fully linked, canonical changelog. See [bug_unreleased.md](bug_unreleased.md) for
the original `[Unreleased]` link-reference report that motivated this.

## What strict enforces (hard errors)

1. **Version link references.** When the changelog already links *any* version,
   every released version — and a non-empty `[Unreleased]` — must have a matching
   bottom-of-file link ref. A changelog that links **no** versions at all is left
   alone (a brand-new changelog is still valid).
2. **Ordering / empty / duplicate.** The conditions our default checks only warn
   about: versions out of descending order, `[Unreleased]` not on top, empty
   version or change-type sections, duplicate entries within a section.
3. **Canonical preamble.** The Keep a Changelog + Semantic Versioning preamble must
   be present (independent of the `enforce_preamble` config knob).

## Triggering

- CLI flag: `changelogmanager validate --strict`.
- Config key: `project.validation.strict = true` (standalone `changelogmanager.toml`
  uses `[project.validation]`; in `pyproject.toml` it is
  `[tool.changelogmanager.project.validation]`). The flag wins over the key.

## Strict + `--fix` (round-trips clean)

`validate --fix --strict` repairs everything mechanically fixable, then re-checks
and exits non-zero only for problems `--fix` cannot safely repair:

- The missing `[Unreleased]:` link is backfilled (see bug_unreleased.md), deriving
  the URL from existing released links.
- Ordering / empty / duplicate issues are normalised by the existing autofix.
- The canonical preamble is inserted (strict forces the preamble backfill even when
  `enforce_preamble` is off).
- A released version **genuinely missing** a link reference is *not* fabricated —
  strict reports it and exits 1, since inventing a compare URL for a historical
  release would be guesswork.

**mdformat casing (verified harmless):** the mdformat pass lowercases and re-sorts
link labels (`[Unreleased]` → `[unreleased]`). This is spec-correct CommonMark
case-folding, and real `kacl-cli verify` (python-kacl 0.7.3) was confirmed to accept
the lowercased label, so `validate --fix --strict` round-trips clean through
`validate --strict` with *or* without the mdformat pass. `--no-format` only matters
if you want to preserve the exact source casing/order cosmetically.

## Implementation

- `ChangelogReader.strict_violations(changelog, text)` +
  `_release_content_violations(...)` in `changelogmanager/changelog_reader.py`
  collect the violation messages (no I/O; the caller decides the exit code).
- `command_validate` in `changelogmanager/cli/commands.py` resolves strict (flag or
  config key), enforces it on the no-fix path via `_enforce_strict(...)`, and on the
  fix path re-checks after writing via `_raise_on_strict_violations(...)`.
- `load_changelog_for_validate_fix` in `changelogmanager/cli/loaders.py` forces
  `enforce_preamble` under strict so the raw-text pass backfills the preamble.
- `--strict` argument registered in `changelogmanager/cli/parser.py`.

## Tests

`tests/test_bug_unreleased_link.py`:
- `test_strict_flags_missing_unreleased_link_as_error`
- `test_strict_fix_roundtrips_clean`
- `test_strict_errors_on_unfixable_released_link`
- `test_strict_passes_brandnew_unlinked_changelog`

## Non-goals

- Strict is **not** the default; lenient `validate` stays Keep-a-Changelog-compliant.
- We do not fabricate link references for historical releases that never had one.
