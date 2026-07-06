import { Component, effect, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { RepoService } from '../core/repo.service';
import { KatlServerBackend } from '../core/backend/katl-server-backend';
import { KatlConflict, KatlConflictsClient } from '../core/backend/katl-conflicts-client';
import {
  ConflictsScreen,
  FILE_CONFLICT_MESSAGE,
  conflictFieldLabel,
  isBodyConflict,
  isFileConflict,
} from '../core/conflicts';
import { ConflictCountService } from './conflict-count.service';

/** Resolve sync conflicts reported by the KATL Co server: per-field server vs
 * incoming values (ours/theirs/custom), plus remote file deletions. */
@Component({
  selector: 'app-conflicts',
  imports: [FormsModule, RouterLink],
  template: `
    <h1>Conflicts</h1>

    @if (!screen) {
      <p class="hint">
        Conflict resolution needs a KATL Co server connection. Open
        <a routerLink="/workspace">Workspace</a> and connect to a server first.
      </p>
    } @else {
      <p class="hint">
        Fields changed on both sides since the last sync. Pick the
        <strong>server</strong> value (ours), the <strong>incoming</strong> value (theirs), or type
        a custom one.
      </p>

      @if (screen.status()) {
        <p class="status" [class.err]="screen.isError()">{{ screen.status() }}</p>
      }

      @if (screen.loading()) {
        <p class="hint">Loading conflicts…</p>
      } @else if (screen.loaded() && !screen.conflicts().length) {
        <p class="empty">No open conflicts. 🎉</p>
      }

      @for (group of screen.groups(); track group.taskId) {
        <section class="card">
          <h2>{{ group.taskId }}</h2>
          @for (c of group.conflicts; track c.id) {
            <article class="conflict" [attr.data-field]="c.field">
              <h3>{{ fieldLabel(c.field) }}</h3>
              @if (isFile(c)) {
                <p class="filemsg">{{ fileMessage }}</p>
                <div class="actions">
                  <button (click)="resolve(c, 'ours')">Restore file</button>
                  <button class="danger" (click)="resolve(c, 'theirs')">Archive ticket</button>
                </div>
              } @else {
                <div class="sides" [class.stacked]="isBody(c)">
                  <div class="side">
                    <h4>Server (ours)</h4>
                    <pre>{{ c.ours ?? '(empty)' }}</pre>
                    <button (click)="resolve(c, 'ours')">Keep server</button>
                  </div>
                  <div class="side">
                    <h4>Incoming (theirs)</h4>
                    <pre>{{ c.theirs ?? '(empty)' }}</pre>
                    <button (click)="resolve(c, 'theirs')">Take incoming</button>
                  </div>
                </div>
                <div class="custom">
                  <label
                    >Custom value
                    <input
                      [(ngModel)]="customValues[c.id]"
                      [name]="'custom-' + c.id"
                      placeholder="type a value to use instead"
                    />
                  </label>
                  <button [disabled]="!customValues[c.id]" (click)="resolveCustom(c)">
                    Use custom
                  </button>
                </div>
              }
            </article>
          }
        </section>
      }
    }
  `,
  styles: [
    `
      .hint {
        color: #7b8794;
        font-size: 0.9rem;
      }
      .status {
        font-size: 0.85rem;
        color: #2f855a;
      }
      .status.err {
        color: #cf1124;
      }
      .empty {
        color: #7b8794;
      }
      .card {
        background: #f5f7fa;
        border-radius: 8px;
        padding: 1rem 1.25rem;
        margin-bottom: 1.25rem;
      }
      .card h2 {
        margin-top: 0;
        font-size: 1rem;
      }
      .conflict {
        border-top: 1px solid #e4e7eb;
        padding-top: 0.75rem;
        margin-top: 0.75rem;
      }
      .conflict h3 {
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        color: #616e7c;
        margin: 0 0 0.5rem;
      }
      .sides {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0.75rem;
      }
      .sides.stacked {
        grid-template-columns: 1fr;
      }
      .side h4 {
        margin: 0 0 0.3rem;
        font-size: 0.8rem;
        color: #616e7c;
      }
      pre {
        background: #fff;
        border: 1px solid #cbd2d9;
        border-radius: 6px;
        padding: 0.5rem 0.7rem;
        margin: 0 0 0.5rem;
        font-size: 0.85rem;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        max-height: 18rem;
        overflow: auto;
      }
      .filemsg {
        background: #fffbea;
        border: 1px solid #f0b429;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
        font-size: 0.85rem;
      }
      button {
        background: #4da8da;
        color: #fff;
        border: 0;
        padding: 0.4rem 0.8rem;
        border-radius: 6px;
        cursor: pointer;
      }
      button:disabled {
        opacity: 0.4;
        cursor: not-allowed;
      }
      button.danger {
        background: #cf1124;
      }
      .actions {
        display: flex;
        gap: 0.6rem;
      }
      .custom {
        display: flex;
        align-items: end;
        gap: 0.6rem;
        margin-top: 0.6rem;
      }
      .custom label {
        flex: 1;
        display: block;
        font-size: 0.8rem;
        color: #616e7c;
      }
      .custom input {
        width: 100%;
        box-sizing: border-box;
        padding: 0.4rem;
        margin-top: 0.2rem;
        border: 1px solid #cbd2d9;
        border-radius: 4px;
        font: inherit;
      }
      @media (max-width: 700px) {
        .sides {
          grid-template-columns: 1fr;
        }
      }
    `,
  ],
})
export class ConflictsComponent {
  private readonly repo = inject(RepoService);
  private readonly counts = inject(ConflictCountService);

  readonly screen: ConflictsScreen | null;
  readonly customValues: Record<number, string> = {};
  readonly fileMessage = FILE_CONFLICT_MESSAGE;

  constructor() {
    const backend = this.repo.activeBackend;
    this.screen =
      backend instanceof KatlServerBackend
        ? new ConflictsScreen(new KatlConflictsClient(backend.serverConfig))
        : null;
    if (this.screen) {
      const screen = this.screen;
      // Keep the nav badge in sync with the open-conflict count.
      effect(() => {
        if (screen.loaded()) this.counts.count.set(screen.conflicts().length);
      });
      void screen.load();
    }
  }

  fieldLabel(field: string): string {
    return conflictFieldLabel(field);
  }

  isFile(c: KatlConflict): boolean {
    return isFileConflict(c);
  }

  isBody(c: KatlConflict): boolean {
    return isBodyConflict(c);
  }

  resolve(c: KatlConflict, choice: 'ours' | 'theirs'): void {
    void this.screen?.resolve(c, choice);
  }

  resolveCustom(c: KatlConflict): void {
    const value = this.customValues[c.id];
    if (!value) return;
    void this.screen?.resolve(c, 'custom', value);
  }
}
