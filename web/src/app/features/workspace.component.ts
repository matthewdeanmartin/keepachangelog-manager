import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { RepoService } from '../core/repo.service';
import { GitHubClient, GitHubError } from '../core/backend/github-client';
import { GitHubBackend } from '../core/backend/github-backend';
import { LocalStorageBackend } from '../core/backend/local-storage-backend';
import {
  FilesystemBackend,
  isFileSystemBackendSupported,
} from '../core/backend/filesystem-backend';

const PREF_KEY = 'katl.workspace.pref.v1';

@Component({
  selector: 'app-workspace',
  imports: [FormsModule],
  template: `
    <h1>Workspace</h1>
    <p class="hint">
      Choose where KATL reads and writes <code>tickets/</code> and <code>changelog.d/</code>. The
      active backend is <strong>{{ repo.backendId() }}</strong
      >.
    </p>

    <section class="card">
      <h2>Sample (local)</h2>
      <p>Bundled demo tickets, persisted in your browser. No GitHub needed.</p>
      <button (click)="useLocal()">Use sample workspace</button>
    </section>

    @if (fsSupported) {
      <section class="card">
        <h2>Local folder</h2>
        <p>
          Open a local clone of your repo. KATL reads and writes
          <code>tickets/</code> and <code>changelog.d/</code> directly on disk — you commit with
          your own git. Nothing leaves your machine.
        </p>
        <button (click)="openFolder()" [disabled]="busy()">
          {{ busy() ? 'Opening…' : 'Open repo folder…' }}
        </button>
      </section>
    }

    <section class="card">
      <h2>GitHub repository</h2>
      <p class="warn">
        Paste a <strong>fine-grained PAT</strong> with Contents + Pull requests read/write. The
        token is kept <strong>in memory only</strong> and sent only to <code>api.github.com</code>.
        Refresh clears it.
      </p>
      <label
        >Token
        <input
          type="password"
          [(ngModel)]="token"
          placeholder="github_pat_… or ghp_…"
          autocomplete="off"
        />
      </label>
      <div class="row">
        <label>Owner <input [(ngModel)]="owner" placeholder="octocat" /></label>
        <label>Repo <input [(ngModel)]="repoName" placeholder="my-project" /></label>
        <label>Base branch <input [(ngModel)]="baseBranch" placeholder="main" /></label>
      </div>
      <button (click)="connect()" [disabled]="busy() || !token || !owner || !repoName">
        {{ busy() ? 'Connecting…' : 'Connect & scan' }}
      </button>
      @if (status()) {
        <p [class.err]="isError()" class="status">{{ status() }}</p>
      }
    </section>
  `,
  styles: [
    `
      .hint {
        color: #7b8794;
        font-size: 0.9rem;
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
      .warn {
        background: #fffbea;
        border: 1px solid #f0b429;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
        font-size: 0.8rem;
      }
      label {
        display: block;
        font-size: 0.8rem;
        color: #616e7c;
        margin-bottom: 0.6rem;
      }
      input {
        width: 100%;
        box-sizing: border-box;
        padding: 0.4rem;
        margin-top: 0.2rem;
        border: 1px solid #cbd2d9;
        border-radius: 4px;
        font: inherit;
      }
      .row {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        gap: 0.6rem;
      }
      button {
        background: #4da8da;
        color: #fff;
        border: 0;
        padding: 0.5rem 0.9rem;
        border-radius: 6px;
        cursor: pointer;
      }
      button:disabled {
        opacity: 0.4;
        cursor: not-allowed;
      }
      .status {
        font-size: 0.85rem;
        color: #2f855a;
      }
      .status.err {
        color: #cf1124;
      }
      @media (max-width: 700px) {
        .row {
          grid-template-columns: 1fr;
        }
      }
    `,
  ],
})
export class WorkspaceComponent {
  repo = inject(RepoService);
  private router = inject(Router);

  token = '';
  owner = '';
  repoName = '';
  baseBranch = 'main';

  busy = signal(false);
  status = signal('');
  isError = signal(false);
  fsSupported = isFileSystemBackendSupported();

  constructor() {
    const pref = this.readPref();
    if (pref) {
      this.owner = pref.owner;
      this.repoName = pref.repo;
      this.baseBranch = pref.baseBranch;
    }
  }

  async useLocal(): Promise<void> {
    await this.repo.useBackend(new LocalStorageBackend());
    this.router.navigate(['/board']);
  }

  async openFolder(): Promise<void> {
    this.busy.set(true);
    this.isError.set(false);
    this.status.set('');
    try {
      const backend = await FilesystemBackend.pick();
      await this.repo.useBackend(backend);
      this.status.set(`Opened local folder. Loaded ${this.repo.tasks().length} tickets.`);
      this.router.navigate(['/board']);
    } catch (e) {
      // AbortError is the user dismissing the picker — not worth surfacing.
      if ((e as Error)?.name !== 'AbortError') {
        this.isError.set(true);
        this.status.set(`Failed: ${(e as Error).message}`);
      }
    } finally {
      this.busy.set(false);
    }
  }

  async connect(): Promise<void> {
    this.busy.set(true);
    this.isError.set(false);
    this.status.set('');
    try {
      const client = new GitHubClient({ token: this.token });
      const login = await client.whoAmI();
      const backend = new GitHubBackend(client, {
        owner: this.owner.trim(),
        repo: this.repoName.trim(),
        baseBranch: this.baseBranch.trim() || 'main',
      });
      await this.repo.useBackend(backend);
      // Persist only the non-secret repo choice, never the token.
      this.writePref({ owner: this.owner, repo: this.repoName, baseBranch: this.baseBranch });
      this.status.set(`Connected as ${login}. Loaded ${this.repo.tasks().length} tickets.`);
      this.router.navigate(['/board']);
    } catch (e) {
      this.isError.set(true);
      this.status.set(
        e instanceof GitHubError
          ? `GitHub error (${e.status}): ${e.message}`
          : `Failed: ${(e as Error).message}`,
      );
    } finally {
      this.busy.set(false);
    }
  }

  private readPref(): { owner: string; repo: string; baseBranch: string } | null {
    if (typeof localStorage === 'undefined') return null;
    try {
      return JSON.parse(localStorage.getItem(PREF_KEY) ?? 'null');
    } catch {
      return null;
    }
  }

  private writePref(pref: { owner: string; repo: string; baseBranch: string }): void {
    if (typeof localStorage === 'undefined') return;
    localStorage.setItem(PREF_KEY, JSON.stringify(pref));
  }
}
