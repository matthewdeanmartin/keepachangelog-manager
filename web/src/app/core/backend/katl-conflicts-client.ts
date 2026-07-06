// Conflicts API for the KATL Co server:
//   GET  {base}/projects/{project}/conflicts             -> KatlConflict[]
//   POST {base}/projects/{project}/conflicts/{id}/resolve
//        {"choice": "ours"|"theirs"|"custom", "value"?}  -> {id, task_id, field, choice}
//
// Reuses the same config (URL / token / project) and FetchLike seam as the
// katl-server backend; errors surface as KatlServerError with the server's
// {"detail": "..."} message.

import { FetchLike } from './github-client';
import { katlRequest } from './katl-http';
import { KatlServerConfig } from './katl-server-backend';

export interface KatlConflict {
  id: number;
  task_id: string;
  /** Head-field name ("status", ...), "custom.<Key>", "body_md", or "__file__". */
  field: string;
  base: string | null;
  /** The server's value. */
  ours: string | null;
  /** The incoming value. */
  theirs: string | null;
  created_at: string;
}

export type ConflictChoice = 'ours' | 'theirs' | 'custom';

export interface ConflictResolution {
  id: number;
  task_id: string;
  field: string;
  choice: ConflictChoice;
}

export class KatlConflictsClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: FetchLike;

  constructor(private readonly config: KatlServerConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, '');
    this.fetchImpl = config.fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
  }

  private get conflictsPath(): string {
    return `${this.baseUrl}/projects/${encodeURIComponent(this.config.project)}/conflicts`;
  }

  listConflicts(): Promise<KatlConflict[]> {
    return katlRequest<KatlConflict[]>(
      this.fetchImpl,
      this.config.token,
      'GET',
      this.conflictsPath,
    );
  }

  resolveConflict(id: number, choice: ConflictChoice, value?: string): Promise<ConflictResolution> {
    const body: { choice: ConflictChoice; value?: string } = { choice };
    if (value !== undefined) body.value = value;
    return katlRequest<ConflictResolution>(
      this.fetchImpl,
      this.config.token,
      'POST',
      `${this.conflictsPath}/${id}/resolve`,
      body,
    );
  }
}
