// KATL Co server backend: talk to the FastAPI ticket server.
//   GET    {base}/projects/{project}/export            -> { files: [{path, content}] }
//   POST   {base}/projects/{project}/import            -> { created, updated, lint }
//   DELETE {base}/projects/{project}/tickets/{task_id} -> 204
//
// The server only stores tickets today; changelog.d/* fragments never round-trip
// through it, so scan() returns exactly what the server sends. All requests are
// authenticated with the X-Katl-Token header. Errors arrive as JSON
// {"detail": "..."} and are surfaced as thrown Errors.

import { RawFile } from '../fixtures';
import {
  BackendCapabilities,
  FileChange,
  RepoBackend,
  SaveResult,
  WorkspaceIdentity,
} from './repo-backend';
import { FetchLike } from './github-client';
import { katlRequest, KatlServerError } from './katl-http';

export { KatlServerError };

export interface KatlServerConfig {
  /** Server base URL, e.g. https://katl.example.com (trailing slash tolerated). */
  baseUrl: string;
  /** Sent as X-Katl-Token on every request. */
  token: string;
  /** Project key, e.g. "my-project". */
  project: string;
  /** Override for tests; defaults to global fetch. */
  fetchImpl?: FetchLike;
}

export interface RepoLinkInfo {
  full_name: string;
  branch: string;
  tickets_dir: string;
  push_policy: string;
}

const TICKET_PATH_RE = /^tickets\/(.+)\.md$/;

/** The task id for a tickets/<id>.md path, or null for anything else. */
export function ticketIdFromPath(path: string): string | null {
  const m = TICKET_PATH_RE.exec(path);
  return m ? m[1] : null;
}

export class KatlServerBackend implements RepoBackend {
  readonly id = 'katl-server' as const;
  readonly capabilities: BackendCapabilities = { pullRequest: false, directWrite: true };

  protected readonly baseUrl: string;
  protected readonly fetchImpl: FetchLike;

  constructor(protected readonly config: KatlServerConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, '');
    this.fetchImpl = config.fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
  }

  /** The connection config, so sibling clients (e.g. conflicts) can reuse it. */
  get serverConfig(): KatlServerConfig {
    return this.config;
  }

  describe(): WorkspaceIdentity {
    let host = this.baseUrl;
    try {
      host = new URL(this.baseUrl).host;
    } catch {
      // Not a parseable URL (tests, relative bases): show it as-is.
    }
    return { label: this.config.project, detail: `KATL server at ${host}` };
  }

  /** The projects this connection can see, for the project switcher. */
  listProjects(): Promise<{ key: string; name: string }[]> {
    return this.request<{ key: string; name: string }[]>('GET', `${this.baseUrl}/projects`);
  }

  /** The same connection pointed at a different project. */
  withProject(project: string): KatlServerBackend {
    return new KatlServerBackend({ ...this.config, project });
  }

  /** The project's linked git repos (the server never echoes tokens). */
  listRepoLinks(): Promise<RepoLinkInfo[]> {
    return this.request<RepoLinkInfo[]>('GET', `${this.projectPath}/repo-links`);
  }

  private get projectPath(): string {
    return `${this.baseUrl}/projects/${encodeURIComponent(this.config.project)}`;
  }

  protected request<T = unknown>(method: string, url: string, body?: unknown): Promise<T> {
    return katlRequest<T>(this.fetchImpl, this.config.token, method, url, body);
  }

  /** Export the project's tickets. The server holds no changelog.d/* files. */
  async scan(): Promise<RawFile[]> {
    const data = await this.request<{
      files: { path: string; content: string; repo?: string | null }[];
    }>('GET', `${this.projectPath}/export`);
    return data.files.map((f) => ({ path: f.path, content: f.content, repo: f.repo }));
  }

  /** Import all upserts in one batch, then delete tickets one by one. */
  async save(changes: FileChange[]): Promise<SaveResult> {
    if (!changes.length) {
      return { kind: 'written', message: 'Nothing to save.' };
    }
    const upserts = changes.filter((c) => c.op === 'upsert');
    const deletes = changes.filter((c) => c.op === 'delete');

    let imported = 0;
    if (upserts.length) {
      const result = await this.request<{ created: number; updated: number }>(
        'POST',
        `${this.projectPath}/import`,
        { files: upserts.map((c) => ({ path: c.path, content: c.content ?? '' })) },
      );
      imported = result.created + result.updated;
    }

    let deleted = 0;
    const skipped: string[] = [];
    for (const change of deletes) {
      const taskId = ticketIdFromPath(change.path);
      if (taskId === null) {
        // The server only stores tickets; non-ticket deletes have nowhere to go.
        skipped.push(change.path);
        continue;
      }
      await this.request('DELETE', `${this.projectPath}/tickets/${encodeURIComponent(taskId)}`);
      deleted++;
    }

    let message = `Imported ${imported}, deleted ${deleted}`;
    if (skipped.length) {
      message += ` (skipped non-ticket deletes: ${skipped.join(', ')})`;
    }
    return { kind: 'written', message };
  }
}

/** The chip's "All projects" option — never a real project key (server keys
 * are ^[a-z0-9][a-z0-9-]*$). */
export const ALL_PROJECTS = '*';

/**
 * The merged all-projects view: one board over every project this connection
 * can see. Read-only — two projects may both own tickets/0001-x.md, so
 * path-keyed edits could misroute; editing stays per-project.
 */
export class KatlMergedBackend extends KatlServerBackend {
  override readonly capabilities: BackendCapabilities = {
    pullRequest: false,
    directWrite: false,
    readOnly: true,
  };

  constructor(config: Omit<KatlServerConfig, 'project'>) {
    super({ ...config, project: ALL_PROJECTS });
  }

  override describe(): WorkspaceIdentity {
    let host = this.baseUrl;
    try {
      host = new URL(this.baseUrl).host;
    } catch {
      // Not a parseable URL (tests, relative bases): show it as-is.
    }
    return { label: 'All projects', detail: `KATL server at ${host}` };
  }

  /** Every project's export, each file stamped with its project key. */
  override async scan(): Promise<RawFile[]> {
    const projects = await this.listProjects();
    const exports = await Promise.all(
      projects.map(async ({ key }) => {
        const data = await this.request<{
          files: { path: string; content: string; repo?: string | null }[];
        }>('GET', `${this.baseUrl}/projects/${encodeURIComponent(key)}/export`);
        return data.files.map((f) => ({
          path: f.path,
          content: f.content,
          repo: f.repo,
          project: key,
        }));
      }),
    );
    return exports.flat();
  }

  override async save(): Promise<SaveResult> {
    // RepoService never routes edits here (capabilities.readOnly); belt and
    // braces for any future caller.
    throw new Error('The all-projects view is read-only. Switch to a project to edit.');
  }
}
