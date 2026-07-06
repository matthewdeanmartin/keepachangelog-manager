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
import { KatlServerBackend, KatlServerError } from '../core/backend/katl-server-backend';

const PREF_KEY = 'katl.workspace.pref.v1';
const KATL_PREF_KEY = 'katl.workspace.katl-server.pref.v1';

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

    <section class="card">
      <h2>KATL Co server</h2>
      <p class="warn">
        Connect to a KATL Co server. The token is kept <strong>in memory only</strong> and sent only
        to the server URL below. Refresh clears it. The server stores tickets only —
        <code>changelog.d/</code> fragments stay local.
      </p>
      <label
        >Token
        <input
          type="password"
          [(ngModel)]="katlToken"
          placeholder="server token"
          autocomplete="off"
        />
      </label>
      <div class="row two">
        <label
          >Server URL <input [(ngModel)]="katlUrl" placeholder="https://katl.example.com" />
        </label>
        <label>Project key <input [(ngModel)]="katlProject" placeholder="my-project" /></label>
      </div>
      <button (click)="connectKatl()" [disabled]="busy() || !katlToken || !katlUrl || !katlProject">
        {{ busy() ? 'Connecting…' : 'Connect & scan' }}
      </button>
      @if (katlStatus()) {
        <p [class.err]="isError()" class="status">{{ katlStatus() }}</p>
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
      .row.two {
        grid-template-columns: 2fr 1fr;
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

  katlToken = '';
  katlUrl = '';
  katlProject = '';

  busy = signal(false);
  status = signal('');
  katlStatus = signal('');
  isError = signal(false);
  fsSupported = isFileSystemBackendSupported();

  constructor() {
    const pref = this.readPref();
    if (pref) {
      this.owner = pref.owner;
      this.repoName = pref.repo;
      this.baseBranch = pref.baseBranch;
    }
    const katlPref = this.readKatlPref();
    if (katlPref) {
      this.katlUrl = katlPref.baseUrl;
      this.katlProject = katlPref.project;
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
      const rl = await client.rateLimit().catch(() => null);
      const quota = rl ? ` API quota: ${rl.remaining}/${rl.limit}.` : '';
      this.status.set(`Connected as ${login}. Loaded ${this.repo.tasks().length} tickets.${quota}`);
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

  async connectKatl(): Promise<void> {
    this.busy.set(true);
    this.isError.set(false);
    this.katlStatus.set('');
    try {
      const backend = new KatlServerBackend({
        baseUrl: this.katlUrl.trim(),
        token: this.katlToken,
        project: this.katlProject.trim(),
      });
      await this.repo.useBackend(backend);
      // Persist only the non-secret server choice, never the token.
      this.writeKatlPref({ baseUrl: this.katlUrl.trim(), project: this.katlProject.trim() });
      this.katlStatus.set(`Connected. Loaded ${this.repo.tasks().length} tickets.`);
      this.router.navigate(['/board']);
    } catch (e) {
      this.isError.set(true);
      this.katlStatus.set(
        e instanceof KatlServerError
          ? `KATL server error (${e.status}): ${e.message}`
          : `Failed: ${(e as Error).message}`,
      );
    } finally {
      this.busy.set(false);
    }
  }

  private readKatlPref(): { baseUrl: string; project: string } | null {
    if (typeof localStorage === 'undefined') return null;
    try {
      return JSON.parse(localStorage.getItem(KATL_PREF_KEY) ?? 'null');
    } catch {
      return null;
    }
  }

  private writeKatlPref(pref: { baseUrl: string; project: string }): void {
    if (typeof localStorage === 'undefined') return;
    localStorage.setItem(KATL_PREF_KEY, JSON.stringify(pref));
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
