import {
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChildren,
} from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { RepoService } from '../core/repo.service';
import { TASK_STATUSES, TaskFragment } from '../core/models';
import { statusGlyph } from '../core/emoji';
import {
  BoardFilter,
  EMPTY_FILTER,
  distinctAssignees,
  distinctCategories,
  filterTasks,
  groupByMilestone,
} from '../core/board-filter';
import { TicketCardComponent } from './ticket-card.component';

interface Column {
  status: string;
  tasks: TaskFragment[];
}

@Component({
  selector: 'app-board',
  imports: [FormsModule, TicketCardComponent],
  template: `
    <div class="head">
      <h1>Board</h1>
      <div class="actions">
        <button (click)="newTask()">+ New ticket</button>
        <button class="ghost" (click)="resetSamples()">Reset to samples</button>
      </div>
    </div>

    <div class="toolbar">
      <input
        class="search"
        [ngModel]="filter().search"
        (ngModelChange)="patchFilter({ search: $event })"
        placeholder="Search title, id, labels…"
      />
      <select
        [ngModel]="filter().assignee"
        (ngModelChange)="patchFilter({ assignee: $event })"
        aria-label="Filter by assignee"
      >
        <option value="">All assignees</option>
        @for (a of assignees(); track a) {
          <option [value]="a">{{ a }}</option>
        }
      </select>
      <select
        [ngModel]="filter().category"
        (ngModelChange)="patchFilter({ category: $event })"
        aria-label="Filter by type"
      >
        <option value="">All types</option>
        @for (c of categories(); track c) {
          <option [value]="c">{{ c }}</option>
        }
      </select>
      <span class="spacer"></span>
      <div class="seg">
        <button [class.on]="view() === 'status'" (click)="view.set('status')">By status</button>
        <button [class.on]="view() === 'milestone'" (click)="view.set('milestone')">
          By milestone
        </button>
      </div>
    </div>

    @if (view() === 'status') {
      <div class="board">
        @for (col of columns(); track col.status) {
          <section
            class="col"
            [class.over]="dragOver() === col.status"
            (dragover)="onDragOver($event, col.status)"
            (dragleave)="dragOver.set('')"
            (drop)="onDrop(col.status)"
          >
            <h2>
              {{ glyph(col.status) }} {{ col.status }} <span>{{ col.tasks.length }}</span>
            </h2>
            @for (t of col.tasks; track t.taskId) {
              <app-ticket-card
                [task]="t"
                (openTask)="open($event)"
                (dragStart)="dragging.set($event)"
              />
            }
            @if (quickAddFor() === col.status) {
              <input
                class="quick"
                [(ngModel)]="quickText"
                (keydown.enter)="commitQuickAdd(col.status)"
                (keydown.escape)="cancelQuickAdd()"
                (blur)="cancelQuickAdd()"
                placeholder="Title, then Enter"
                #quickInput
              />
            } @else {
              <button class="add" (click)="startQuickAdd(col.status)">+ Quick add</button>
            }
          </section>
        }
      </div>
    } @else {
      <div class="lanes">
        @for (group of milestones(); track group.milestone) {
          <section class="lane">
            <h2>
              {{ group.milestone }} <span>{{ group.tasks.length }}</span>
            </h2>
            <div class="lane-cards">
              @for (t of group.tasks; track t.taskId) {
                <app-ticket-card [task]="t" (openTask)="open($event)" />
              }
            </div>
          </section>
        }
      </div>
    }
  `,
  styles: [
    `
      .head {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      h1 {
        margin: 0;
      }
      .actions {
        display: flex;
        gap: 0.5rem;
      }
      .toolbar {
        display: flex;
        gap: 0.5rem;
        align-items: center;
        margin: 0.75rem 0 1rem;
        flex-wrap: wrap;
      }
      .toolbar .search {
        flex: 1;
        min-width: 180px;
      }
      .spacer {
        flex: 1;
      }
      input,
      select {
        padding: 0.4rem;
        border: 1px solid #cbd2d9;
        border-radius: 4px;
        font: inherit;
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
      .seg {
        display: flex;
        border: 1px solid #4da8da;
        border-radius: 6px;
        overflow: hidden;
      }
      .seg button {
        background: #fff;
        color: #4da8da;
        border-radius: 0;
        padding: 0.4rem 0.7rem;
        font-size: 0.85rem;
      }
      .seg button.on {
        background: #4da8da;
        color: #fff;
      }
      .board {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 0.75rem;
        align-items: start;
      }
      .col {
        background: #f5f7fa;
        border-radius: 8px;
        padding: 0.5rem;
        min-height: 120px;
        transition: background 0.1s;
      }
      .col.over {
        background: #e0f0ff;
        outline: 2px dashed #4da8da;
      }
      .col h2 {
        font-size: 0.8rem;
        text-transform: capitalize;
        margin: 0.25rem 0 0.5rem;
        color: #3e4c59;
        display: flex;
        justify-content: space-between;
      }
      .col h2 span {
        background: #cbd2d9;
        border-radius: 10px;
        padding: 0 0.5rem;
        font-size: 0.7rem;
      }
      .add {
        background: transparent;
        color: #7b8794;
        border: 1px dashed #cbd2d9;
        width: 100%;
        padding: 0.35rem;
        font-size: 0.8rem;
      }
      .add:hover {
        color: #4da8da;
        border-color: #4da8da;
      }
      .quick {
        width: 100%;
        box-sizing: border-box;
      }
      .lanes {
        display: flex;
        flex-direction: column;
        gap: 1rem;
      }
      .lane {
        background: #f5f7fa;
        border-radius: 8px;
        padding: 0.75rem;
      }
      .lane h2 {
        font-size: 0.9rem;
        color: #3e4c59;
        margin: 0 0 0.5rem;
        display: flex;
        gap: 0.5rem;
        align-items: center;
      }
      .lane h2 span {
        background: #cbd2d9;
        border-radius: 10px;
        padding: 0 0.5rem;
        font-size: 0.7rem;
      }
      .lane-cards {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 0.5rem;
      }
      @media (max-width: 900px) {
        .board {
          grid-template-columns: repeat(2, 1fr);
        }
      }
    `,
  ],
})
export class BoardComponent {
  private repo = inject(RepoService);
  private router = inject(Router);

  glyph = statusGlyph;

  readonly filter = signal<BoardFilter>({ ...EMPTY_FILTER });
  readonly view = signal<'status' | 'milestone'>('status');
  readonly dragging = signal<TaskFragment | null>(null);
  readonly dragOver = signal<string>('');
  readonly quickAddFor = signal<string>('');
  quickText = '';

  // Focus the quick-add input when it appears (replaces the a11y-flagged autofocus).
  private quickInputs = viewChildren<ElementRef<HTMLInputElement>>('quickInput');

  constructor() {
    effect(() => {
      if (this.quickAddFor()) this.quickInputs()[0]?.nativeElement.focus();
    });
  }

  private visible = computed(() => filterTasks(this.repo.tasks(), this.filter()));
  assignees = computed(() => distinctAssignees(this.repo.tasks()));
  categories = computed(() => distinctCategories(this.repo.tasks()));

  columns = computed<Column[]>(() => {
    const tasks = this.visible();
    return TASK_STATUSES.map((status) => ({
      status,
      tasks: tasks.filter((t) => t.status === status),
    }));
  });

  milestones = computed(() => groupByMilestone(this.visible()));

  patchFilter(partial: Partial<BoardFilter>): void {
    this.filter.set({ ...this.filter(), ...partial });
  }

  open(t: TaskFragment): void {
    this.router.navigate(['/ticket', t.taskId]);
  }

  newTask(): void {
    this.router.navigate(['/ticket', 'new']);
  }

  // --- drag and drop ---

  onDragOver(event: DragEvent, status: string): void {
    event.preventDefault(); // allow drop
    this.dragOver.set(status);
  }

  onDrop(status: string): void {
    const card = this.dragging();
    this.dragOver.set('');
    this.dragging.set(null);
    if (card) this.repo.setTaskStatus(card.taskId, status);
  }

  // --- quick add ---

  startQuickAdd(status: string): void {
    this.quickText = '';
    this.quickAddFor.set(status);
  }

  cancelQuickAdd(): void {
    this.quickAddFor.set('');
  }

  commitQuickAdd(status: string): void {
    const title = this.quickText.trim();
    if (!title) {
      this.cancelQuickAdd();
      return;
    }
    const taskId = this.repo.nextTaskId(title);
    this.repo.saveTask({
      taskId,
      path: `tickets/${taskId}.md`,
      title,
      category: 'added',
      status,
      labels: [],
      assignees: [],
      custom: {},
      body: '## Summary\n\n',
      lint: [],
    });
    this.cancelQuickAdd();
  }

  resetSamples(): void {
    if (confirm('Discard local edits and reload sample tickets?')) {
      this.repo.loadFixtures();
    }
  }
}
