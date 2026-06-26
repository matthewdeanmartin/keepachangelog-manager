# Vendored code and forks

This page is for implementation details that matter when you are contributing,
debugging internals, or trying to understand the package layout.

## Project lineage

This repository is a fork of the original `keepachangelog-manager`, originally
written mostly by Kevin DeJong at TomTom International.

The published package in this fork is `keepachangelog-manager-fork`, while the
main CLI command remains `changelogmanager`.

## `keepachangelog` vs `keepachangelog-manager`

There are two related but different things in this repository:

| | `keepachangelog` | `keepachangelog-manager` |
|---|---|---|
| **Role** | Parser/serializer layer | User-facing CLI, GUI, validation, release, and automation layer |
| **Origin** | Vendored subset of [`Colin-b/keepachangelog`](https://github.com/Colin-b/keepachangelog) | This project |
| **Location** | `changelogmanager/vendor/keepachangelog/` | `changelogmanager/` |

`keepachangelog-manager` vendors only the small subset of upstream
`keepachangelog` that it needs for parsing and serialization.

## Other vendored code

This repository also vendors `llvm_diagnostics` under
`changelogmanager/llvm_diagnostics/` and adapts the import paths for local use.

That diagnostic layer is what powers the CLI's `llvm` and `github` error-format
output.

## Why this page exists

Most users do not need these implementation details to use the tool. The main
docs focus on workflows and behavior first, while this page keeps the internal
split documented in one place for contributors.
