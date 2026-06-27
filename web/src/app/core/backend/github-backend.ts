// GitHub backend: scan a repo's tickets/ + changelog.d/ over the Git Trees API,
// and save a batch of changes as one multi-file commit on a fresh branch, then
// open a pull request (Git Data API: blobs -> tree -> commit -> ref -> PR).
//
// The app never writes the base branch directly. See spec/web_remaining_phases.md §4 (W1b).

import { RawFile } from '../fixtures';
import { BackendCapabilities, FileChange, RepoBackend, SaveResult } from './repo-backend';
import { GitHubClient } from './github-client';

export interface GitHubRepoConfig {
  owner: string;
  repo: string;
  baseBranch: string;
  /** Directories to scan; defaults match the CLI's discovery. */
  ticketsDir?: string;
  fragmentsDir?: string;
}

/** A new-branch name with a sortable timestamp, e.g. katl/update-fragments-20260626-171500. */
export function branchName(now: Date = new Date()): string {
  const p = (n: number, w = 2) => String(n).padStart(w, '0');
  const ts =
    `${now.getUTCFullYear()}${p(now.getUTCMonth() + 1)}${p(now.getUTCDate())}` +
    `-${p(now.getUTCHours())}${p(now.getUTCMinutes())}${p(now.getUTCSeconds())}`;
  return `katl/update-fragments-${ts}`;
}

/** A Git tree patch entry for one file change (blob sha for upsert, null to delete). */
export interface TreeEntry {
  path: string;
  mode: '100644';
  type: 'blob';
  sha: string | null;
}

export function buildCommitMessage(changes: FileChange[]): { title: string; body: string } {
  const upserts = changes.filter((c) => c.op === 'upsert').map((c) => c.path);
  const deletes = changes.filter((c) => c.op === 'delete').map((c) => c.path);
  const lines = ['Updated by KATL.', ''];
  if (upserts.length) {
    lines.push('Changed fragments:');
    upserts.forEach((p) => lines.push(`- ${p}`));
  }
  if (deletes.length) {
    if (upserts.length) lines.push('');
    lines.push('Removed fragments:');
    deletes.forEach((p) => lines.push(`- ${p}`));
  }
  return { title: 'Update KATL task fragments', body: lines.join('\n') };
}

export class GitHubBackend implements RepoBackend {
  readonly id = 'github' as const;
  readonly capabilities: BackendCapabilities = { pullRequest: true, directWrite: false };

  constructor(
    private readonly client: GitHubClient,
    private readonly config: GitHubRepoConfig,
  ) {}

  private get ticketsDir() {
    return (this.config.ticketsDir ?? 'tickets').replace(/\/$/, '');
  }
  private get fragmentsDir() {
    return (this.config.fragmentsDir ?? 'changelog.d').replace(/\/$/, '');
  }

  /** Read every tracked tickets/* and changelog.d/* file in the base branch. */
  async scan(): Promise<RawFile[]> {
    const { owner, repo, baseBranch } = this.config;
    const tree = await this.client.request<{ tree: { path: string; type: string }[] }>(
      'GET',
      `/repos/${owner}/${repo}/git/trees/${encodeURIComponent(baseBranch)}?recursive=1`,
    );
    const wanted = tree.tree.filter(
      (e) =>
        e.type === 'blob' &&
        e.path.endsWith('.md') &&
        (e.path.startsWith(`${this.ticketsDir}/`) || e.path.startsWith(`${this.fragmentsDir}/`)),
    );
    const files: RawFile[] = [];
    for (const entry of wanted) {
      const blob = await this.client.request<{ content: string; encoding: string }>(
        'GET',
        `/repos/${owner}/${repo}/contents/${entry.path.split('/').map(encodeURIComponent).join('/')}?ref=${encodeURIComponent(baseBranch)}`,
      );
      files.push({ path: entry.path, content: decodeContent(blob.content, blob.encoding) });
    }
    return files;
  }

  /** Commit all changes on a new branch and open a PR against the base. */
  async save(changes: FileChange[]): Promise<SaveResult> {
    if (!changes.length) {
      return { kind: 'pull-request', message: 'Nothing to commit.' };
    }
    const { owner, repo, baseBranch } = this.config;
    const repoPath = `/repos/${owner}/${repo}`;

    // 1. Resolve the base ref + its commit + tree.
    const baseRef = await this.client.request<{ object: { sha: string } }>(
      'GET',
      `${repoPath}/git/ref/heads/${encodeURIComponent(baseBranch)}`,
    );
    const baseSha = baseRef.object.sha;
    const baseCommit = await this.client.request<{ tree: { sha: string } }>(
      'GET',
      `${repoPath}/git/commits/${baseSha}`,
    );

    // 2. One blob per upsert; deletes become null-sha tree entries.
    const treeEntries: TreeEntry[] = [];
    for (const change of changes) {
      if (change.op === 'delete') {
        treeEntries.push({ path: change.path, mode: '100644', type: 'blob', sha: null });
        continue;
      }
      const blob = await this.client.request<{ sha: string }>('POST', `${repoPath}/git/blobs`, {
        content: change.content ?? '',
        encoding: 'utf-8',
      });
      treeEntries.push({ path: change.path, mode: '100644', type: 'blob', sha: blob.sha });
    }

    // 3. Tree -> commit -> new branch ref.
    const newTree = await this.client.request<{ sha: string }>('POST', `${repoPath}/git/trees`, {
      base_tree: baseCommit.tree.sha,
      tree: treeEntries,
    });
    const { title, body } = buildCommitMessage(changes);
    const commit = await this.client.request<{ sha: string }>('POST', `${repoPath}/git/commits`, {
      message: `${title}\n\n${body}`,
      tree: newTree.sha,
      parents: [baseSha],
    });
    const head = branchName();
    await this.client.request('POST', `${repoPath}/git/refs`, {
      ref: `refs/heads/${head}`,
      sha: commit.sha,
    });

    // 4. Open the PR.
    const pr = await this.client.request<{ html_url: string; number: number }>(
      'POST',
      `${repoPath}/pulls`,
      { title, body: prBody(changes), head, base: baseBranch },
    );
    return {
      kind: 'pull-request',
      url: pr.html_url,
      message: `Opened PR #${pr.number}`,
    };
  }
}

function prBody(changes: FileChange[]): string {
  const lines = [
    '## Summary',
    '',
    'This PR updates KATL task/changelog fragments.',
    '',
    '## Changed fragments',
    '',
  ];
  for (const c of changes) {
    lines.push(`- ${c.op === 'delete' ? '🗑 ' : ''}\`${c.path}\``);
  }
  lines.push('', '## Generated by', '', 'KATL static editor.');
  return lines.join('\n');
}

function decodeContent(content: string, encoding: string): string {
  if (encoding === 'base64') {
    const binary = atob(content.replace(/\n/g, ''));
    // Decode UTF-8 from the binary string.
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    return new TextDecoder('utf-8').decode(bytes);
  }
  return content;
}
