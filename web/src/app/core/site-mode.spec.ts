import { describe, expect, it } from 'vitest';
import { resolveSiteMode } from './site-mode';
import { FetchLike } from './backend/github-client';

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

describe('resolveSiteMode', () => {
  it('defaults to lite: no site-mode.json, no dev config', async () => {
    const mode = await resolveSiteMode(fakeFetch({}), { devConfigPresent: false });
    expect(mode).toBe('lite');
  });

  it('honors /site-mode.json declaring server', async () => {
    const fetch = fakeFetch({ '/site-mode.json': { ok: true, body: { mode: 'server' } } });
    const mode = await resolveSiteMode(fetch, { devConfigPresent: false });
    expect(mode).toBe('server');
  });

  it('an explicit lite declaration beats a present dev config', async () => {
    const fetch = fakeFetch({ '/site-mode.json': { ok: true, body: { mode: 'lite' } } });
    const mode = await resolveSiteMode(fetch, { devConfigPresent: true });
    expect(mode).toBe('lite');
  });

  it('a present dev config implies server when no declaration exists', async () => {
    const mode = await resolveSiteMode(fakeFetch({}), { devConfigPresent: true });
    expect(mode).toBe('server');
  });

  it('ignores an unrecognized mode value', async () => {
    const fetch = fakeFetch({ '/site-mode.json': { ok: true, body: { mode: 'premium' } } });
    const mode = await resolveSiteMode(fetch, { devConfigPresent: false });
    expect(mode).toBe('lite');
  });

  it('survives index.html being served for unknown paths (json() throws)', async () => {
    const fetch = fakeFetch({ '/site-mode.json': { ok: true } }); // body undefined -> throws
    const mode = await resolveSiteMode(fetch, { devConfigPresent: false });
    expect(mode).toBe('lite');
  });
});
