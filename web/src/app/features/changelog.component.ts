import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RepoService } from '../core/repo.service';
import { SHIPPING_CATEGORIES, lookupCategory } from '../core/models';
import { emojiGlyph } from '../core/emoji';

@Component({
  selector: 'app-changelog',
  imports: [FormsModule],
  template: `
    <h1>Changelog fragments</h1>
    <p class="hint">
      One file per future changelog bullet in <code>changelog.d/&lt;slug&gt;.&lt;type&gt;.md</code>.
      Developers create these from their tickets; <code>fragments collect</code> assembles them
      into <code>CHANGELOG.md</code> on release.
    </p>

    <section class="add">
      <h2>New fragment</h2>
      <div class="row">
        <input [(ngModel)]="slug" placeholder="slug (e.g. oauth-mock-server)" />
        <select [(ngModel)]="type">
          @for (c of categories; track c.key) {
            <option [value]="c.key">{{ glyph(c.key) }} {{ c.key }}</option>
          }
        </select>
      </div>
      <textarea [(ngModel)]="text" rows="3" placeholder="The changelog bullet text (no leading '- ')"></textarea>
      <button (click)="add()" [disabled]="!slug.trim() || !text.trim()">Add fragment</button>
    </section>

    <table>
      <thead><tr><th>Type</th><th>Slug</th><th>Text</th><th></th></tr></thead>
      <tbody>
        @for (f of repo.changelogFragments(); track f.path) {
          <tr [class.warn]="f.lint.length">
            <td>{{ glyph(f.changeType) }} {{ f.changeType }}</td>
            <td class="mono">{{ f.slug }}</td>
            <td>{{ f.text }}</td>
            <td><button class="danger" (click)="remove(f.path)">✕</button></td>
          </tr>
        }
        @if (!repo.changelogFragments().length) {
          <tr><td colspan="4" class="empty">No changelog fragments yet.</td></tr>
        }
      </tbody>
    </table>
  `,
  styles: [
    `
      h1 { margin-bottom: 0.25rem; }
      .hint { color: #7b8794; font-size: 0.85rem; }
      .add { background: #f5f7fa; border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; }
      .add h2 { margin-top: 0; font-size: 0.9rem; }
      .row { display: flex; gap: 0.5rem; margin-bottom: 0.5rem; }
      input, select, textarea { padding: 0.4rem; border: 1px solid #cbd2d9; border-radius: 4px; font: inherit; }
      input { flex: 1; } textarea { width: 100%; box-sizing: border-box; font-family: monospace; }
      button { background: #4da8da; color: #fff; border: 0; padding: 0.45rem 0.9rem; border-radius: 6px; cursor: pointer; margin-top: 0.5rem; }
      button:disabled { opacity: 0.4; }
      button.danger { background: #cf1124; padding: 0.2rem 0.5rem; margin: 0; }
      table { width: 100%; border-collapse: collapse; }
      th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid #e4e7eb; font-size: 0.9rem; }
      .mono { font-family: monospace; }
      tr.warn { background: #fffbea; }
      .empty { color: #cbd2d9; text-align: center; }
    `,
  ],
})
export class ChangelogComponent {
  repo = inject(RepoService);
  categories = SHIPPING_CATEGORIES;

  slug = '';
  type = 'added';
  text = '';

  glyph = (key: string) => emojiGlyph(lookupCategory(key)?.emoji);

  add(): void {
    this.repo.saveChangelogFragment(this.slug, this.type, this.text.trim());
    this.slug = '';
    this.text = '';
  }

  remove(path: string): void {
    this.repo.deleteChangelogFragment(path);
  }
}
