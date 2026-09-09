import { Component, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { RepoService } from '../core/repo.service';
import { SiteModeService } from '../core/site-mode';
import { GitHubClient, GitHubError } from '../core/backend/github-client';
import { GitHubBackend } from '../core/backend/github-backend';
import { LocalStorageBackend } from '../core/backend/local-storage-backend';
import {
  FilesystemBackend,
  isFileSystemBackendSupported,
} from '../core/backend/filesystem-backend';
import {
  KatlServerBackend,
  KatlServerError,
  RepoLinkInfo,
} from '../core/backend/katl-server-backend';

const PREF_KEY = 'katl.workspace.pref.v1';
const KATL_PREF_KEY = 'katl.workspace.katl-server.pref.v1';

@Component({
  selector: 'app-workspace',
  imports: [FormsModule],
  template: `
    <h1>Workspace</h1>
    <p class="hint">
      Choose where KATL reads and writes <code>tickets/</code> and <code>changelog.d/</code>.
    </p>

    <section class="card connected">
      <h2>Connected now</h2>
      <p>
        <strong>{{ repo.identity().label }}</strong> — {{ repo.identity().detail }}.
        {{ repo.tasks().length }} ticket(s) loaded.
      </p>
    </section>

    <section class="card" [class.active]="repo.backendId() === 'local-storage'">
      <h2>
        Sample workspace
        @if (repo.backendId() === 'local-storage') {
          <em class="on">· active</em>
        }
      </h2>
      <p>
        A bundled demo workspace that lives entirely in this browser — works offline, needs no
        account, server, or setup. The right mode for trying KATL out.
      </p>
      <button (click)="useLocal()">Use sample workspace</button>
    </section>

    @if (fsSupported) {
      <section class="card" [class.active]="repo.backendId() === 'filesystem'">
        <h2>
          Local folder
          @if (repo.backendId() === 'filesystem') {
            <em class="on">· active</em>
          }
        </h2>
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

    <section class="card" [class.active]="repo.backendId() === 'github'">
      <h2>
        GitHub repository
        @if (repo.backendId() === 'github') {
          <em class="on">· active</em>
        }
      </h2>
      @if (githubConfigured() && !editGithub()) {
        <dl class="kv">
          <div>
            <dt>Repository</dt>
            <dd>{{ owner }}/{{ repoName }}</dd>
          </div>
          <div>
            <dt>Base branch</dt>
            <dd>{{ baseBranch || 'main' }}</dd>
          </div>
        </dl>
        @if (repo.backendId() !== 'github') {
          <p class="warn">
            The <strong>fine-grained PAT</strong> is kept in memory only and cleared on refresh —
            re-enter it to reconnect.
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
          <button (click)="connect()" [disabled]="busy() || !token">
            {{ busy() ? 'Connecting…' : 'Connect & scan' }}
          </button>
        }
        <button class="ghost" (click)="editGithub.set(true)">Change repository…</button>
      } @else {
        <p class="warn">
          Paste a <strong>fine-grained PAT</strong> with Contents + Pull requests read/write. The
          token is kept <strong>in memory only</strong> and sent only to
          <code>api.github.com</code>. Refresh clears it.
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
        @if (githubConfigured()) {
          <button class="ghost" (click)="editGithub.set(false)">Cancel</button>
        }
      }
      @if (status()) {
        <p [class.err]="isError()" class="status">{{ status() }}</p>
      }
    </section>

    @if (isLite()) {
      <section class="card upgrade">
        <h2>KATL Co server <span class="badge">Server mode</span></h2>
        <p>
          The hosted version of KATL: one project spanning several repos, team sync through a
          server, and conflict resolution — your board stays live without anyone pasting tokens.
          This free lite site doesn't connect to a server.
        </p>
        <a class="cta" href="https://katl.co" rel="noopener">Learn about server mode</a>
      </section>
    } @else {
      <section class="card" [class.active]="repo.backendId() === 'katl-server'">
        <h2>
          KATL Co server
          @if (repo.backendId() === 'katl-server') {
            <em class="on">· active</em>
          }
        </h2>
        @if (katlConfigured() && !editKatl()) {
          <dl class="kv">
            <div>
              <dt>Server URL</dt>
              <dd>{{ katlUrl }}</dd>
            </div>
            <div>
              <dt>Project</dt>
              <dd>{{ katlProject }}</dd>
            </div>
          </dl>
          @if (repo.backendId() === 'katl-server') {
            @if (repoLinks().length) {
              <p class="links-head">Linked repos of this project:</p>
              <ul class="links">
                @for (link of repoLinks(); track link.full_name) {
                  <li>
                    <code>{{ link.full_name }}</code> — {{ link.branch }},
                    <code>{{ link.tickets_dir }}/</code> [{{ link.push_policy }}]
                  </li>
                }
              </ul>
              <p class="hint">Manage links with <code>katl repo add/remove</code>.</p>
            }
          } @else {
            <p class="warn">
              The server token is kept <strong>in memory only</strong> and cleared on refresh —
              re-enter it to reconnect.
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
            <button (click)="connectKatl()" [disabled]="busy() || !katlToken">
              {{ busy() ? 'Connecting…' : 'Connect & scan' }}
            </button>
          }
          <button class="ghost" (click)="editKatl.set(true)">Change server…</button>
        } @else {
          <p class="warn">
            Connect to a KATL Co server. The token is kept <strong>in memory only</strong> and sent
            only to the server URL below. Refresh clears it. The server stores tickets only —
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
          <button
            (click)="connectKatl()"
            [disabled]="busy() || !katlToken || !katlUrl || !katlProject"
          >
            {{ busy() ? 'Connecting…' : 'Connect & scan' }}
          </button>
          @if (katlConfigured()) {
            <button class="ghost" (click)="editKatl.set(false)">Cancel</button>
          }
        }
        @if (katlStatus()) {
          <p [class.err]="isError()" class="status">{{ katlStatus() }}</p>
        }
      </section>
    }
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
      .card.active {
        border-left: 4px solid #4da8da;
      }
      .card.connected {
        background: #e0f0ff;
      }
      .card.upgrade {
        border: 1px dashed #4da8da;
        background: #fff;
      }
      .badge {
        background: #e0f0ff;
        color: #2680c2;
        border-radius: 4px;
        padding: 0.1rem 0.4rem;
        font-size: 0.75rem;
        font-weight: 600;
        vertical-align: middle;
      }
      a.cta {
        display: inline-block;
        background: #4da8da;
        color: #fff;
        text-decoration: none;
        padding: 0.5rem 0.9rem;
        border-radius: 6px;
      }
      .card.connected p {
        margin-bottom: 0;
      }
      .on {
        color: #4da8da;
        font-style: normal;
        font-weight: 400;
        font-size: 0.85rem;
      }
      .kv {
        margin: 0 0 0.75rem;
      }
      .kv div {
        display: flex;
        gap: 0.5rem;
        font-size: 0.85rem;
        margin-bottom: 0.25rem;
      }
      .kv dt {
        color: #616e7c;
        min-width: 7rem;
      }
      .kv dd {
        margin: 0;
        font-weight: 600;
        color: #1f2933;
      }
      .links-head {
        font-size: 0.85rem;
        color: #616e7c;
        margin-bottom: 0.25rem;
      }
      .links {
        margin: 0 0 0.5rem;
        padding-left: 1.25rem;
        font-size: 0.85rem;
      }
      button.ghost {
        background: transparent;
        color: #4da8da;
        border: 1px solid #4da8da;
        margin-left: 0.5rem;
      }
      button.ghost:first-of-type {
        margin-left: 0;
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
  isLite = inject(SiteModeService).isLite;
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

  // CRUD-truth: configured cards show state labels; forms appear only for
  // unconfigured cards or after an explicit "Change…".
  editGithub = signal(false);
  editKatl = signal(false);
  repoLinks = signal<RepoLinkInfo[]>([]);

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
    effect(() => {
      if (this.repo.backendId() !== 'katl-server') {
        this.repoLinks.set([]);
        return;
      }
      const backend = this.repo.activeBackend as KatlServerBackend;
      // Reflect what auto-connect/switching actually connected to.
      this.katlUrl = backend.serverConfig.baseUrl;
      this.katlProject = backend.serverConfig.project;
      backend
        .listRepoLinks()
        .then((links) => this.repoLinks.set(links))
        .catch(() => this.repoLinks.set([]));
    });
  }

  githubConfigured(): boolean {
    return !!(this.owner && this.repoName) || this.repo.backendId() === 'github';
  }

  katlConfigured(): boolean {
    return !!(this.katlUrl && this.katlProject) || this.repo.backendId() === 'katl-server';
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
      this.editGithub.set(false);
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
      this.editKatl.set(false);
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
