// Bundled sample data so non-developers can use the app with zero GitHub setup.
// These mirror real tickets/*.md and changelog.d/*.md shapes.

export interface RawFile {
  path: string;
  content: string;
}

export const FIXTURE_TICKETS: RawFile[] = [
  {
    path: 'tickets/0001-oauth-mock-server.md',
    content: `# 0001-oauth-mock-server — Add OAuth mock server demo

- **Category:** added
- **Status:** in-progress
- **Tracker:** github#12
- **Labels:** oauth, testing
- **Assignees:** @matthew

---

## Summary

Add a minimal OAuth mock server demo for unattended tests.

## Acceptance Criteria

- [ ] Angular demo app can authenticate against mock server.
- [ ] Gatling script runs without human SSO interaction.
`,
  },
  {
    path: 'tickets/0002-gatling-criteria.md',
    content: `# 0002-gatling-criteria — Update Gatling acceptance criteria

- **Category:** changed
- **Status:** proposed
- **Labels:** testing
- **Assignees:** @sam

---

Clarify the Gatling acceptance criteria so QA and dev agree on pass/fail.
`,
  },
  {
    path: 'tickets/0003-protected-branch-fix.md',
    content: `# 0003-protected-branch-fix — Fix branch creation on protected base

- **Category:** fixed
- **Status:** done
- **Tracker:** github#34
- **Labels:** github, branches

---

Fixed branch creation when the selected base branch is protected.
`,
  },
  {
    path: 'tickets/0004-parser-refactor.md',
    content: `# 0004-parser-refactor — Refactor fragment parser internals

- **Category:** internal
- **Status:** done
- **Labels:** code-health

---

Internal refactor; no user-visible effect. Should NOT reach the changelog.
`,
  },
  {
    path: 'tickets/0005-blocked-spike.md',
    content: `# 0005-blocked-spike — Investigate GitHub App webhooks

- **Category:** spike
- **Status:** blocked
- **Assignees:** @matthew
- **Story Points:** 3

---

Blocked on org admin granting a test installation.
`,
  },
];

export const FIXTURE_CHANGELOG_FRAGMENTS: RawFile[] = [
  {
    path: 'changelog.d/oauth-mock-server.added.md',
    content: 'Added an OAuth mock server demo for unattended authentication tests.\n',
  },
  {
    path: 'changelog.d/protected-branch-fix.fixed.md',
    content: 'Fixed branch creation when the selected base branch is protected.\n',
  },
];
