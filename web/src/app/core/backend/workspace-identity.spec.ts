import { describe, expect, it } from 'vitest';
import { LocalStorageBackend } from './local-storage-backend';
import { FilesystemBackend } from './filesystem-backend';
import { GitHubBackend } from './github-backend';
import { GitHubClient } from './github-client';
import { KatlServerBackend } from './katl-server-backend';

// Every backend must answer "what am I looking at?" — the topbar chip and
// the Workspace screen render these verbatim.
describe('RepoBackend.describe()', () => {
  it('local-storage names the sample workspace, not a config gap', () => {
    expect(new LocalStorageBackend().describe()).toEqual({
      label: 'Sample workspace',
      detail: 'demo tickets in browser storage',
    });
  });

  it('filesystem uses the picked folder name', () => {
    const root = { name: 'my-repo' } as FileSystemDirectoryHandle;
    expect(new FilesystemBackend(root).describe()).toEqual({
      label: 'my-repo',
      detail: 'local folder on disk',
    });
  });

  it('filesystem falls back when the handle has no name (drive roots)', () => {
    const root = { name: '' } as FileSystemDirectoryHandle;
    expect(new FilesystemBackend(root).describe().label).toBe('Local folder');
  });

  it('github shows owner/repo and the base branch', () => {
    const backend = new GitHubBackend(new GitHubClient({ token: 't' }), {
      owner: 'octocat',
      repo: 'hello',
      baseBranch: 'main',
    });
    expect(backend.describe()).toEqual({
      label: 'octocat/hello',
      detail: 'branch main, via GitHub API',
    });
  });

  it('katl-server shows the project and the server host', () => {
    const backend = new KatlServerBackend({
      baseUrl: 'https://katl.example.com:8443/',
      token: 'sekret',
      project: 'mastodon-is-my-blog',
    });
    expect(backend.describe()).toEqual({
      label: 'mastodon-is-my-blog',
      detail: 'KATL server at katl.example.com:8443',
    });
  });

  it('katl-server tolerates an unparseable base URL', () => {
    const backend = new KatlServerBackend({ baseUrl: '/api', token: 't', project: 'p' });
    expect(backend.describe().detail).toBe('KATL server at /api');
  });
});

describe('KatlServerBackend.withProject', () => {
  it('keeps the connection and swaps only the project', () => {
    const backend = new KatlServerBackend({
      baseUrl: 'https://katl.example.com',
      token: 'sekret',
      project: 'alpha',
    });
    const swapped = backend.withProject('beta');
    expect(swapped).not.toBe(backend);
    expect(swapped.serverConfig).toEqual({ ...backend.serverConfig, project: 'beta' });
    expect(backend.serverConfig.project).toBe('alpha');
  });
});
