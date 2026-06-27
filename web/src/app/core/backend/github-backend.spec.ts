import { describe, it, expect } from 'vitest';
import {
  GitHubBackend,
  GitHubRepoConfig,
  branchName,
  buildCommitMessage,
} from './github-backend';
import { GitHubClient, FetchLike } from './github-client';
import { FileChange } from './repo-backend';

/** A scripted fake fetch that records requests and replies by route. */
function fakeFetch(routes: Record<string, (body: any) => any>): {
  fetchImpl: FetchLike;
  calls: { method: string; url: string; body: any }[];
} {
  const calls: { method: string; url: string; body: any }[] = [];
  const fetchImpl: FetchLike = async (url, init) => {
    const body = init.body ? JSON.parse(init.body) : undefined;
    calls.push({ method: init.method, url, body });
    const key = Object.keys(routes).find((k) => {
      const [m, ...rest] = k.split(' ');
      return m === init.method && url.includes(rest.join(' '));
    });
    const payload = key ? routes[key](body) : {};
    return {
      ok: true,
      status: 200,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    };
  };
  return { fetchImpl, calls };
}

const config: GitHubRepoConfig = { owner: 'me', repo: 'proj', baseBranch: 'main' };

describe('branchName', () => {
  it('builds a sortable katl/ branch from a fixed date', () => {
    const name = branchName(new Date(Date.UTC(2026, 5, 26, 17, 15, 0)));
    expect(name).toBe('katl/update-fragments-20260626-171500');
  });
});

describe('buildCommitMessage', () => {
  it('lists upserts and deletes', () => {
    const { title, body } = buildCommitMessage([
      { path: 'tickets/a.md', op: 'upsert', content: 'x' },
      { path: 'changelog.d/b.added.md', op: 'delete' },
    ]);
    expect(title).toBe('Update KATL task fragments');
    expect(body).toContain('Changed fragments:');
    expect(body).toContain('- tickets/a.md');
    expect(body).toContain('Removed fragments:');
    expect(body).toContain('- changelog.d/b.added.md');
  });
});

describe('GitHubBackend.scan', () => {
  it('reads only tickets/* and changelog.d/* markdown blobs', async () => {
    const { fetchImpl } = fakeFetch({
      'GET /git/trees/main': () => ({
        tree: [
          { path: 'tickets/0001-a.md', type: 'blob' },
          { path: 'changelog.d/x.added.md', type: 'blob' },
          { path: 'README.md', type: 'blob' },
          { path: 'src/main.ts', type: 'blob' },
        ],
      }),
      'GET /contents/': () => ({ content: btoa('hello'), encoding: 'base64' }),
    });
    const backend = new GitHubBackend(new GitHubClient({ token: 't', fetchImpl }), config);
    const files = await backend.scan();
    expect(files.map((f) => f.path).sort()).toEqual([
      'changelog.d/x.added.md',
      'tickets/0001-a.md',
    ]);
    expect(files[0].content).toBe('hello');
  });
});

describe('GitHubBackend.save', () => {
  it('runs blobs -> tree -> commit -> ref -> PR and returns the PR url', async () => {
    const { fetchImpl, calls } = fakeFetch({
      'GET /git/ref/heads/main': () => ({ object: { sha: 'basesha' } }),
      'GET /git/commits/basesha': () => ({ tree: { sha: 'basetree' } }),
      'POST /git/blobs': () => ({ sha: 'blobsha' }),
      'POST /git/trees': () => ({ sha: 'newtree' }),
      'POST /git/commits': () => ({ sha: 'commitsha' }),
      'POST /git/refs': () => ({}),
      'POST /pulls': () => ({ html_url: 'https://github.com/me/proj/pull/7', number: 7 }),
    });
    const backend = new GitHubBackend(new GitHubClient({ token: 't', fetchImpl }), config);
    const changes: FileChange[] = [
      { path: 'tickets/0001-a.md', op: 'upsert', content: 'body' },
      { path: 'changelog.d/old.fixed.md', op: 'delete' },
    ];
    const result = await backend.save(changes);

    expect(result.kind).toBe('pull-request');
    expect(result.url).toBe('https://github.com/me/proj/pull/7');
    expect(result.message).toContain('#7');

    // The new tree references base_tree and includes a null-sha delete entry.
    const treeCall = calls.find((c) => c.url.includes('/git/trees') && c.method === 'POST')!;
    expect(treeCall.body.base_tree).toBe('basetree');
    const del = treeCall.body.tree.find((e: any) => e.path === 'changelog.d/old.fixed.md');
    expect(del.sha).toBeNull();

    // The commit parents the base sha; the PR targets main from a katl/ branch.
    const commitCall = calls.find((c) => c.url.includes('/git/commits') && c.method === 'POST')!;
    expect(commitCall.body.parents).toEqual(['basesha']);
    const prCall = calls.find((c) => c.url.includes('/pulls'))!;
    expect(prCall.body.base).toBe('main');
    expect(prCall.body.head).toMatch(/^katl\/update-fragments-/);
  });

  it('no-ops on an empty change set', async () => {
    const { fetchImpl, calls } = fakeFetch({});
    const backend = new GitHubBackend(new GitHubClient({ token: 't', fetchImpl }), config);
    const result = await backend.save([]);
    expect(result.message).toContain('Nothing');
    expect(calls.length).toBe(0);
  });
});
