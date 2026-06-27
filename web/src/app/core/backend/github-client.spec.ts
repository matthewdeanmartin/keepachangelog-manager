import { describe, it, expect } from 'vitest';
import { GitHubClient, GitHubError, FetchLike } from './github-client';

function jsonFetch(status: number, payload: unknown): FetchLike {
  return async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  });
}

describe('GitHubClient', () => {
  it('sends the bearer token and api-version headers', async () => {
    let seen: Record<string, string> = {};
    const fetchImpl: FetchLike = async (_url, init) => {
      seen = init.headers;
      return { ok: true, status: 200, json: async () => ({ login: 'me' }), text: async () => '' };
    };
    const client = new GitHubClient({ token: 'abc', fetchImpl });
    expect(await client.whoAmI()).toBe('me');
    expect(seen['Authorization']).toBe('Bearer abc');
    expect(seen['X-GitHub-Api-Version']).toBe('2022-11-28');
  });

  it('throws GitHubError with status and message on failure', async () => {
    const client = new GitHubClient({
      token: 't',
      fetchImpl: jsonFetch(401, { message: 'Bad credentials' }),
    });
    await expect(client.whoAmI()).rejects.toThrowError(GitHubError);
    await expect(client.whoAmI()).rejects.toMatchObject({
      status: 401,
      message: 'Bad credentials',
    });
  });

  it('parses the nested rate-limit shape', async () => {
    const client = new GitHubClient({
      token: 't',
      fetchImpl: jsonFetch(200, { resources: { core: { remaining: 4987, limit: 5000 } } }),
    });
    expect(await client.rateLimit()).toEqual({ remaining: 4987, limit: 5000 });
  });
});
