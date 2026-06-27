import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { RepoService } from '../core/repo.service';
import { ALL_CATEGORIES, TASK_STATUSES, TaskFragment } from '../core/models';
import { renderTaskFragment } from '../core/fragment-parser';
import {
  BodySection,
  CriterionRow,
  KNOWN_SECTIONS,
  findSection,
  parseCriteria,
  parseSections,
  serializeCriteria,
  serializeSections,
  setSection,
  unknownSections,
} from '../core/body-sections';
import { TICKET_TEMPLATES, templateById } from '../core/templates';

@Component({
  selector: 'app-ticket-detail',
  imports: [FormsModule, RouterLink],
  template: `
    @if (model(); as m) {
      <div class="head">
        <a routerLink="/board" class="back">← Board</a>
        <div class="actions">
          <label class="adv">
            <input type="checkbox" [ngModel]="advanced()" (ngModelChange)="advanced.set($event)" />
            Advanced
          </label>
          <button (click)="save()">Save</button>
          @if (!isNew) {
            <button class="danger" (click)="remove()">Delete</button>
            <button class="ghost" (click)="makeChangelog(m)" [disabled]="!ships(m.category)">
              Create changelog fragment
            </button>
          }
        </div>
      </div>

      @if (isNew) {
        <div class="templates">
          <span>Start from:</span>
          @for (t of templates; track t.id) {
            <button class="chip" (click)="applyTemplate(t.id)">{{ t.label }}</button>
          }
        </div>
      }

      <div class="grid">
        <section class="form">
          <h2>Details</h2>
          <label
            >Title
            <input [ngModel]="m.title" (ngModelChange)="patch({ title: $event })" />
          </label>
          <div class="row">
            <label
              >Type
              <select [ngModel]="m.category" (ngModelChange)="patch({ category: $event })">
                @for (c of categories; track c.key) {
                  <option [value]="c.key">
                    {{ c.title }}{{ c.shipsToChangelog ? '' : ' · internal' }}
                  </option>
                }
              </select>
            </label>
            <label
              >Status
              <select [ngModel]="m.status" (ngModelChange)="patch({ status: $event })">
                @for (s of statuses; track s) {
                  <option [value]="s">{{ s }}</option>
                }
              </select>
            </label>
          </div>
          <div class="row">
            <label
              >Assignees
              <input
                [ngModel]="assigneesText()"
                (ngModelChange)="patchList('assignees', $event)"
                placeholder="@you, @them"
              />
            </label>
            <label
              >Labels
              <input
                [ngModel]="labelsText()"
                (ngModelChange)="patchList('labels', $event)"
                placeholder="ui, api"
              />
            </label>
          </div>

          @if (advanced()) {
            <label
              >Task id
              <input
                [ngModel]="m.taskId"
                (ngModelChange)="patch({ taskId: $event })"
                [disabled]="!isNew"
              />
            </label>
            <div class="row">
              <label
                >Tracker
                <input
                  [ngModel]="m.tracker"
                  (ngModelChange)="patch({ tracker: $event })"
                  placeholder="github#128"
                />
              </label>
              <label
                >Milestone
                <input [ngModel]="m.milestone" (ngModelChange)="patch({ milestone: $event })" />
              </label>
            </div>
            @if (customKeys(m).length) {
              <h3>Custom fields</h3>
              @for (k of customKeys(m); track k) {
                <label
                  >{{ k }}
                  <input [ngModel]="m.custom[k]" (ngModelChange)="patchCustom(k, $event)" />
                </label>
              }
            }
          }
        </section>

        <section class="body">
          @if (!advanced()) {
            <h2>Summary</h2>
            <textarea
              rows="4"
              [ngModel]="summary()"
              (ngModelChange)="setBodySection(KNOWN.summary, $event)"
              placeholder="What is this ticket about?"
            ></textarea>

            <div class="ac-head">
              <h2>Acceptance criteria</h2>
              <button class="chip" (click)="addCriterion()">+ Add</button>
            </div>
            @for (row of criteria(); track $index) {
              <div class="ac-row">
                <input
                  type="checkbox"
                  [ngModel]="row.checked"
                  (ngModelChange)="setCriterion($index, { checked: $event })"
                />
                <input
                  [ngModel]="row.text"
                  (ngModelChange)="setCriterion($index, { text: $event })"
                  placeholder="A condition that must be true when done"
                />
                <button class="x" (click)="removeCriterion($index)" aria-label="Remove">✕</button>
              </div>
            }

            <h2>Notes</h2>
            <textarea
              rows="4"
              [ngModel]="notes()"
              (ngModelChange)="setBodySection(KNOWN.notes, $event)"
              placeholder="Anything else (optional)"
            ></textarea>

            @if (extraSections().length) {
              <h2>Other sections</h2>
              <p class="hint">Preserved as-is; switch to Advanced to edit the raw markdown.</p>
              @for (s of extraSections(); track s.heading) {
                <details class="extra">
                  <summary>{{ s.heading }}</summary>
                  <pre>{{ s.content }}</pre>
                </details>
              }
            }
          } @else {
            <h2>Free body (markdown)</h2>
            <textarea
              class="mono"
              rows="20"
              [ngModel]="m.body"
              (ngModelChange)="patch({ body: $event })"
            ></textarea>
            <details open>
              <summary>
                Rendered file — <code>{{ m.path || 'tickets/' + m.taskId + '.md' }}</code>
              </summary>
              <pre>{{ rendered() }}</pre>
            </details>
          }

          @if (m.lint.length) {
            <div class="lint">
              <strong>Hints</strong>
              <ul>
                @for (l of m.lint; track l) {
                  <li>{{ l }}</li>
                }
              </ul>
            </div>
          }
        </section>
      </div>
    } @else {
      <p>Ticket not found. <a routerLink="/board">Back to board</a></p>
    }
  `,
  styles: [
    `
      .head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
      }
      .back {
        text-decoration: none;
        color: #4da8da;
      }
      .actions {
        display: flex;
        gap: 0.5rem;
        align-items: center;
      }
      .adv {
        font-size: 0.8rem;
        color: #616e7c;
        display: flex;
        align-items: center;
        gap: 0.3rem;
      }
      .templates {
        display: flex;
        gap: 0.5rem;
        align-items: center;
        margin-bottom: 1rem;
        font-size: 0.85rem;
        color: #616e7c;
      }
      button {
        background: #4da8da;
        color: #fff;
        border: 0;
        padding: 0.5rem 0.9rem;
        border-radius: 6px;
        cursor: pointer;
      }
      button.ghost {
        background: transparent;
        color: #4da8da;
        border: 1px solid #4da8da;
      }
      button.danger {
        background: #cf1124;
      }
      button.chip {
        background: #e4e7eb;
        color: #3e4c59;
        padding: 0.25rem 0.6rem;
        font-size: 0.8rem;
      }
      button:disabled {
        opacity: 0.4;
        cursor: not-allowed;
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
        border-bottom: 1px solid #e4e7eb;
        padding-bottom: 0.3rem;
      }
      label {
        display: block;
        font-size: 0.8rem;
        color: #616e7c;
        margin-bottom: 0.6rem;
      }
      input,
      select,
      textarea {
        width: 100%;
        box-sizing: border-box;
        padding: 0.4rem;
        margin-top: 0.2rem;
        border: 1px solid #cbd2d9;
        border-radius: 4px;
        font: inherit;
      }
      textarea.mono {
        font-family: monospace;
        font-size: 0.85rem;
      }
      .row {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0.6rem;
      }
      .ac-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .ac-row {
        display: flex;
        gap: 0.5rem;
        align-items: center;
        margin-bottom: 0.4rem;
      }
      .ac-row input[type='checkbox'] {
        width: auto;
        margin: 0;
      }
      .ac-row .x {
        background: transparent;
        color: #cf1124;
        padding: 0.2rem 0.4rem;
      }
      .hint {
        color: #7b8794;
        font-size: 0.8rem;
        margin: 0.2rem 0;
      }
      .extra summary {
        cursor: pointer;
        font-size: 0.85rem;
        color: #3e4c59;
      }
      .lint {
        background: #fffbea;
        border: 1px solid #f0b429;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
        font-size: 0.8rem;
        margin-top: 0.75rem;
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
      @media (max-width: 800px) {
        .grid {
          grid-template-columns: 1fr;
        }
      }
    `,
  ],
})
export class TicketDetailComponent {
  private repo = inject(RepoService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  categories = ALL_CATEGORIES;
  statuses = TASK_STATUSES;
  templates = TICKET_TEMPLATES;
  KNOWN = KNOWN_SECTIONS;
  isNew = false;

  readonly model = signal<TaskFragment | undefined>(undefined);
  readonly advanced = signal(false);

  rendered = computed(() => {
    const m = this.model();
    return m ? renderTaskFragment(m) : '';
  });

  // Derive structured editors from the body — the body stays the source of
  // truth, so unknown sections are never lost.
  private sections = computed<BodySection[]>(() => parseSections(this.model()?.body ?? ''));
  summary = computed(() => findSection(this.sections(), KNOWN_SECTIONS.summary)?.content ?? '');
  notes = computed(() => findSection(this.sections(), KNOWN_SECTIONS.notes)?.content ?? '');
  criteria = computed<CriterionRow[]>(() =>
    parseCriteria(findSection(this.sections(), KNOWN_SECTIONS.acceptance)?.content ?? ''),
  );
  extraSections = computed(() => unknownSections(this.sections()));

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
    const list = value
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    this.patch({ [field]: list } as Partial<TaskFragment>);
  }

  patchCustom(key: string, value: string): void {
    const m = this.model();
    if (m) this.model.set({ ...m, custom: { ...m.custom, [key]: value } });
  }

  /** Write a structured section back into the body, preserving everything else. */
  setBodySection(heading: string, content: string): void {
    this.patch({ body: serializeSections(setSection(this.sections(), heading, content)) });
  }

  addCriterion(): void {
    this.writeCriteria([...this.criteria(), { checked: false, text: '' }]);
  }

  removeCriterion(index: number): void {
    this.writeCriteria(this.criteria().filter((_, i) => i !== index));
  }

  setCriterion(index: number, patch: Partial<CriterionRow>): void {
    this.writeCriteria(this.criteria().map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  private writeCriteria(rows: CriterionRow[]): void {
    this.setBodySection(KNOWN_SECTIONS.acceptance, serializeCriteria(rows));
  }

  applyTemplate(id: string): void {
    const t = templateById(id);
    const m = this.model();
    if (t && m) {
      this.model.set({ ...m, category: t.category, status: t.status, body: t.body });
    }
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
