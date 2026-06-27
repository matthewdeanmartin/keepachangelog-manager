// The storage seam. RepoService owns parsing + dirty-tracking; a RepoBackend
// owns IO. Three implementations plug in unchanged behind this interface:
//   * local-storage (the zero-setup demo)
//   * github       (PAT + branch + pull request)
//   * filesystem   (File System Access API, write a local clone in place)
//
// See spec/web_remaining_phases.md §4.

import { RawFile } from '../fixtures';

type BackendId = 'local-storage' | 'github' | 'filesystem';

/** A single create/update/delete of one repo-relative file. */
export interface FileChange {
  path: string;
  /** New content for create/update; ignored (may be omitted) for delete. */
  content?: string;
  op: 'upsert' | 'delete';
}

export interface SaveResult {
  /** Where the change landed, for the UI to link to. */
  kind: 'committed' | 'pull-request' | 'written';
  /** PR / commit URL when the backend produced one. */
  url?: string;
  /** Human summary, e.g. "Opened PR #42" or "Wrote 3 files". */
  message: string;
}

export interface BackendCapabilities {
  /** save() opens a pull request rather than writing directly. */
  pullRequest: boolean;
  /** save() writes files where they live (local FS / localStorage). */
  directWrite: boolean;
}

export interface RepoBackend {
  readonly id: BackendId;
  readonly capabilities: BackendCapabilities;

  /** Load every tracked tickets/* and changelog.d/* file. */
  scan(): Promise<RawFile[]>;

  /** Persist a batch of changes. The batch is RepoService's dirty set. */
  save(changes: FileChange[]): Promise<SaveResult>;
}
