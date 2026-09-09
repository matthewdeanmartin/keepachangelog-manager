import { describe, it, expect } from 'vitest';
import { RepoService } from './repo.service';
import { FileChange, RepoBackend, SaveResult } from './backend/repo-backend';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function backend(directWrite = false) {
  const writes: { changes: FileChange[]; done: ReturnType<typeof deferred<SaveResult>> }[] = [];
  const repo: RepoBackend = {
    id: 'filesystem',
    capabilities: { directWrite, pullRequest: !directWrite },
    describe: () => ({ label: 'Test', detail: 'Test' }),
    scan: async () => [],
    save: (changes) => {
      if (!changes.length) return Promise.resolve({ kind: 'written', message: 'No changes' });
      const done = deferred<SaveResult>();
      writes.push({ changes, done });
      return done.promise;
    },
  };
  return { repo, writes };
}
const tick = async () => {
  for (let i = 0; i < 10; i++) await Promise.resolve();
};
const saved: SaveResult = { kind: 'written', message: 'Saved' };

describe('workspace persistence', () => {
  it('keeps newer edits to the same file pending during a commit', async () => {
    const service = new RepoService();
    const { repo, writes } = backend();
    await service.useBackend(repo);
    service.saveChangelogFragment('a', 'fixed', 'first');
    const pending = service.commit();
    await tick();
    service.saveChangelogFragment('a', 'fixed', 'second');
    writes[0].done.resolve(saved);
    await pending;
    expect(writes[0].changes[0].content).toBe('first\n');
    expect(service.dirtyPaths()).toEqual(['changelog.d/a.fixed.md']);
    const next = service.commit();
    await tick();
    expect(writes[1].changes[0].content).toBe('second\n');
    writes[1].done.resolve(saved);
    await next;
    expect(service.dirtyPaths()).toEqual([]);
  });

  it('serializes autosaves so older writes cannot finish last', async () => {
    const service = new RepoService();
    const { repo, writes } = backend(true);
    await service.useBackend(repo);
    service.saveChangelogFragment('a', 'fixed', 'first');
    await tick();
    service.saveChangelogFragment('a', 'fixed', 'second');
    await tick();
    expect(writes).toHaveLength(1);
    writes[0].done.resolve(saved);
    await tick();
    expect(writes).toHaveLength(2);
    expect(writes[1].changes[0].content).toBe('second\n');
    writes[1].done.resolve(saved);
    await tick();
    expect(service.dirtyPaths()).toEqual([]);
  });

  it('retains failed writes, reports errors, and permits retry', async () => {
    const service = new RepoService();
    const { repo, writes } = backend(true);
    await service.useBackend(repo);
    service.saveChangelogFragment('a', 'fixed', 'first');
    await tick();
    writes[0].done.reject(new Error('Permission denied'));
    await tick();
    expect(service.saveError()).toBe('Permission denied');
    expect(service.dirtyPaths()).toHaveLength(1);
    await expect(service.useBackend(backend().repo)).rejects.toThrow('Save pending');
    const retry = service.commit();
    await tick();
    writes[1].done.resolve(saved);
    await retry;
    expect(service.saveError()).toBeNull();
    expect(service.dirtyPaths()).toEqual([]);
  });

  it('does not replace a workspace when connecting fails', async () => {
    const service = new RepoService();
    const original = backend().repo;
    await service.useBackend(original);
    await expect(
      service.useBackend({
        ...backend().repo,
        scan: async () => {
          throw new Error('Offline');
        },
      }),
    ).rejects.toThrow('Offline');
    expect(service.activeBackend).toBe(original);
  });
});
