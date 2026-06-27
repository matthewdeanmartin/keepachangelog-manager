import { Component, input, output } from '@angular/core';
import { TaskFragment, lookupCategory } from '../core/models';
import { emojiGlyph } from '../core/emoji';

/** A single draggable ticket card, shared by the status and milestone views. */
@Component({
  selector: 'app-ticket-card',
  template: `
    <article
      class="card"
      role="button"
      tabindex="0"
      draggable="true"
      (click)="openTask.emit(task())"
      (keydown.enter)="openTask.emit(task())"
      (keydown.space)="openTask.emit(task()); $event.preventDefault()"
      (dragstart)="dragStart.emit(task())"
      [class.warn]="task().lint.length"
    >
      <div class="cat" [title]="catTitle(task().category)">
        {{ catGlyph(task().category) }} {{ task().category }}
        @if (!ships(task().category)) {
          <em class="badge">internal</em>
        }
      </div>
      <div class="title">{{ task().title }}</div>
      <div class="meta">
        <span class="id">{{ task().taskId }}</span>
        @if (task().milestone) {
          <span class="ms">{{ task().milestone }}</span>
        }
        @for (a of task().assignees; track a) {
          <span class="who">{{ a }}</span>
        }
      </div>
      @if (task().lint.length) {
        <div class="lint">⚠ {{ task().lint.length }} hint(s)</div>
      }
    </article>
  `,
  styles: [
    `
      .card {
        background: #fff;
        border: 1px solid #e4e7eb;
        border-radius: 6px;
        padding: 0.6rem;
        margin-bottom: 0.5rem;
        cursor: grab;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
      }
      .card:hover {
        border-color: #4da8da;
      }
      .card:active {
        cursor: grabbing;
      }
      .card.warn {
        border-left: 3px solid #f0b429;
      }
      .cat {
        font-size: 0.7rem;
        color: #616e7c;
        text-transform: capitalize;
      }
      .badge {
        background: #9aa5b1;
        color: #fff;
        border-radius: 4px;
        padding: 0 0.3rem;
        font-style: normal;
        font-size: 0.6rem;
        margin-left: 0.3rem;
      }
      .title {
        font-weight: 600;
        font-size: 0.9rem;
        margin: 0.25rem 0;
      }
      .meta {
        display: flex;
        gap: 0.4rem;
        flex-wrap: wrap;
        font-size: 0.7rem;
        color: #7b8794;
      }
      .id {
        font-family: monospace;
      }
      .ms {
        background: #e0f0ff;
        color: #2779bd;
        border-radius: 4px;
        padding: 0 0.3rem;
      }
      .who {
        background: #e4e7eb;
        border-radius: 4px;
        padding: 0 0.3rem;
      }
      .lint {
        font-size: 0.7rem;
        color: #cb6e17;
        margin-top: 0.25rem;
      }
    `,
  ],
})
export class TicketCardComponent {
  task = input.required<TaskFragment>();
  openTask = output<TaskFragment>();
  dragStart = output<TaskFragment>();

  catGlyph = (key: string) => emojiGlyph(lookupCategory(key)?.emoji);
  catTitle = (key: string) => lookupCategory(key)?.title ?? key;
  ships = (key: string) => lookupCategory(key)?.shipsToChangelog ?? false;
}
