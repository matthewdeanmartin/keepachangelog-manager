# Vendored `keepachangelog`

This directory contains a slim vendored copy of the parser/serializer logic from
[`Colin-b/keepachangelog`](https://github.com/Colin-b/keepachangelog).

## Kept

- `to_dict(...)`
- `to_dict(..., show_unreleased=True)`
- `from_dict(...)`
- SemVer, PEP 440, and CalVer metadata extraction used by parsed release entries
- version-link parsing (`[1.2.3]: https://...`)

## Dropped

- CLI entry points
- release automation helpers
- `to_raw_dict(...)`
- Starlette and Flask-RESTX helpers
- package version metadata and unrelated packaging files

See `LICENSE` in this folder for the upstream MIT license.
