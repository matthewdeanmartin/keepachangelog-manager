import { describe, it, expect } from 'vitest';
import {
  KatlServerBackend,
  KatlServerConfig,
  KatlServerError,
  ticketIdFromPath,
} from './katl-server-backend';
import { FetchLike } from './github-client';
import { FileChange } from './repo-backend';

type Json = Record<string, unknown>;

interface RecordedCall {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: Json | undefined;
}

/** A scripted fake fetch that records requests and replies by route. */
function fakeFetch(
  routes: Record<string, (body: Json | undefined) => { status?: number; payload?: Json }>,
): { fetchImpl: FetchLike; calls: RecordedCall[] } {
  const calls: RecordedCall[] = [];
  const fetchImpl: FetchLike = async (url, init) => {
    const body = init.body ? JSON.parse(init.body) : undefined;
    calls.push({ method: init.method, url, headers: init.headers, body });
    const key = Object.keys(routes).find((k) => {
      const [m, ...rest] = k.split(' ');
      return m === init.method && url.includes(rest.join(' '));
    });
    const { status = 200, payload = {} } = key ? routes[key](body) : {};
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    };
  };
  return { fetchImpl, calls };
}

function makeBackend(fetchImpl: FetchLike, overrides: Partial<KatlServerConfig> = {}) {
  return new KatlServerBackend({
    baseUrl: 'https://katl.example.com/',
    token: 'sekret',
    project: 'proj',
    fetchImpl,
    ...overrides,
  });
}

describe('ticketIdFromPath', () => {
  it('extracts the task id from tickets/*.md', () => {
    expect(ticketIdFromPath('tickets/0001-a.md')).toBe('0001-a');
  });
  it('returns null for non-ticket paths', () => {
    expect(ticketIdFromPath('changelog.d/x.added.md')).toBeNull();
    expect(ticketIdFromPath('tickets/0001-a.txt')).toBeNull();
  });
});

describe('KatlServerBackend.scan', () => {
  it('maps the export payload to RawFile[] and sends the auth header', async () => {
    const { fetchImpl, calls } = fakeFetch({
      'GET /projects/proj/export': () => ({
        payload: {
          files: [
            { path: 'tickets/0001-a.md', content: 'hello' },
            { path: 'tickets/0002-b.md', content: 'world' },
          ],
        },
      }),
    });
    const files = await makeBackend(fetchImpl).scan();
    expect(files).toEqual([
      { path: 'tickets/0001-a.md', content: 'hello' },
      { path: 'tickets/0002-b.md', content: 'world' },
    ]);
    expect(calls[0].url).toBe('https://katl.example.com/projects/proj/export');
    expect(calls[0].headers['X-Katl-Token']).toBe('sekret');
  });
});

describe('KatlServerBackend.save', () => {
  it('imports upserts in one batch and deletes tickets individually', async () => {
    const { fetchImpl, calls } = fakeFetch({
      'POST /projects/proj/import': () => ({ payload: { created: 1, updated: 2, lint: [] } }),
      'DELETE /projects/proj/tickets/': () => ({ status: 204 }),
    });
    const changes: FileChange[] = [
      { path: 'tickets/0001-a.md', op: 'upsert', content: 'a' },
      { path: 'tickets/0002-b.md', op: 'upsert', content: 'b' },
      { path: 'tickets/0003-c.md', op: 'delete' },
    ];
    const result = await makeBackend(fetchImpl).save(changes);

    expect(result.kind).toBe('written');
    expect(result.message).toBe('Imported 3, deleted 1');

    const importCall = calls.find((c) => c.method === 'POST')!;
    expect(importCall.body).toEqual({
      files: [
        { path: 'tickets/0001-a.md', content: 'a' },
        { path: 'tickets/0002-b.md', content: 'b' },
      ],
    });
    const deleteCall = calls.find((c) => c.method === 'DELETE')!;
    expect(deleteCall.url).toBe('https://katl.example.com/projects/proj/tickets/0003-c');
    expect(deleteCall.headers['X-Katl-Token']).toBe('sekret');
  });

  it('skips non-ticket deletes with a note and no DELETE request', async () => {
    const { fetchImpl, calls } = fakeFetch({});
    const result = await makeBackend(fetchImpl).save([
      { path: 'changelog.d/x.added.md', op: 'delete' },
    ]);
    expect(result.message).toContain('deleted 0');
    expect(result.message).toContain('changelog.d/x.added.md');
    expect(calls.length).toBe(0);
  });

  it('no-ops on an empty change set', async () => {
    const { fetchImpl, calls } = fakeFetch({});
    const result = await makeBackend(fetchImpl).save([]);
    expect(result.message).toContain('Nothing');
    expect(calls.length).toBe(0);
  });

  it('surfaces the server error detail on non-2xx', async () => {
    const { fetchImpl } = fakeFetch({
      'GET /projects/proj/export': () => ({
        status: 403,
        payload: { detail: 'bad token' },
      }),
    });
    const backend = makeBackend(fetchImpl);
    await expect(backend.scan()).rejects.toThrowError('bad token');
    await expect(backend.scan()).rejects.toBeInstanceOf(KatlServerError);
  });
});
