// The zero-setup demo backend: tickets + changelog fragments live in
// localStorage, seeded from bundled fixtures. Formalizes the original
// RepoService behavior as a RepoBackend. See spec/web_remaining_phases.md §4 (W1a).

import {
  FIXTURE_CHANGELOG_FRAGMENTS,
  FIXTURE_TICKETS,
  RawFile,
} from '../fixtures';
import {
  BackendCapabilities,
  FileChange,
  RepoBackend,
  SaveResult,
} from './repo-backend';

const STORAGE_KEY = 'katl.workspace.v1';

export class LocalStorageBackend implements RepoBackend {
  readonly id = 'local-storage' as const;
  readonly capabilities: BackendCapabilities = { pullRequest: false, directWrite: true };

  async scan(): Promise<RawFile[]> {
    const raw = this.read();
    if (raw) return raw;
    const seeded = [
      ...FIXTURE_TICKETS.map((f) => ({ ...f })),
      ...FIXTURE_CHANGELOG_FRAGMENTS.map((f) => ({ ...f })),
    ];
    this.write(seeded);
    return seeded;
  }

  async save(changes: FileChange[]): Promise<SaveResult> {
    const files = this.read() ?? [];
    const byPath = new Map(files.map((f) => [f.path, f]));
    for (const c of changes) {
      if (c.op === 'delete') byPath.delete(c.path);
      else byPath.set(c.path, { path: c.path, content: c.content ?? '' });
    }
    this.write([...byPath.values()]);
    return { kind: 'written', message: `Saved ${changes.length} file(s) locally.` };
  }

  /** Reset to the bundled sample workspace. */
  reset(): RawFile[] {
    const seeded = [
      ...FIXTURE_TICKETS.map((f) => ({ ...f })),
      ...FIXTURE_CHANGELOG_FRAGMENTS.map((f) => ({ ...f })),
    ];
    this.write(seeded);
    return seeded;
  }

  private read(): RawFile[] | null {
    if (typeof localStorage === 'undefined') return null;
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      // v1 stored {tickets, changelog}; normalize to a flat file list.
      if (Array.isArray(parsed)) return parsed as RawFile[];
      return [...(parsed.tickets ?? []), ...(parsed.changelog ?? [])];
    } catch {
      return null;
    }
  }

  private write(files: RawFile[]): void {
    if (typeof localStorage === 'undefined') return;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(files));
  }
}
