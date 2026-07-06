import { describe, it, expect } from 'vitest';
import { KatlConflict, KatlConflictsClient } from './katl-conflicts-client';
import { KatlServerError } from './katl-http';
import { FetchLike } from './github-client';

type Json = unknown;

interface RecordedCall {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: Record<string, unknown> | undefined;
}

/** A scripted fake fetch that records requests and replies by route. */
function fakeFetch(routes: Record<string, () => { status?: number; payload?: Json }>): {
  fetchImpl: FetchLike;
  calls: RecordedCall[];
} {
  const calls: RecordedCall[] = [];
  const fetchImpl: FetchLike = async (url, init) => {
    calls.push({
      method: init.method,
      url,
      headers: init.headers,
      body: init.body ? JSON.parse(init.body) : undefined,
    });
    const key = Object.keys(routes).find((k) => {
      const [m, ...rest] = k.split(' ');
      return m === init.method && url.includes(rest.join(' '));
    });
    const { status = 200, payload = {} } = key ? routes[key]() : {};
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    };
  };
  return { fetchImpl, calls };
}

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

function makeClient(fetchImpl: FetchLike): KatlConflictsClient {
  return new KatlConflictsClient({
    baseUrl: 'https://katl.example.com/',
    token: 'sekret',
    project: 'proj',
    fetchImpl,
  });
}

describe('KatlConflictsClient.listConflicts', () => {
  it('GETs the conflicts endpoint with the auth header', async () => {
    const payload = [conflict(), conflict({ id: 2, field: 'title' })];
    const { fetchImpl, calls } = fakeFetch({
      'GET /projects/proj/conflicts': () => ({ payload }),
    });
    const conflicts = await makeClient(fetchImpl).listConflicts();
    expect(conflicts).toEqual(payload);
    expect(calls[0].url).toBe('https://katl.example.com/projects/proj/conflicts');
    expect(calls[0].headers['X-Katl-Token']).toBe('sekret');
  });
});

describe('KatlConflictsClient.resolveConflict', () => {
  it.each(['ours', 'theirs'] as const)('POSTs {choice: %s} without a value', async (choice) => {
    const { fetchImpl, calls } = fakeFetch({
      'POST /conflicts/7/resolve': () => ({
        payload: { id: 7, task_id: '0001-a', field: 'status', choice },
      }),
    });
    const result = await makeClient(fetchImpl).resolveConflict(7, choice);
    expect(result.choice).toBe(choice);
    expect(calls[0].url).toBe('https://katl.example.com/projects/proj/conflicts/7/resolve');
    expect(calls[0].body).toEqual({ choice });
    expect(calls[0].headers['Content-Type']).toBe('application/json');
  });

  it('POSTs {choice: custom, value} for a custom resolution', async () => {
    const { fetchImpl, calls } = fakeFetch({
      'POST /conflicts/9/resolve': () => ({
        payload: { id: 9, task_id: '0001-a', field: 'title', choice: 'custom' },
      }),
    });
    await makeClient(fetchImpl).resolveConflict(9, 'custom', 'Merged title');
    expect(calls[0].body).toEqual({ choice: 'custom', value: 'Merged title' });
  });

  it('surfaces the server error detail on non-2xx', async () => {
    const { fetchImpl } = fakeFetch({
      'POST /conflicts/7/resolve': () => ({ status: 409, payload: { detail: 'already resolved' } }),
    });
    const client = makeClient(fetchImpl);
    await expect(client.resolveConflict(7, 'ours')).rejects.toThrowError('already resolved');
    await expect(client.resolveConflict(7, 'ours')).rejects.toBeInstanceOf(KatlServerError);
  });
});
