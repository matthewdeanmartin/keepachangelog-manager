import { Component, computed, inject } from '@angular/core';
import { RepoService } from '../core/repo.service';
import {
  buildUnreleasedGroups,
  renderUnreleasedMarkdown,
  tasksMissingChangelog,
} from '../core/changelog-preview';

@Component({
  selector: 'app-preview',
  template: `
    <h1>Release preview</h1>
    <p class="hint">
      What <code>fragments collect</code> would write to <code>[Unreleased]</code>: changelog
      fragments plus <code>done</code> shipping tickets. Non-shipping categories
      (internal, chore, docs, test, spike) are excluded.
    </p>

    <div class="grid">
      <section>
        <h2>Generated <code>CHANGELOG.md</code> · [Unreleased]</h2>
        <pre>{{ markdown() }}</pre>
      </section>

      <section>
        <h2>Consistency report</h2>
        @if (missing().length) {
          <div class="warn">
            <strong>Done tickets without a changelog fragment</strong>
            <ul>
              @for (t of missing(); track t.taskId) {
                <li><code>{{ t.taskId }}</code> — {{ t.title }}</li>
              }
            </ul>
          </div>
        } @else {
          <div class="ok">Every done shipping ticket has a changelog fragment. ✓</div>
        }

        <h3>Counts</h3>
        <ul class="counts">
          <li>Tickets: {{ repo.tasks().length }}</li>
          <li>Done shipping tickets: {{ doneShipping() }}</li>
          <li>Changelog fragments: {{ repo.changelogFragments().length }}</li>
        </ul>

        @if (repo.dirtyPaths().length) {
          <h3>Pending changes (PR payload)</h3>
          <p class="hint">These files would be committed on a branch + PR by the GitHub layer.</p>
          <ul class="dirty">
            @for (p of repo.dirtyPaths(); track p) { <li><code>{{ p }}</code></li> }
          </ul>
        }
      </section>
    </div>
  `,
  styles: [
    `
      .hint { color: #7b8794; font-size: 0.85rem; }
      .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
      h2 { font-size: 0.9rem; color: #3e4c59; }
      pre { background: #1f2933; color: #e4e7eb; padding: 1rem; border-radius: 8px; overflow: auto; font-size: 0.85rem; white-space: pre-wrap; }
      .warn { background: #fffbea; border: 1px solid #f0b429; border-radius: 6px; padding: 0.75rem; font-size: 0.85rem; }
      .ok { background: #e3f9e5; border: 1px solid #57ae5b; border-radius: 6px; padding: 0.75rem; font-size: 0.85rem; }
      .counts li, .dirty li { font-size: 0.85rem; }
      code { font-family: monospace; }
      @media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
    `,
  ],
})
export class PreviewComponent {
  repo = inject(RepoService);

  private groups = computed(() =>
    buildUnreleasedGroups(this.repo.changelogFragments(), this.repo.tasks()),
  );
  markdown = computed(() => renderUnreleasedMarkdown(this.groups()));
  missing = computed(() =>
    tasksMissingChangelog(this.repo.tasks(), this.repo.changelogFragments()),
  );
  doneShipping = computed(
    () => this.repo.tasks().filter((t) => t.status === 'done').length,
  );
}
