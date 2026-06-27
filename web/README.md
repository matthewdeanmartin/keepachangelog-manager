# KATL — Keep A Task Log (web app)

A browser-only Angular app — a "mini-Jira" for repo-native task and changelog
fragments. It is a UI over the **same on-disk formats** the
[`keepachangelog-manager`](../) Python CLI uses, so anything written here
round-trips with the CLI and CI.

## Who it's for

- **PMs / BAs / non-developers** write **task fragments** (tickets) on a Jira-like
  board. No Markdown or Git knowledge required.
- Every ~3 weeks, tickets merge to `develop`.
- **Developers** fork a ticket and turn it into a **changelog fragment**.
- On release date, `done` shipping tickets + changelog fragments flow into
  `CHANGELOG.md` via the CLI's `fragments collect` / `tasks assemble`.

## The two artifacts (grounded in the real tool)

| Artifact | On disk | Shape |
| --- | --- | --- |
| Task fragment | `tickets/*.md` | rigid markdown head (`- **Key:** value`) + free body, split on the first column-0 `---` outside a code fence — see [`spec/TASK_FRAGMENTS_AND_UI.md`](../spec/TASK_FRAGMENTS_AND_UI.md) |
| Changelog fragment | `changelog.d/<slug>.<type>.md` | bullet text; type in filename — see [`spec/fragments.md`](../spec/fragments.md) |

Categories match `changelogmanager/change_types.py`: six **shipping** Keep a
Changelog types (`added`, `changed`, `deprecated`, `removed`, `fixed`,
`security`) plus five **non-shipping** types (`internal`, `chore`, `docs`,
`test`, `spike`) that are tracked but never reach the public changelog.

> Note: the original `spec/web_gui.md` draft invented a `.katl/` YAML-front-matter
> format. This app deliberately does **not** use it — it uses the real formats
> above so files interoperate with the CLI.

## Screens

- **Board** — tickets grouped by status (proposed → done), Jira-style columns.
- **Ticket** — edit the rigid head as a form + the free body as Markdown; live
  rendered-file preview; lint warnings; "Create changelog fragment" shortcut.
- **Changelog** — manage `changelog.d/*` fragments.
- **Release preview** — the `[Unreleased]` section `fragments collect` would
  produce, plus a consistency report (done tickets missing a changelog fragment).

## Data backend

This build is **local-first**: it ships sample tickets and persists edits to
`localStorage`, so non-developers can use it with zero GitHub setup. The
`RepoService` tracks dirty files; a future GitHub layer (Octokit + PAT) can
scan a repo into the same model and turn `dirtyPaths()` into a branch + PR
without changing the UI.

## Develop

```sh
cd web
npm install
npm start          # ng serve, http://localhost:4200
npm test           # vitest run — pure-logic specs, runs in Node, no browser
npm run test:watch # vitest in watch mode
npm run build -- --base-href=/keepachangelog-manager/
```

Deployed to GitHub Pages by [`.github/workflows/web-pages.yml`](../.github/workflows/web-pages.yml).
