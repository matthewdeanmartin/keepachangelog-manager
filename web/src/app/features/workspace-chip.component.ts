import { Component, computed, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { RepoService } from '../core/repo.service';
import {
  ALL_PROJECTS,
  KatlMergedBackend,
  KatlServerBackend,
} from '../core/backend/katl-server-backend';
import { writeProjectOverride } from '../core/backend/dev-autoconnect';

const MODE_GLYPH: Record<string, string> = {
  'local-storage': '🧪',
  filesystem: '📁',
  github: '🐙',
  'katl-server': '🛰️',
};

/**
 * The always-visible answer to "what am I looking at?": mode glyph +
 * workspace label in the topbar, linking to /workspace. On a KATL server
 * connection the label becomes a project switcher fed by GET /projects.
 */
@Component({
  selector: 'app-workspace-chip',
  imports: [RouterLink],
  template: `
    <span class="chip" [title]="identity().detail">
      <span aria-hidden="true">{{ glyph() }}</span>
      @if (projects().length > 1) {
        <select
          aria-label="Switch project"
          [value]="selectedKey()"
          (change)="switchProject($event)"
        >
          @for (p of projects(); track p.key) {
            <option [value]="p.key">{{ p.key }}</option>
          }
          <option [value]="ALL_PROJECTS">All projects (read-only)</option>
        </select>
      } @else {
        <a routerLink="/workspace">{{ identity().label }}</a>
      }
    </span>
  `,
  styles: [
    `
      .chip {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: #323f4b;
        border-radius: 999px;
        padding: 0.25rem 0.75rem;
        font-size: 0.85rem;
        max-width: 18rem;
      }
      .chip a {
        color: #e4e7eb;
        text-decoration: none;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .chip a:hover {
        color: #fff;
        text-decoration: underline;
      }
      .chip select {
        background: #323f4b;
        color: #e4e7eb;
        border: 0;
        font: inherit;
        cursor: pointer;
        max-width: 14rem;
      }
      .chip select option {
        background: #fff;
        color: #1f2933;
      }
    `,
  ],
})
export class WorkspaceChipComponent {
  private repo = inject(RepoService);

  readonly ALL_PROJECTS = ALL_PROJECTS;
  readonly identity = this.repo.identity;
  readonly glyph = computed(() => MODE_GLYPH[this.repo.backendId()] ?? '❓');
  readonly projects = signal<{ key: string; name: string }[]>([]);
  /** The select's value: the active project key, or "*" for the merged view. */
  readonly selectedKey = computed(() => {
    // backendId() re-evaluates this when the backend switches.
    this.repo.backendId();
    const backend = this.repo.activeBackend;
    return backend instanceof KatlServerBackend ? backend.serverConfig.project : '';
  });

  constructor() {
    // Refresh the project list whenever a KATL server connection activates.
    effect(() => {
      if (this.repo.backendId() !== 'katl-server') {
        this.projects.set([]);
        return;
      }
      const backend = this.repo.activeBackend as KatlServerBackend;
      backend
        .listProjects()
        .then((projects) => this.projects.set(projects))
        .catch(() => this.projects.set([]));
    });
  }

  async switchProject(event: Event): Promise<void> {
    const key = (event.target as HTMLSelectElement).value;
    const backend = this.repo.activeBackend;
    if (!(backend instanceof KatlServerBackend) || key === backend.serverConfig.project) return;
    if (
      this.repo.dirtyPaths().length &&
      !confirm('Unsaved changes will be discarded. Switch project?')
    ) {
      // Snap the select back to the current project.
      (event.target as HTMLSelectElement).value = backend.serverConfig.project;
      return;
    }
    const next =
      key === ALL_PROJECTS ? new KatlMergedBackend(backend.serverConfig) : backend.withProject(key);
    await this.repo.useBackend(next);
    writeProjectOverride(key);
  }
}
