# 0005-tracker-profiles — GitHub & GitLab issue-field profiles

- **Category:** added
- **Status:** proposed
- **Tracker:** github#5
- **Labels:** tasks, interop
- **Weight:** 5

---

## Goal

Map fragment head fields to/from GitHub Issue and GitLab Issue objects via two
built-in profiles, reusing `changelogmanager/github.py` and
`changelogmanager/gitlab.py`. On-disk format is identical regardless of profile;
only import/export mapping differs.

This fragment carries GitLab's `Weight` on purpose: under the **GitHub** profile
it must fall through to `custom`; under **GitLab** it must map to `weight`.

## Acceptance criteria

- [ ] GitHub profile maps title/body/Status/Labels/Assignees/Milestone/Tracker
      per the spec table; `Status` → `state` + `state_reason`.
- [ ] GitLab profile maps the equivalents plus `Weight`, `Due Date`, `Confidential`.
- [ ] Fields unmapped by the active profile survive as `custom` (e.g. `Weight`
      under GitHub).
- [ ] `--profile github|gitlab` selects the mapping; GitHub default.

---

## Out of scope here

Live API sync. This ticket is purely the **mapping layer** (fragment ⇄ issue
payload), consistent with `spec/fragments.md` deferring API wiring to a later
phase. `Tracker` generalizes the existing `refs` concept in `TaskItem`.
