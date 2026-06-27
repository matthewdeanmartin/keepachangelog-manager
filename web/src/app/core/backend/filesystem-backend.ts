// Filesystem backend: open a local clone with the File System Access API and
// read/write tickets/ + changelog.d/ in place. The developer commits via their
// own git — capabilities.pullRequest is false. See spec/web_remaining_phases.md §4 (W1c).
//
// Chromium-only API; feature-detect with isSupported() and hide this backend
// where it is unavailable.

import { RawFile } from '../fixtures';
import { BackendCapabilities, FileChange, RepoBackend, SaveResult } from './repo-backend';

const SCAN_DIRS = ['tickets', 'changelog.d'];

/** True when the browser exposes the File System Access directory picker. */
export function isFileSystemBackendSupported(): boolean {
  return typeof window !== 'undefined' && 'showDirectoryPicker' in window;
}

export class FilesystemBackend implements RepoBackend {
  readonly id = 'filesystem' as const;
  readonly capabilities: BackendCapabilities = { pullRequest: false, directWrite: true };

  constructor(private readonly root: FileSystemDirectoryHandle) {}

  /** Prompt for a repo root directory and build a backend for it. */
  static async pick(): Promise<FilesystemBackend> {
    if (!isFileSystemBackendSupported()) {
      throw new Error('This browser does not support the File System Access API.');
    }
    const root = await window.showDirectoryPicker({ mode: 'readwrite' });
    return new FilesystemBackend(root);
  }

  async scan(): Promise<RawFile[]> {
    const files: RawFile[] = [];
    for (const dir of SCAN_DIRS) {
      const handle = await this.getDir(dir, false);
      if (!handle) continue;
      for await (const [name, entry] of handle.entries()) {
        if (entry.kind !== 'file' || !name.endsWith('.md')) continue;
        const file = await (entry as FileSystemFileHandle).getFile();
        files.push({ path: `${dir}/${name}`, content: await file.text() });
      }
    }
    return files;
  }

  async save(changes: FileChange[]): Promise<SaveResult> {
    let written = 0;
    let deleted = 0;
    for (const change of changes) {
      const { dir, name } = splitPath(change.path);
      if (change.op === 'delete') {
        const handle = await this.getDir(dir, false);
        if (handle) {
          await handle.removeEntry(name).catch(() => undefined);
          deleted++;
        }
        continue;
      }
      const handle = await this.getDir(dir, true);
      if (!handle) continue;
      const fileHandle = await handle.getFileHandle(name, { create: true });
      const writable = await fileHandle.createWritable();
      await writable.write(change.content ?? '');
      await writable.close();
      written++;
    }
    const parts = [];
    if (written) parts.push(`wrote ${written}`);
    if (deleted) parts.push(`deleted ${deleted}`);
    return {
      kind: 'written',
      message: parts.length ? `Saved to disk (${parts.join(', ')}).` : 'No changes to save.',
    };
  }

  private async getDir(path: string, create: boolean): Promise<FileSystemDirectoryHandle | null> {
    let handle: FileSystemDirectoryHandle = this.root;
    for (const segment of path.split('/').filter(Boolean)) {
      try {
        handle = await handle.getDirectoryHandle(segment, { create });
      } catch {
        return null;
      }
    }
    return handle;
  }
}

/** Split "tickets/0001-x.md" -> { dir: "tickets", name: "0001-x.md" }. */
export function splitPath(path: string): { dir: string; name: string } {
  const idx = path.lastIndexOf('/');
  if (idx < 0) return { dir: '', name: path };
  return { dir: path.slice(0, idx), name: path.slice(idx + 1) };
}
