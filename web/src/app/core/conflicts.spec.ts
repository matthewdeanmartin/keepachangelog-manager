import { describe, it, expect } from 'vitest';
import {
  ConflictsScreen,
  FILE_CONFLICT_MESSAGE,
  FILE_FIELD,
  conflictFieldLabel,
  groupConflicts,
  isBodyConflict,
  isFileConflict,
} from './conflicts';
import { KatlConflict, KatlConflictsClient } from './backend/katl-conflicts-client';
import { FetchLike } from './backend/github-client';

function conflict(overrides: Partial<KatlConflict> = {}): KatlConflict {
  return {
    id: 1,
    task_id: '0001-a',
    field: 'status',
    base: 'todo',
    ours: 'doing',
    theirs: 'done',
    created_at: '2026-07-01T00:00:00Z',
    ...overrides,
  };
}

describe('conflictFieldLabel', () => {
  it('labels head fields, body, custom fields, and file deletions', () => {
    expect(conflictFieldLabel('status')).toBe('status');
    expect(conflictFieldLabel('body_md')).toBe('body');
    expect(conflictFieldLabel('custom.Sprint')).toBe('Sprint (custom field)');
    expect(conflictFieldLabel(FILE_FIELD)).toBe('file deleted');
  });
});

describe('conflict kind helpers', () => {
  it('detects __file__ and body_md conflicts', () => {
    expect(isFileConflict(conflict({ field: FILE_FIELD }))).toBe(true);
    expect(isFileConflict(conflict())).toBe(false);
    expect(isBodyConflict(conflict({ field: 'body_md' }))).toBe(true);
    expect(isBodyConflict(conflict())).toBe(false);
  });

  it('has a user-facing message for remote file deletions', () => {
    expect(FILE_CONFLICT_MESSAGE).toContain('deleting a file does not close a ticket');
  });
});

describe('groupConflicts', () => {
  it('groups by task id, sorted by task then field', () => {
    const groups = groupConflicts([
      conflict({ id: 3, task_id: '0002-b', field: 'title' }),
      conflict({ id: 1, task_id: '0001-a', field: 'status' }),
      conflict({ id: 2, task_id: '0002-b', field: 'body_md' }),
    ]);
    expect(groups.map((g) => g.taskId)).toEqual(['0001-a', '0002-b']);
    expect(groups[1].conflicts.map((c) => c.field)).toEqual(['body_md', 'title']);
  });

  it('returns no groups for an empty list', () => {
    expect(groupConflicts([])).toEqual([]);
  });
});

interface RecordedCall {
  method: string;
  url: string;
  body: Record<string, unknown> | undefined;
}

/** A conflicts client wired to a scripted fake server. */
function makeScreen(
  conflicts: KatlConflict[],
  resolveStatus = 200,
  resolveDetail = '',
): { screen: ConflictsScreen; calls: RecordedCall[] } {
  const calls: RecordedCall[] = [];
  const fetchImpl: FetchLike = async (url, init) => {
    calls.push({ method: init.method, url, body: init.body ? JSON.parse(init.body) : undefined });
    const isResolve = init.method === 'POST';
    const status = isResolve ? resolveStatus : 200;
    const payload = isResolve ? (resolveDetail ? { detail: resolveDetail } : {}) : conflicts;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    };
  };
  const client = new KatlConflictsClient({
    baseUrl: 'https://katl.example.com',
    token: 't',
    project: 'proj',
    fetchImpl,
  });
  return { screen: new ConflictsScreen(client), calls };
}

describe('ConflictsScreen', () => {
  it('load() populates and groups the conflict list', async () => {
    const { screen } = makeScreen([
      conflict({ id: 1, task_id: '0002-b' }),
      conflict({ id: 2, task_id: '0001-a' }),
    ]);
    expect(screen.loaded()).toBe(false);
    await screen.load();
    expect(screen.loaded()).toBe(true);
    expect(screen.conflicts()).toHaveLength(2);
    expect(screen.groups().map((g) => g.taskId)).toEqual(['0001-a', '0002-b']);
  });

  it('resolve() posts the choice and removes the row', async () => {
    const c = conflict({ id: 5 });
    const { screen, calls } = makeScreen([c, conflict({ id: 6, field: 'title' })]);
    await screen.load();
    await screen.resolve(c, 'theirs');

    const post = calls.find((call) => call.method === 'POST')!;
    expect(post.url).toBe('https://katl.example.com/projects/proj/conflicts/5/resolve');
    expect(post.body).toEqual({ choice: 'theirs' });
    expect(screen.conflicts().map((x) => x.id)).toEqual([6]);
    expect(screen.status()).toContain('0001-a');
    expect(screen.isError()).toBe(false);
  });

  it('resolve() with a custom value sends {choice, value}', async () => {
    const c = conflict({ id: 5, field: 'title' });
    const { screen, calls } = makeScreen([c]);
    await screen.load();
    await screen.resolve(c, 'custom', 'Better title');

    const post = calls.find((call) => call.method === 'POST')!;
    expect(post.body).toEqual({ choice: 'custom', value: 'Better title' });
    expect(screen.conflicts()).toEqual([]);
    expect(screen.status()).toContain('custom value');
  });

  it('describes __file__ resolutions as archive/restore', async () => {
    const c = conflict({ id: 5, field: FILE_FIELD, ours: 'file body', theirs: null });
    const { screen } = makeScreen([c]);
    await screen.load();
    await screen.resolve(c, 'theirs');
    expect(screen.status()).toContain('Archived ticket');

    const { screen: screen2 } = makeScreen([c]);
    await screen2.load();
    await screen2.resolve(c, 'ours');
    expect(screen2.status()).toContain('Restored file');
  });

  it('keeps the row and surfaces the server detail on a failed resolve', async () => {
    const c = conflict({ id: 5 });
    const { screen } = makeScreen([c], 409, 'already resolved');
    await screen.load();
    await screen.resolve(c, 'ours');
    expect(screen.conflicts()).toHaveLength(1);
    expect(screen.isError()).toBe(true);
    expect(screen.status()).toContain('already resolved');
    expect(screen.status()).toContain('409');
  });
});
