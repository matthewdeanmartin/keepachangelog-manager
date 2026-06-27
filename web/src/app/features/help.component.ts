import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

/** In-app documentation: getting started, token permissions, fragment format,
 * security model, and known limitations. See spec/web_remaining_phases.md §8 (W5). */
@Component({
  selector: 'app-help',
  imports: [RouterLink],
  template: `
    <h1>About KATL</h1>
    <p class="lead">
      KATL — <em>Keep A Task Log</em> — is a browser-only editor for repo-native task and changelog
      fragments. It is a friendly UI over the exact files the
      <code>keepachangelog-manager</code> CLI reads, so anything you write here round-trips with the
      CLI and CI.
    </p>

    <nav class="toc" aria-label="Sections">
      <a href="#start">Getting started</a>
      <a href="#tokens">Token permissions</a>
      <a href="#format">Fragment format</a>
      <a href="#security">Security model</a>
      <a href="#limits">Known limitations</a>
    </nav>

    <section id="start">
      <h2>Getting started</h2>
      <ol>
        <li>Open <a routerLink="/workspace">Workspace</a> and pick where your tickets live.</li>
        <li>
          <strong>Sample</strong> needs nothing — bundled demo tickets in your browser.
          <strong>Local folder</strong> opens a clone on disk (Chromium).
          <strong>GitHub</strong> reads a repo with a token and writes via a pull request.
        </li>
        <li>Use the <a routerLink="/board">Board</a> to create and move tickets.</li>
        <li>
          Mark a <code>done</code> shipping ticket and click <em>Create changelog fragment</em>, or
          add one directly under <a routerLink="/changelog">Changelog</a>.
        </li>
        <li>
          Check <a routerLink="/preview">Release preview</a> for the generated
          <code>[Unreleased]</code> section and readiness report, then open a release PR.
        </li>
      </ol>
    </section>

    <section id="tokens">
      <h2>Token permissions (GitHub backend)</h2>
      <p>Use a <strong>fine-grained PAT</strong> scoped to just the repo you edit:</p>
      <ul>
        <li><strong>Contents</strong> — read &amp; write</li>
        <li><strong>Pull requests</strong> — read &amp; write</li>
        <li><strong>Metadata</strong> — read (granted automatically)</li>
      </ul>
      <p class="muted">Revoke the token when you are done testing.</p>
    </section>

    <section id="format">
      <h2>Fragment format</h2>
      <p>
        <strong>Task fragments</strong> live in <code>tickets/*.md</code>: a rigid markdown head
        plus a free body, split on the first column-0 <code>---</code> outside a code fence.
      </p>
      <pre>{{ ticketExample }}</pre>
      <p>
        <strong>Changelog fragments</strong> live in
        <code>changelog.d/&lt;slug&gt;.&lt;type&gt;.md</code> — the bullet text, with the Keep a
        Changelog type in the filename.
      </p>
      <pre>
changelog.d/oauth-mock-server.added.md →
"Added an OAuth mock server demo for unattended tests."</pre>
      <p>
        Shipping types: <code>added changed deprecated removed fixed security</code>. Non-shipping
        (tracked but never in the changelog): <code>internal chore docs test spike</code>. Unknown
        types are treated as non-shipping, so a typo never leaks into a public changelog.
      </p>
    </section>

    <section id="security">
      <h2>Security model</h2>
      <ul>
        <li>
          No backend, no KATL server — your token is never sent anywhere except
          <code>api.github.com</code>.
        </li>
        <li>The token is kept <strong>in memory only</strong> and cleared on refresh.</li>
        <li>
          Browser-held tokens still carry XSS risk; prefer fine-grained, repo-scoped PATs and revoke
          them after use.
        </li>
        <li>The app writes to a branch and opens a PR — it never pushes to your base branch.</li>
      </ul>
    </section>

    <section id="limits">
      <h2>Known limitations</h2>
      <ul>
        <li>
          The app previews <code>[Unreleased]</code> but never assembles <code>CHANGELOG.md</code> —
          CI's <code>fragments collect</code> does that on merge.
        </li>
        <li>The local-folder backend needs a Chromium-based browser (File System Access API).</li>
        <li>No live conflict detection yet if a file changes remotely after a scan.</li>
      </ul>
    </section>
  `,
  styles: [
    `
      .lead {
        font-size: 1rem;
        color: #3e4c59;
      }
      .toc {
        display: flex;
        gap: 1rem;
        flex-wrap: wrap;
        background: #f5f7fa;
        padding: 0.6rem 0.9rem;
        border-radius: 8px;
        margin-bottom: 1rem;
      }
      .toc a {
        color: #2779bd;
        text-decoration: none;
        font-size: 0.85rem;
      }
      section {
        margin-bottom: 1.5rem;
      }
      h2 {
        font-size: 1rem;
        color: #1f2933;
        border-bottom: 1px solid #e4e7eb;
        padding-bottom: 0.3rem;
      }
      pre {
        background: #1f2933;
        color: #e4e7eb;
        padding: 0.75rem;
        border-radius: 6px;
        overflow: auto;
        font-size: 0.8rem;
        white-space: pre-wrap;
      }
      code {
        font-family: monospace;
      }
      .muted {
        color: #7b8794;
        font-size: 0.85rem;
      }
      a {
        color: #2779bd;
      }
    `,
  ],
})
export class HelpComponent {
  ticketExample = `# 0042-network-config — Add a Network Config dialog

- **Category:** added
- **Status:** in-progress
- **Assignees:** @you

---

## Summary

What this ticket is about.

## Acceptance Criteria

- [ ] A condition that must be true when done.`;
}
