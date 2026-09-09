import { describe, it, expect } from 'vitest';
import {
  GitHubBackend,
  GitHubRepoConfig,
  TreeEntry,
  branchName,
  buildCommitMessage,
} from './github-backend';
import { GitHubClient, FetchLike } from './github-client';
import { FileChange } from './repo-backend';

type Json = Record<string, unknown>;

/** A scripted fake fetch that records requests and replies by route. */
function fakeFetch(routes: Record<string, (body: Json | undefined) => Json>): {
  fetchImpl: FetchLike;
  calls: { method: string; url: string; body: Json | undefined }[];
} {
  const calls: { method: string; url: string; body: Json | undefined }[] = [];
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
      'GET /git/ref/heads/main': () => ({ object: { sha: 'basesha' } }),
      'GET /git/trees/basesha': () => ({
        tree: [
          { path: 'tickets/0001-a.md', type: 'blob', sha: 'original' },
          { path: 'changelog.d/x.added.md', type: 'blob', sha: 'original' },
          { path: 'README.md', type: 'blob', sha: 'original' },
          { path: 'src/main.ts', type: 'blob', sha: 'original' },
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
      'GET /git/trees/basesha': () => ({
        tree: [{ path: 'changelog.d/old.fixed.md', type: 'blob', sha: 'old' }],
      }),
      'GET /contents/': () => ({ content: 'old', encoding: 'utf-8' }),
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
    await backend.scan();
    const result = await backend.save(changes);

    expect(result.kind).toBe('pull-request');
    expect(result.url).toBe('https://github.com/me/proj/pull/7');
    expect(result.message).toContain('#7');

    // The new tree references base_tree and includes a null-sha delete entry.
    const treeBody = calls.find((c) => c.url.includes('/git/trees') && c.method === 'POST')!
      .body as { base_tree: string; tree: TreeEntry[] };
    expect(treeBody.base_tree).toBe('basetree');
    const del = treeBody.tree.find((e) => e.path === 'changelog.d/old.fixed.md');
    expect(del?.sha).toBeNull();

    // The commit parents the base sha; the PR targets main from a katl/ branch.
    const commitBody = calls.find((c) => c.url.includes('/git/commits') && c.method === 'POST')!
      .body as { parents: string[] };
    expect(commitBody.parents).toEqual(['basesha']);
    const prBody = calls.find((c) => c.url.includes('/pulls'))!.body as {
      base: string;
      head: string;
    };
    expect(prBody.base).toBe('main');
    expect(prBody.head).toMatch(/^katl\/update-fragments-/);
  });

  it('no-ops on an empty change set', async () => {
    const { fetchImpl, calls } = fakeFetch({});
    const backend = new GitHubBackend(new GitHubClient({ token: 't', fetchImpl }), config);
    const result = await backend.save([]);
    expect(result.message).toContain('Nothing');
    expect(calls.length).toBe(0);
  });
});

describe('GitHub conflict checks', () => {
  it.each(['modified', 'deleted', 'created'])(
    'rejects a remotely %s file before any writes',
    async (kind) => {
      let saving = false;
      const path = 'tickets/a.md';
      const initial = kind === 'created' ? [] : [{ path, type: 'blob', sha: 'old' }];
      const current = kind === 'deleted' ? [] : [{ path, type: 'blob', sha: 'new' }];
      const { fetchImpl, calls } = fakeFetch({
        'GET /git/ref/heads/main': () => ({ object: { sha: saving ? 'newbase' : 'oldbase' } }),
        'GET /git/trees/oldbase': () => ({ tree: initial }),
        'GET /git/trees/newbase': () => ({ tree: current }),
        'GET /contents/': () => ({ content: 'original', encoding: 'utf-8' }),
      });
      const backend = new GitHubBackend(new GitHubClient({ token: 't', fetchImpl }), config);
      await backend.scan();
      saving = true;
      await expect(backend.save([{ path, op: 'upsert', content: 'my edit' }])).rejects.toThrow(
        path,
      );
      expect(calls.every((c) => c.method === 'GET')).toBe(true);
      expect(
        calls
          .filter((c) => c.url.includes('/contents/'))
          .every((c) => c.url.endsWith('ref=oldbase')),
      ).toBe(true);
    },
  );
  it('refuses incomplete trees rather than treating omitted paths as absent', async () => {
    const { fetchImpl } = fakeFetch({
      'GET /git/ref/heads/main': () => ({ object: { sha: 'base' } }),
      'GET /git/trees/base': () => ({ tree: [], truncated: true }),
    });
    const backend = new GitHubBackend(new GitHubClient({ token: 't', fetchImpl }), config);
    await expect(backend.scan()).rejects.toThrow('incomplete');
    await expect(backend.save([{ path: 'tickets/a.md', op: 'delete' }])).rejects.toThrow('Load');
  });
});
