import { Component, inject, signal } from '@angular/core';
import { RepoService } from '../core/repo.service';

/**
 * Floating action bar shown when a PR backend has uncommitted edits. Direct-write
 * backends (local / filesystem) autosave, so this only surfaces for GitHub.
 */
@Component({
  selector: 'app-commit-bar',
  template: `
    @if (repo.canOpenPr() && repo.dirtyPaths().length) {
      <div class="bar">
        <span class="count">{{ repo.dirtyPaths().length }} pending change(s)</span>
        @if (result(); as r) {
          @if (r.url) {
            <a class="link" [href]="r.url" target="_blank" rel="noopener">{{ r.message }} ↗</a>
          } @else {
            <span class="msg">{{ r.message }}</span>
          }
        }
        <button (click)="commit()" [disabled]="busy()">
          {{ busy() ? 'Opening PR…' : 'Commit & open PR' }}
        </button>
      </div>
    }
  `,
  styles: [
    `
      .bar {
        position: fixed; bottom: 1rem; left: 50%; transform: translateX(-50%);
        display: flex; align-items: center; gap: 1rem;
        background: #1f2933; color: #fff; padding: 0.6rem 1rem;
        border-radius: 999px; box-shadow: 0 4px 16px rgba(0,0,0,0.25); z-index: 50;
      }
      .count { font-size: 0.85rem; }
      .link, .msg { font-size: 0.85rem; color: #9ad0f0; }
      .link { text-decoration: none; }
      button { background: #4da8da; color: #fff; border: 0; padding: 0.4rem 0.9rem; border-radius: 999px; cursor: pointer; }
      button:disabled { opacity: 0.5; cursor: not-allowed; }
    `,
  ],
})
export class CommitBarComponent {
  repo = inject(RepoService);
  busy = signal(false);
  result = signal<{ message: string; url?: string } | null>(null);

  async commit(): Promise<void> {
    this.busy.set(true);
    this.result.set(null);
    try {
      const r = await this.repo.commit();
      this.result.set({ message: r.message, url: r.url });
    } catch (e) {
      this.result.set({ message: `Failed: ${(e as Error).message}` });
    } finally {
      this.busy.set(false);
    }
  }
}
