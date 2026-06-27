import { describe, it, expect } from 'vitest';
import { FilesystemBackend, splitPath } from './filesystem-backend';
import { FileChange } from './repo-backend';

// Minimal in-memory fakes of the File System Access handles. The backend only
// uses getDirectoryHandle / getFileHandle / entries / getFile / createWritable /
// removeEntry, so we implement just those.

class FakeWritable {
  constructor(private file: FakeFile) {}
  async write(data: string) {
    this.file.content = data;
  }
  closed = false;
  async close() {
    this.closed = true;
  }
}

class FakeFile {
  kind = 'file' as const;
  constructor(
    public name: string,
    public content: string,
  ) {}
  async getFile() {
    const content = this.content;
    return { text: async () => content } as File;
  }
  async createWritable() {
    return new FakeWritable(this) as unknown as FileSystemWritableFileStream;
  }
}

class FakeDir {
  kind = 'directory' as const;
  dirs = new Map<string, FakeDir>();
  files = new Map<string, FakeFile>();
  constructor(public name: string) {}

  async getDirectoryHandle(name: string, opts?: { create?: boolean }) {
    let d = this.dirs.get(name);
    if (!d) {
      if (!opts?.create) throw new Error('NotFound');
      d = new FakeDir(name);
      this.dirs.set(name, d);
    }
    return d as unknown as FileSystemDirectoryHandle;
  }
  async getFileHandle(name: string, opts?: { create?: boolean }) {
    let f = this.files.get(name);
    if (!f) {
      if (!opts?.create) throw new Error('NotFound');
      f = new FakeFile(name, '');
      this.files.set(name, f);
    }
    return f as unknown as FileSystemFileHandle;
  }
  async removeEntry(name: string) {
    if (!this.files.delete(name)) throw new Error('NotFound');
  }
  async *entries(): AsyncGenerator<[string, FakeFile]> {
    for (const [name, file] of this.files) yield [name, file];
  }
}

function repoWith(files: Record<string, string>): FakeDir {
  const root = new FakeDir('');
  for (const [path, content] of Object.entries(files)) {
    const { dir, name } = splitPath(path);
    let d = root;
    for (const seg of dir.split('/').filter(Boolean)) {
      if (!d.dirs.has(seg)) d.dirs.set(seg, new FakeDir(seg));
      d = d.dirs.get(seg)!;
    }
    d.files.set(name, new FakeFile(name, content));
  }
  return root;
}

describe('splitPath', () => {
  it('splits dir and name', () => {
    expect(splitPath('tickets/0001-x.md')).toEqual({ dir: 'tickets', name: '0001-x.md' });
  });
  it('handles a bare filename', () => {
    expect(splitPath('x.md')).toEqual({ dir: '', name: 'x.md' });
  });
});

describe('FilesystemBackend.scan', () => {
  it('reads .md files from tickets/ and changelog.d/ only', async () => {
    const root = repoWith({
      'tickets/0001-a.md': 'A',
      'changelog.d/x.added.md': 'X',
      'tickets/README.txt': 'ignore me',
      'src/main.ts': 'ignore',
    });
    const backend = new FilesystemBackend(root as unknown as FileSystemDirectoryHandle);
    const files = await backend.scan();
    expect(files.map((f) => f.path).sort()).toEqual([
      'changelog.d/x.added.md',
      'tickets/0001-a.md',
    ]);
  });

  it('returns empty when the directories are absent', async () => {
    const backend = new FilesystemBackend(new FakeDir('') as unknown as FileSystemDirectoryHandle);
    expect(await backend.scan()).toEqual([]);
  });
});

describe('FilesystemBackend.save', () => {
  it('writes upserts and removes deletes in place', async () => {
    const root = repoWith({ 'tickets/0001-a.md': 'old', 'tickets/0002-b.md': 'bye' });
    const backend = new FilesystemBackend(root as unknown as FileSystemDirectoryHandle);
    const changes: FileChange[] = [
      { path: 'tickets/0001-a.md', op: 'upsert', content: 'new' },
      { path: 'tickets/0002-b.md', op: 'delete' },
      { path: 'changelog.d/n.fixed.md', op: 'upsert', content: 'fresh' },
    ];
    const result = await backend.save(changes);

    expect(root.dirs.get('tickets')!.files.get('0001-a.md')!.content).toBe('new');
    expect(root.dirs.get('tickets')!.files.has('0002-b.md')).toBe(false);
    // changelog.d/ was created on demand.
    expect(root.dirs.get('changelog.d')!.files.get('n.fixed.md')!.content).toBe('fresh');
    expect(result.message).toContain('wrote 2');
    expect(result.message).toContain('deleted 1');
  });
});
