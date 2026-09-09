import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  createDevBackend,
  fetchDevConfig,
  readProjectOverride,
  writeProjectOverride,
} from './dev-autoconnect';
import { FetchLike } from './github-client';

/** Minimal localStorage for the node test environment. */
function stubLocalStorage(): void {
  const store = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
  });
}

interface Route {
  ok: boolean;
  status?: number;
  body?: unknown;
}

function fakeFetch(routes: Record<string, Route>): FetchLike {
  return async (url) => {
    const route = routes[url] ?? { ok: false, status: 404 };
    return {
      ok: route.ok,
      status: route.status ?? (route.ok ? 200 : 404),
      json: async () => {
        if (route.body === undefined) throw new SyntaxError('not json');
        return route.body;
      },
      text: async () => JSON.stringify(route.body ?? ''),
    };
  };
}

const CONFIG = { baseUrl: 'http://localhost:8000', token: 'katl_secret' };

describe('fetchDevConfig', () => {
  it('returns the config when /dev-katl.json exists and is valid', async () => {
    const config = await fetchDevConfig(
      fakeFetch({ '/dev-katl.json': { ok: true, body: CONFIG } }),
    );
    expect(config).toEqual({ ...CONFIG, project: undefined });
  });

  it('returns null on 404 (production: no generated file)', async () => {
    expect(await fetchDevConfig(fakeFetch({}))).toBeNull();
  });

  it('returns null when the file is not valid config (e.g. index.html fallback)', async () => {
    expect(await fetchDevConfig(fakeFetch({ '/dev-katl.json': { ok: true } }))).toBeNull();
    expect(
      await fetchDevConfig(fakeFetch({ '/dev-katl.json': { ok: true, body: { nope: 1 } } })),
    ).toBeNull();
  });
});

describe('createDevBackend', () => {
  it('connects to the pinned project when the config names one', async () => {
    const backend = await createDevBackend(
      fakeFetch({ '/dev-katl.json': { ok: true, body: { ...CONFIG, project: 'pinned' } } }),
    );
    expect(backend?.serverConfig.project).toBe('pinned');
    expect(backend?.serverConfig.token).toBe('katl_secret');
  });

  it('falls back to the first project on the server', async () => {
    const backend = await createDevBackend(
      fakeFetch({
        '/dev-katl.json': { ok: true, body: CONFIG },
        'http://localhost:8000/projects': { ok: true, body: [{ key: 'alpha' }, { key: 'beta' }] },
      }),
    );
    expect(backend?.serverConfig.project).toBe('alpha');
  });

  it('returns null (never throws) when the server is down or empty', async () => {
    expect(
      await createDevBackend(fakeFetch({ '/dev-katl.json': { ok: true, body: CONFIG } })),
    ).toBeNull();
    expect(
      await createDevBackend(
        fakeFetch({
          '/dev-katl.json': { ok: true, body: CONFIG },
          'http://localhost:8000/projects': { ok: true, body: [] },
        }),
      ),
    ).toBeNull();
  });

  it('returns null without a dev config', async () => {
    expect(await createDevBackend(fakeFetch({}))).toBeNull();
  });
});

describe('project override (the UI project switcher survives refresh)', () => {
  afterEach(() => vi.unstubAllGlobals());

  const ROUTES = {
    '/dev-katl.json': { ok: true, body: CONFIG },
    'http://localhost:8000/projects': { ok: true, body: [{ key: 'alpha' }, { key: 'beta' }] },
  };

  it('is a no-op reader/writer without localStorage (node, SSR)', () => {
    expect(readProjectOverride()).toBeNull();
    expect(() => writeProjectOverride('beta')).not.toThrow();
  });

  it('beats the first-project default when it names a real project', async () => {
    stubLocalStorage();
    writeProjectOverride('beta');
    const backend = await createDevBackend(fakeFetch(ROUTES));
    expect(backend?.serverConfig.project).toBe('beta');
  });

  it('is ignored when the project no longer exists on the server', async () => {
    stubLocalStorage();
    writeProjectOverride('deleted-project');
    const backend = await createDevBackend(fakeFetch(ROUTES));
    expect(backend?.serverConfig.project).toBe('alpha');
  });

  it('never overrides a project pinned in the dev config', async () => {
    stubLocalStorage();
    writeProjectOverride('beta');
    const backend = await createDevBackend(
      fakeFetch({ '/dev-katl.json': { ok: true, body: { ...CONFIG, project: 'pinned' } } }),
    );
    expect(backend?.serverConfig.project).toBe('pinned');
  });
});
