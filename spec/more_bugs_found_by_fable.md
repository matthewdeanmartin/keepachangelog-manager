# More bugs found by Fable (2026-07-04)

Discovered by loading `../bash2yaml/CHANGELOG.md` into the GUI. That file has five
nested sub-list bullets under the "Traceless mode" entry (lines 46, 52, 54, 56, 59) —
legal Markdown, but rejected by this tool's "Sub-lists are not permitted in changelog
entries" layout rule. That made it a perfect trigger for two GUI bugs.

## Bug 1 (colossal, destructive): failed load + save = changelog wiped

**Symptom.** Open the GUI on a changelog that exists but fails layout validation, then
hit Save / Validate / Release on the Edit screen. The file is rewritten containing only
the preamble header — every version and entry is gone.

**Root cause.** `AppState.reload()` in `changelogmanager/gui/state.py` caught the
reader's exception and substituted an **empty** `Changelog(file_path=path)` bound to the
*real* file path. The Edit screen's `save()` renders whatever model is loaded and writes
it to `changelog.get_file_path()` — so the empty stand-in model rendered as a bare
header and clobbered the file. Worse, `validate()` and `release()` both called `save()`
unconditionally as a "persist edits first" step, so even actions that *look* read-only
(clicking Validate to find out what's wrong!) destroyed the file.

The empty-model fallback was only intended for the *missing-file* case, where saving is
safe (it creates the file). The parse-failure case reused it incorrectly.

**Fix.**

- `state.py::reload()` — when the file exists but fails to parse, `changelog` is now
  `None` (missing-file still yields an empty editable model). All Edit-screen mutations
  and `save()` already refuse to run when the model is `None`
  (`require_changelog()`), so there is nothing left that can write.
- `edit.py::save()` — belt-and-braces guard: refuses to write when `load_error` is set
  and the target file exists on disk, with an explanatory error dialog.
- `edit.py::validate()` — only saves first when there is a cleanly loaded model;
  otherwise it validates the on-disk file as-is (which is exactly what you want when
  the load failed).
- `edit.py::refresh()` — the load-error banner now shows even when the model is `None`,
  followed by an explanation that editing is disabled to protect the file, suggesting
  `validate --fix` + Reload.

**Regression test.** `tests/test_gui.py::test_appstate_invalid_changelog_yields_no_model`
loads an invalid changelog through `AppState` and asserts no model is produced and the
file's bytes are untouched.

## Bug 2: "5 problems" reported with no detail

**Symptom.** The GUI status bar / Edit screen said only
`5 errors detected in the layout` — the actual diagnostics were nowhere in the UI.

**Root cause.** `ChangelogReader.read()` ran `validate_layout()`, which printed each
diagnostic to **stderr** (`Message.report()`) and returned only a count; the raised
`logging.Error`'s message contained just `"{n} errors detected in the layout"`. The
GUI's `AppState.reload()` calls the reader in-process (not through `run_cli`, which
does capture stderr), so the per-line diagnostics vanished into the console and only
the count reached `load_error`.

**Fix.** In `changelogmanager/changelog_reader.py`:

- New `collect_layout_errors()` returns the diagnostic list without reporting;
  `validate_layout()` is now a thin wrapper that reports each one and returns the count
  (public behavior unchanged — all existing callers/tests pass).
- `read()` still reports each diagnostic to stderr for CLI users, but the raised
  exception message now also embeds one line per diagnostic
  (`line 46: Sub-lists are not permitted in changelog entries`, …), so any consumer
  that only sees the exception — the GUI — shows the user *what* is wrong.

The Edit screen's load-issue label is left-justified so the multi-line detail renders
readably.

## Verification

- Repro script: loading a copy of bash2yaml's changelog through `AppState` yields
  `changelog is None` and a `load_error` containing all five `line N: …` diagnostics;
  the missing-file path still yields an editable empty model.
- Full suite: 847 passed, 2 skipped (includes the new regression test and the two
  updated reader tests, which now also assert the exception carries the details).

## Feature follow-up: nested sub-list bullets are now supported

The trigger itself is fixed: bash2yaml's changelog now loads cleanly. Background on
the parser: it is **not** an AST — the vendored `keepachangelog` module
(`changelogmanager/vendor/keepachangelog/__init__.py`) is a line-by-line
strip-and-dispatch parser, and the model is a flat `list[str]` of entries per
category. Design chosen: **preserve nesting inside the parent entry string** —
an indented bullet parses to an embedded `"\n  - child"` line (two spaces per
nesting level) appended to the previous entry. The model type, mutation API,
exports, and schema validation are all unchanged, and `from_dict` emits embedded
newlines verbatim, so the nesting round-trips byte-stably (verified: parse →
render → re-parse is a fixed point, and mdformat under `validate --fix --strict`
keeps the two-space indent).

Changes:

- **Parser** (`vendor/keepachangelog`): indentation is measured on the raw line
  before stripping; an indented bullet folds into `category[-1]` via
  `add_nested_information()` instead of becoming a sibling entry. Soft-wrapped
  continuations of a nested bullet keep working (they append to the entry tail,
  which is the nested line).
- **Validator** (`changelog_reader.validate_entry`): the "Sub-lists are not
  permitted" indent error is gone. The separate `ENTRY_RULES` rule for a doubled
  marker on one line (`- - foo`) remains, reworded to "Doubled list markers are
  not permitted".
- **Autofix** (`autofix_line`): no longer strips leading indentation (that was a
  flattening fix for something that is now valid); marker fixes preserve indent.
- **Bonus bug fixed while here**: `add_information()` used `lstrip(" *-")` to
  remove the bullet marker, which also ate Markdown emphasis markers — an entry
  starting with `**bold**` lost its `**` (bash2yaml's `**Traceless mode**`
  demonstrated this). It now strips exactly one bullet marker.
- Tests: new `tests/test_vendored_keepachangelog/test_changelog_nested_bullets.py`
  (fold, round-trip, wrapped continuation of a nested bullet, deeper nesting);
  flipped the two tests that asserted sub-lists are errors; the GUI regression
  test's invalid-file trigger switched to a numbered-list entry. Suite: 853
  passed, 2 skipped.

Known cosmetic limits (acceptable, not bugs): the GUI Edit screen shows a
multi-line entry in a single-line `ttk.Entry`, and the HTML export renders the
embedded sub-bullets as literal text inside one `<li>`.

## Not fixed here (candidates)

- Other screens drive the CLI via `run_cli`, which re-reads the file per command, so
  they fail loudly rather than destructively — but `release`-family commands were not
  audited line-by-line for similar "empty model on failure" fallbacks outside the GUI.
- GUI Edit screen could render nested bullets as an indented tree / multi-line
  editor instead of a flat `ttk.Entry`.
- HTML export could turn embedded `\n  - ` lines into real nested `<ul>`s.
