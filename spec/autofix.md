# Autofix design

Status: **proposed** · Owner: TBD · Last updated: 2026-05-30

## Goal

Make `changelogmanager validate --fix` correct as many mechanically-fixable
`CHANGELOG.md` problems as possible, and finish with an optional Markdown
*formatting* pass driven by [`mdformat`](https://mdformat.readthedocs.io/) so the
output is also stylistically consistent — without making `mdformat` a hard
dependency.

## Background: where autofix lives today

Autofix is a two-layer operation:

1. **Structural fixes** — `ChangelogReader.autofix(data)`
   (`changelogmanager/changelog_reader.py`). Operates on the *parsed dict*, not
   raw text. Today it: lowercases change-type keys, drops empty buckets, dedupes
   entries within a bucket, and re-sorts versions newest-first. Returns
   `(data, applied_messages)`.
2. **Serialization** — `Changelog.write_to_file()` renders the dict back to
   Markdown via the vendored `keepachangelog.from_dict(...)` subset plus our preamble rewrite
   (`Changelog.__render_preamble`).

The CLI glue is `command_validate(args, ctx)` in `cli.py`: on `--fix` it
re-reads with autofix, and if anything was applied, writes the dict back. The
multi-component path is `run_validate_all(...)`.

This means today's autofixes are limited to what survives a
parse → dict → re-serialize round trip. Anything purely cosmetic in the raw
Markdown (blank lines, heading spacing, list bullet style, trailing whitespace)
is normalized only as a side effect of the vendored `keepachangelog`
serializer, which we keep intentionally tiny.

## Proposed change: add a formatting pass

Introduce a **third, optional layer** that runs *after* serialization: a
Markdown formatter pass. Pipeline becomes:

```
raw md ─▶ parse ─▶ structural autofix (dict) ─▶ serialize (vendored keepachangelog)
        ─▶ FORMAT PASS (mdformat) ─▶ write to file
```

The format pass takes the serialized Markdown string and returns a formatted
string. It is purely textual and never changes semantic content (headings,
entries, versions) — only whitespace/wrapping/bullet style.

### Why a separate pass (not inside the serializer)

- `keepachangelog.from_dict` output is intentionally fixed; keep the vendored
  surface small instead of teaching it formatting concerns.
- Formatting is opt-in and tool-discovery-dependent, so it must degrade
  gracefully when `mdformat` is absent.
- Keeping it textual and last means it composes with the existing structural
  fixes and the preamble rewrite without re-parsing.

## mdformat discovery & invocation

`mdformat` must **not** become a required runtime dependency. Discover it in
this order and use the first that works:

1. **In-process import** — `import mdformat; mdformat.text(md)`. Fastest, no
   subprocess. Used when the user installed `keepachangelog-manager-fork[format]`
   (a new optional extra) or has `mdformat` in the same environment.
2. **Auto-discovered executable** — `shutil.which("mdformat")`, invoked as
   `mdformat -` reading stdin / writing stdout. Lets users rely on a globally
   installed `uv tool install mdformat` without it being in our venv.
3. **No formatter found** — skip the pass silently at `--info` level, emit one
   `note`-level diagnostic only under `--verbose`. Structural fixes still apply.

A `--no-format` flag (and config key `project.validation.format: false`) forces
skipping layer 3 even when `mdformat` is present, for users who manage Markdown
style with their own pre-commit hook.

### Configuration surface

```yaml
project:
  validation:
    format: true            # master switch for the format pass (default: auto)
    formatter: mdformat      # reserved; only "mdformat" supported initially
    mdformat_options:        # passed through to mdformat
      number: false
      wrap: "keep"
```

`format: auto` (default) ⇒ run the pass iff a formatter is discovered.
`format: true` ⇒ run it; error if none discovered. `format: false` ⇒ never run.

CLI overrides config: `--format` / `--no-format`.

## Diagnostics & dry-run

- The format pass contributes to the `applied` list with a single entry, e.g.
  `formatted CHANGELOG.md with mdformat` — but only when the formatted text
  actually differs from the input (no-op formatting is not reported as a fix).
- `--dry-run` must show whether formatting *would* change the file without
  writing. Compute the formatted string in memory and diff against current
  on-disk content; report `would format: <path>`.
- `--json` payload gains `"formatted": true|false` alongside the existing
  `"fixed"` list.

## Idempotency & safety

- Running `validate --fix` twice must be a no-op the second time (formatter
  output is stable; `mdformat` is idempotent by design).
- The format pass operates on the rendered string only; it must never be able to
  drop a changelog entry. Add a guard test: parse the pre- and post-format
  Markdown and assert the structural dicts are equal.
- Encoding stays UTF-8; preserve a trailing newline.

## Touch points (implementation sketch)

1. New module `changelogmanager/formatting.py`:
   - `discover_formatter() -> Formatter | None`
   - `format_markdown(text, options) -> str`
   - `Formatter` protocol with in-process and subprocess implementations.
2. `Changelog.write_to_file()` (or a new `Changelog.render()` returning the
   string) gains an optional `formatter` argument so the CLI can inject the
   discovered formatter; keeps `Changelog` free of discovery logic.
3. `cli.command_validate` / `run_validate_all`: discover formatter once, thread
   it through, honour `--format/--no-format` + config, extend `applied` and the
   JSON payload.
4. `config.py`: read `project.validation.format`, `formatter`,
   `mdformat_options` with sensible defaults.
5. `pyproject.toml`: add an optional extra:
   ```toml
   [project.optional-dependencies]
   format = ["mdformat>=0.7"]
   ```

## Testing plan

- Discovery: in-process available; only executable available (monkeypatch
  `shutil.which`); neither available ⇒ pass skipped, structural fixes still run.
- Idempotency: format twice ⇒ identical bytes.
- Safety: structural dict equality before/after the format pass.
- Dry-run: reports `would format` and does not write.
- Config/flag precedence: `--no-format` beats `format: true`; `format: false`
  beats discovery.

## Open questions

- Should we vendor a minimal formatter to guarantee availability, or stay
  fully optional? (Leaning: stay optional; document the extra.)
- Do we want to expose `mdformat` plugins (e.g. `mdformat-gfm`)? Probably via
  passthrough `mdformat_options` only, no first-class config.
- Should `to-html` / `to-json` exports also be run through any formatter? No —
  the format pass is Markdown-only.

## Out of scope

- Reflowing prose inside entries beyond what `mdformat` does by default.
- Rewriting links or auto-generating version-compare URLs.
