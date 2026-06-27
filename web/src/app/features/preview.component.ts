import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { RepoService } from '../core/repo.service';
import { buildUnreleasedGroups, renderUnreleasedMarkdown } from '../core/changelog-preview';
import { buildReadinessReport } from '../core/release-readiness';

@Component({
  selector: 'app-preview',
  imports: [RouterLink],
  template: `
    <h1>Release preview</h1>
    <p class="hint">
      What <code>fragments collect</code> would write to <code>[Unreleased]</code>: changelog
      fragments plus <code>done</code> shipping tickets. Non-shipping categories (internal, chore,
      docs, test, spike) and unknown categories are <strong>never</strong> shipped to the changelog.
    </p>

    <div class="grid">
      <section>
        <h2>Generated <code>CHANGELOG.md</code> · [Unreleased]</h2>
        <pre>{{ markdown() }}</pre>

        <div class="release">
          <h3>Cut a release</h3>
          @if (repo.canOpenPr()) {
            <p class="hint">
              Opens a single pull request with the pending fragment changes. CI runs
              <code>fragments collect</code> on merge to assemble <code>CHANGELOG.md</code> — this
              app never assembles it directly.
            </p>
            <button (click)="openReleasePr()" [disabled]="busy() || !repo.dirtyPaths().length">
              {{ busy() ? 'Opening PR…' : 'Open release PR' }}
            </button>
            @if (!repo.dirtyPaths().length && !result()) {
              <span class="muted">No pending changes to include.</span>
            }
            @if (result(); as r) {
              @if (r.url) {
                <a class="link" [href]="r.url" target="_blank" rel="noopener">{{ r.message }} ↗</a>
              } @else {
                <span [class.err]="r.error" class="muted">{{ r.message }}</span>
              }
            }
          } @else {
            <p class="muted">
              The active backend (<strong>{{ repo.backendId() }}</strong
              >) writes files directly — there is no PR step. Switch to the GitHub backend in
              <a routerLink="/workspace">Workspace</a> to open release PRs.
            </p>
          }
        </div>
      </section>

      <section>
        <h2>Readiness report</h2>
        @if (report().ready) {
          <div class="ok">Ready: every done shipping ticket has a fragment, no orphans. ✓</div>
        } @else {
          <div class="warn">Not release-ready — see the gaps below.</div>
        }

        @if (report().doneMissingFragment.length) {
          <h3>Done tickets without a changelog fragment</h3>
          <ul>
            @for (t of report().doneMissingFragment; track t.taskId) {
              <li>
                <code>{{ t.taskId }}</code> — {{ t.title }}
              </li>
            }
          </ul>
        }

        @if (report().orphanFragments.length) {
          <h3>Changelog fragments with no matching ticket</h3>
          <ul>
            @for (f of report().orphanFragments; track f.path) {
              <li>
                <code>{{ f.slug }}.{{ f.changeType }}</code> — {{ f.text }}
              </li>
            }
          </ul>
        }

        @if (report().stuckTickets.length) {
          <h3>In progress / blocked</h3>
          <ul class="muted-list">
            @for (t of report().stuckTickets; track t.taskId) {
              <li>
                <code>{{ t.taskId }}</code> — {{ t.title }} ({{ t.status }})
              </li>
            }
          </ul>
        }

        <h3>Counts</h3>
        <ul class="counts">
          <li>Tickets: {{ repo.tasks().length }}</li>
          <li>Done shipping tickets: {{ doneShipping() }}</li>
          <li>Changelog fragments: {{ repo.changelogFragments().length }}</li>
        </ul>

        @if (repo.dirtyPaths().length) {
          <h3>Pending changes (PR payload)</h3>
          <ul class="dirty">
            @for (p of repo.dirtyPaths(); track p) {
              <li>
                <code>{{ p }}</code>
              </li>
            }
          </ul>
        }
      </section>
    </div>
  `,
  styles: [
    `
      .hint {
        color: #7b8794;
        font-size: 0.85rem;
      }
      .grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 1.5rem;
        align-items: start;
      }
      h2 {
        font-size: 0.9rem;
        color: #3e4c59;
      }
      h3 {
        font-size: 0.8rem;
        color: #3e4c59;
        margin-bottom: 0.3rem;
      }
      pre {
        background: #1f2933;
        color: #e4e7eb;
        padding: 1rem;
        border-radius: 8px;
        overflow: auto;
        font-size: 0.85rem;
        white-space: pre-wrap;
      }
      .release {
        margin-top: 1rem;
        background: #f5f7fa;
        border-radius: 8px;
        padding: 0.75rem 1rem;
      }
      button {
        background: #4da8da;
        color: #fff;
        border: 0;
        padding: 0.5rem 0.9rem;
        border-radius: 6px;
        cursor: pointer;
      }
      button:disabled {
        opacity: 0.4;
        cursor: not-allowed;
      }
      .link {
        color: #2779bd;
        font-size: 0.85rem;
        margin-left: 0.5rem;
      }
      .muted {
        color: #7b8794;
        font-size: 0.85rem;
        margin-left: 0.5rem;
      }
      .err {
        color: #cf1124;
      }
      .warn {
        background: #fffbea;
        border: 1px solid #f0b429;
        border-radius: 6px;
        padding: 0.75rem;
        font-size: 0.85rem;
      }
      .ok {
        background: #e3f9e5;
        border: 1px solid #57ae5b;
        border-radius: 6px;
        padding: 0.75rem;
        font-size: 0.85rem;
      }
      ul {
        font-size: 0.85rem;
        margin-top: 0.2rem;
      }
      .muted-list {
        color: #7b8794;
      }
      code {
        font-family: monospace;
      }
      @media (max-width: 800px) {
        .grid {
          grid-template-columns: 1fr;
        }
      }
    `,
  ],
})
export class PreviewComponent {
  repo = inject(RepoService);

  busy = signal(false);
  result = signal<{ message: string; url?: string; error?: boolean } | null>(null);

  private groups = computed(() =>
    buildUnreleasedGroups(this.repo.changelogFragments(), this.repo.tasks()),
  );
  markdown = computed(() => renderUnreleasedMarkdown(this.groups()));
  report = computed(() => buildReadinessReport(this.repo.tasks(), this.repo.changelogFragments()));
  doneShipping = computed(() => this.repo.tasks().filter((t) => t.status === 'done').length);

  async openReleasePr(): Promise<void> {
    this.busy.set(true);
    this.result.set(null);
    try {
      const r = await this.repo.commit();
      this.result.set({ message: r.message, url: r.url });
    } catch (e) {
      this.result.set({ message: `Failed: ${(e as Error).message}`, error: true });
    } finally {
      this.busy.set(false);
    }
  }
}
