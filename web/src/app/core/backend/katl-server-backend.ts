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
import { BackendCapabilities, FileChange, RepoBackend, SaveResult } from './repo-backend';
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

const TICKET_PATH_RE = /^tickets\/(.+)\.md$/;

/** The task id for a tickets/<id>.md path, or null for anything else. */
export function ticketIdFromPath(path: string): string | null {
  const m = TICKET_PATH_RE.exec(path);
  return m ? m[1] : null;
}

export class KatlServerBackend implements RepoBackend {
  readonly id = 'katl-server' as const;
  readonly capabilities: BackendCapabilities = { pullRequest: false, directWrite: true };

  private readonly baseUrl: string;
  private readonly fetchImpl: FetchLike;

  constructor(private readonly config: KatlServerConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, '');
    this.fetchImpl = config.fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
  }

  /** The connection config, so sibling clients (e.g. conflicts) can reuse it. */
  get serverConfig(): KatlServerConfig {
    return this.config;
  }

  private get projectPath(): string {
    return `${this.baseUrl}/projects/${encodeURIComponent(this.config.project)}`;
  }

  private request<T = unknown>(method: string, url: string, body?: unknown): Promise<T> {
    return katlRequest<T>(this.fetchImpl, this.config.token, method, url, body);
  }

  /** Export the project's tickets. The server holds no changelog.d/* files. */
  async scan(): Promise<RawFile[]> {
    const data = await this.request<{ files: { path: string; content: string }[] }>(
      'GET',
      `${this.projectPath}/export`,
    );
    return data.files.map((f) => ({ path: f.path, content: f.content }));
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
