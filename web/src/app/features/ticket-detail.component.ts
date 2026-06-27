import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { RepoService } from '../core/repo.service';
import {
  ALL_CATEGORIES,
  TASK_STATUSES,
  TaskFragment,
} from '../core/models';
import { renderTaskFragment } from '../core/fragment-parser';

@Component({
  selector: 'app-ticket-detail',
  imports: [FormsModule, RouterLink],
  template: `
    @if (model(); as m) {
      <div class="head">
        <a routerLink="/board" class="back">← Board</a>
        <div class="actions">
          <button (click)="save()">Save</button>
          @if (!isNew) {
            <button class="danger" (click)="remove()">Delete</button>
            <button class="ghost" (click)="makeChangelog(m)" [disabled]="!ships(m.category)">
              Create changelog fragment
            </button>
          }
        </div>
      </div>

      <div class="grid">
        <section class="form">
          <h2>Rigid head</h2>
          <label>Title
            <input [ngModel]="m.title" (ngModelChange)="patch({ title: $event })" />
          </label>
          <label>Task id
            <input [ngModel]="m.taskId" (ngModelChange)="patch({ taskId: $event })" [disabled]="!isNew" />
          </label>
          <div class="row">
            <label>Category
              <select [ngModel]="m.category" (ngModelChange)="patch({ category: $event })">
                @for (c of categories; track c.key) {
                  <option [value]="c.key">{{ c.title }} ({{ c.key }}){{ c.shipsToChangelog ? '' : ' · no-ship' }}</option>
                }
              </select>
            </label>
            <label>Status
              <select [ngModel]="m.status" (ngModelChange)="patch({ status: $event })">
                @for (s of statuses; track s) { <option [value]="s">{{ s }}</option> }
              </select>
            </label>
          </div>
          <label>Tracker
            <input [ngModel]="m.tracker" (ngModelChange)="patch({ tracker: $event })" placeholder="github#128" />
          </label>
          <label>Labels (comma-separated)
            <input [ngModel]="labelsText()" (ngModelChange)="patchList('labels', $event)" />
          </label>
          <label>Assignees (comma-separated)
            <input [ngModel]="assigneesText()" (ngModelChange)="patchList('assignees', $event)" />
          </label>
          <label>Milestone
            <input [ngModel]="m.milestone" (ngModelChange)="patch({ milestone: $event })" />
          </label>

          @if (customKeys(m).length) {
            <h3>Custom fields</h3>
            @for (k of customKeys(m); track k) {
              <label>{{ k }}
                <input [ngModel]="m.custom[k]" (ngModelChange)="patchCustom(k, $event)" />
              </label>
            }
          }
        </section>

        <section class="body">
          <h2>Free body (markdown)</h2>
          <textarea [ngModel]="m.body" (ngModelChange)="patch({ body: $event })" rows="20"></textarea>

          @if (m.lint.length) {
            <div class="lint">
              <strong>Lint</strong>
              <ul>@for (l of m.lint; track l) { <li>{{ l }}</li> }</ul>
            </div>
          }

          <details>
            <summary>Rendered file — <code>{{ m.path || 'tickets/' + m.taskId + '.md' }}</code></summary>
            <pre>{{ rendered() }}</pre>
          </details>
        </section>
      </div>
    } @else {
      <p>Ticket not found. <a routerLink="/board">Back to board</a></p>
    }
  `,
  styles: [
    `
      .head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
      .back { text-decoration: none; color: #4da8da; }
      .actions { display: flex; gap: 0.5rem; }
      button { background: #4da8da; color: #fff; border: 0; padding: 0.5rem 0.9rem; border-radius: 6px; cursor: pointer; }
      button.ghost { background: transparent; color: #4da8da; border: 1px solid #4da8da; }
      button.danger { background: #cf1124; }
      button:disabled { opacity: 0.4; cursor: not-allowed; }
      .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
      h2 { font-size: 0.9rem; color: #3e4c59; border-bottom: 1px solid #e4e7eb; padding-bottom: 0.3rem; }
      label { display: block; font-size: 0.8rem; color: #616e7c; margin-bottom: 0.6rem; }
      input, select, textarea { width: 100%; box-sizing: border-box; padding: 0.4rem; margin-top: 0.2rem; border: 1px solid #cbd2d9; border-radius: 4px; font: inherit; }
      textarea { font-family: monospace; font-size: 0.85rem; }
      .row { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
      .lint { background: #fffbea; border: 1px solid #f0b429; border-radius: 6px; padding: 0.5rem 0.75rem; font-size: 0.8rem; margin-top: 0.75rem; }
      pre { background: #1f2933; color: #e4e7eb; padding: 0.75rem; border-radius: 6px; overflow: auto; font-size: 0.8rem; }
      @media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
    `,
  ],
})
export class TicketDetailComponent {
  private repo = inject(RepoService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  categories = ALL_CATEGORIES;
  statuses = TASK_STATUSES;
  isNew = false;

  readonly model = signal<TaskFragment | undefined>(undefined);
  rendered = computed(() => {
    const m = this.model();
    return m ? renderTaskFragment(m) : '';
  });

  constructor() {
    const id = this.route.snapshot.paramMap.get('id');
    if (id === 'new') {
      this.isNew = true;
      this.model.set({
        taskId: this.repo.nextTaskId('new task'),
        path: '',
        title: 'New task',
        category: 'added',
        status: 'proposed',
        labels: [],
        assignees: [],
        custom: {},
        body: '## Summary\n\n',
        lint: [],
      });
    } else if (id) {
      const existing = this.repo.getTask(id);
      this.model.set(existing ? structuredClone(existing) : undefined);
    }
  }

  labelsText = () => (this.model()?.labels ?? []).join(', ');
  assigneesText = () => (this.model()?.assignees ?? []).join(', ');
  customKeys = (m: TaskFragment) => Object.keys(m.custom);
  ships = (key: string) => this.categories.find((c) => c.key === key)?.shipsToChangelog ?? false;

  patch(partial: Partial<TaskFragment>): void {
    const m = this.model();
    if (m) this.model.set({ ...m, ...partial });
  }

  patchList(field: 'labels' | 'assignees', value: string): void {
    const list = value.split(',').map((s) => s.trim()).filter(Boolean);
    this.patch({ [field]: list } as Partial<TaskFragment>);
  }

  patchCustom(key: string, value: string): void {
    const m = this.model();
    if (m) this.model.set({ ...m, custom: { ...m.custom, [key]: value } });
  }

  save(): void {
    const m = this.model();
    if (!m) return;
    if (this.isNew && !m.path) m.path = `tickets/${m.taskId}.md`;
    this.repo.saveTask(m);
    this.router.navigate(['/board']);
  }

  remove(): void {
    const m = this.model();
    if (m && confirm(`Delete ${m.taskId}?`)) {
      this.repo.deleteTask(m.taskId);
      this.router.navigate(['/board']);
    }
  }

  makeChangelog(m: TaskFragment): void {
    const path = this.repo.saveChangelogFragment(m.taskId, m.category, m.title);
    alert(`Created ${path}`);
    this.router.navigate(['/changelog']);
  }
}
