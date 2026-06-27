import { Component, computed, inject } from '@angular/core';
import { Router } from '@angular/router';
import { RepoService } from '../core/repo.service';
import { TASK_STATUSES, TaskFragment, lookupCategory } from '../core/models';
import { emojiGlyph, statusGlyph } from '../core/emoji';

interface Column {
  status: string;
  tasks: TaskFragment[];
}

@Component({
  selector: 'app-board',
  template: `
    <div class="head">
      <h1>Board</h1>
      <div class="actions">
        <button (click)="newTask()">+ New ticket</button>
        <button class="ghost" (click)="resetSamples()">Reset to samples</button>
      </div>
    </div>
    <p class="hint">
      Task fragments live in <code>tickets/*.md</code>. PMs &amp; BAs write tickets here; on
      release, <code>done</code> shipping tickets flow into the changelog.
    </p>

    <div class="board">
      @for (col of columns(); track col.status) {
        <section class="col">
          <h2>{{ glyph(col.status) }} {{ col.status }} <span>{{ col.tasks.length }}</span></h2>
          @for (t of col.tasks; track t.taskId) {
            <article class="card" (click)="open(t)" [class.warn]="t.lint.length">
              <div class="cat" [title]="catTitle(t.category)">
                {{ catGlyph(t.category) }} {{ t.category }}
                @if (!ships(t.category)) { <em class="badge">no-ship</em> }
              </div>
              <div class="title">{{ t.title }}</div>
              <div class="meta">
                <span class="id">{{ t.taskId }}</span>
                @for (a of t.assignees; track a) { <span class="who">{{ a }}</span> }
              </div>
              @if (t.lint.length) { <div class="lint">⚠ {{ t.lint.length }} lint</div> }
            </article>
          }
          @if (!col.tasks.length) { <div class="empty">—</div> }
        </section>
      }
    </div>
  `,
  styles: [
    `
      .head { display: flex; justify-content: space-between; align-items: center; }
      h1 { margin: 0; }
      .actions { display: flex; gap: 0.5rem; }
      button { background: #4da8da; color: #fff; border: 0; padding: 0.5rem 0.9rem; border-radius: 6px; cursor: pointer; }
      button.ghost { background: transparent; color: #4da8da; border: 1px solid #4da8da; }
      .hint { color: #7b8794; font-size: 0.85rem; }
      .board { display: grid; grid-template-columns: repeat(6, 1fr); gap: 0.75rem; align-items: start; }
      .col { background: #f5f7fa; border-radius: 8px; padding: 0.5rem; min-height: 120px; }
      .col h2 { font-size: 0.8rem; text-transform: capitalize; margin: 0.25rem 0 0.5rem; color: #3e4c59; display: flex; justify-content: space-between; }
      .col h2 span { background: #cbd2d9; border-radius: 10px; padding: 0 0.5rem; font-size: 0.7rem; }
      .card { background: #fff; border: 1px solid #e4e7eb; border-radius: 6px; padding: 0.6rem; margin-bottom: 0.5rem; cursor: pointer; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
      .card:hover { border-color: #4da8da; }
      .card.warn { border-left: 3px solid #f0b429; }
      .cat { font-size: 0.7rem; color: #616e7c; text-transform: capitalize; }
      .badge { background: #f0b429; color: #fff; border-radius: 4px; padding: 0 0.3rem; font-style: normal; font-size: 0.6rem; margin-left: 0.3rem; }
      .title { font-weight: 600; font-size: 0.9rem; margin: 0.25rem 0; }
      .meta { display: flex; gap: 0.4rem; flex-wrap: wrap; font-size: 0.7rem; color: #7b8794; }
      .id { font-family: monospace; }
      .who { background: #e4e7eb; border-radius: 4px; padding: 0 0.3rem; }
      .lint { font-size: 0.7rem; color: #cb6e17; margin-top: 0.25rem; }
      .empty { color: #cbd2d9; text-align: center; padding: 0.5rem; }
      @media (max-width: 900px) { .board { grid-template-columns: repeat(2, 1fr); } }
    `,
  ],
})
export class BoardComponent {
  private repo = inject(RepoService);
  private router = inject(Router);

  columns = computed<Column[]>(() => {
    const tasks = this.repo.tasks();
    return TASK_STATUSES.map((status) => ({
      status,
      tasks: tasks.filter((t) => t.status === status),
    }));
  });

  glyph = statusGlyph;
  catGlyph = (key: string) => emojiGlyph(lookupCategory(key)?.emoji);
  catTitle = (key: string) => lookupCategory(key)?.title ?? key;
  ships = (key: string) => lookupCategory(key)?.shipsToChangelog ?? false;

  open(t: TaskFragment): void {
    this.router.navigate(['/ticket', t.taskId]);
  }

  newTask(): void {
    this.router.navigate(['/ticket', 'new']);
  }

  resetSamples(): void {
    if (confirm('Discard local edits and reload sample tickets?')) {
      this.repo.loadFixtures();
    }
  }
}
