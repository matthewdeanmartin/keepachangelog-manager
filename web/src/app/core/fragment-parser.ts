// Parser + writer for task fragments (tickets/*.md) and changelog fragments
// (changelog.d/<slug>.<type>.md). Faithful to the real keepachangelog-manager
// formats so files written here round-trip with the Python CLI.
//
// Invariants (from spec/TASK_FRAGMENTS_AND_UI.md):
//   * Total parsing — any markdown is a valid fragment; never throws.
//   * Lossless round-trip — render(parse(text)) preserves title, known fields,
//     custom fields (casing + order), and body (modulo trailing newline).

import {
  ChangelogFragment,
  TaskFragment,
  TaskStatus,
  canonicalCategory,
} from './models';

const KNOWN_HEAD_KEYS = new Set([
  'category',
  'status',
  'tracker',
  'labels',
  'assignees',
  'milestone',
]);

/** Split head/body on the first column-0 `---` that is NOT inside a fenced code block. */
export function splitHeadBody(text: string): { head: string; body: string; hadDivider: boolean } {
  const lines = text.split('\n');
  let inFence = false;
  let fenceMarker = '';
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fenceMatch = line.match(/^(```+|~~~+)/);
    if (fenceMatch) {
      if (!inFence) {
        inFence = true;
        fenceMarker = fenceMatch[1][0];
      } else if (line.startsWith(fenceMarker)) {
        inFence = false;
      }
      continue;
    }
    if (!inFence && /^---\s*$/.test(line)) {
      return {
        head: lines.slice(0, i).join('\n'),
        body: lines.slice(i + 1).join('\n'),
        hadDivider: true,
      };
    }
  }
  return { head: text, body: '', hadDivider: false };
}

function parseList(value: string): string[] {
  return value
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

/**
 * Parse a tickets/*.md file. `path` should be the repo-relative path; its stem
 * becomes the taskId and is cross-checked against the H1 id (lint, not error).
 */
export function parseTaskFragment(text: string, path: string): TaskFragment {
  const stem = fileStem(path);
  const lint: string[] = [];
  const { head, body, hadDivider } = splitHeadBody(text);
  if (!hadDivider) {
    lint.push('No `---` divider found; whole file treated as head, body is empty.');
  }

  const headLines = head.split('\n');

  // H1: "# <id> — <summary>" (em dash or hyphen). Fall back to first non-empty line.
  let title = '';
  let h1Id = '';
  for (const line of headLines) {
    const m = line.match(/^#\s+(.*)$/);
    if (m) {
      const h1 = m[1].trim();
      const dash = h1.match(/^(\S+)\s+[—–-]\s+(.*)$/);
      if (dash) {
        h1Id = dash[1];
        title = dash[2].trim();
      } else {
        title = h1;
      }
      break;
    }
  }
  if (!title) {
    title = stem;
    lint.push('No H1 title found; using filename stem.');
  }
  if (h1Id && h1Id !== stem) {
    lint.push(`H1 id "${h1Id}" does not match filename stem "${stem}".`);
  }

  // Metadata: a bullet list of `- **Key:** value` pairs, order-insensitive.
  const known: Record<string, string> = {};
  const custom: Record<string, string> = {};
  for (const line of headLines) {
    const m = line.match(/^\s*[-*]\s+\*\*(.+?):\*\*\s*(.*)$/);
    if (!m) continue;
    const rawKey = m[1].trim();
    const value = stripComment(m[2]).trim();
    const lowerKey = rawKey.toLowerCase();
    if (KNOWN_HEAD_KEYS.has(lowerKey)) {
      known[lowerKey] = value;
    } else {
      custom[rawKey] = value; // preserve casing + insertion order
    }
  }

  const rawCategory = known['category'] ?? '';
  const category = rawCategory ? canonicalCategory(rawCategory) : 'uncategorized';
  if (!rawCategory) {
    lint.push('Missing required field "Category"; landed in `uncategorized`.');
  }

  const status = (known['status'] || 'proposed') as TaskStatus;

  return {
    taskId: stem,
    path,
    title,
    category,
    status,
    tracker: known['tracker'] || undefined,
    labels: known['labels'] ? parseList(known['labels']) : [],
    assignees: known['assignees'] ? parseList(known['assignees']) : [],
    milestone: known['milestone'] || undefined,
    custom,
    body: body.replace(/\n+$/, ''),
    lint,
  };
}

/** Render a TaskFragment back to tickets/*.md text. */
export function renderTaskFragment(f: TaskFragment): string {
  const lines: string[] = [];
  lines.push(`# ${f.taskId} — ${f.title}`);
  lines.push('');
  lines.push(`- **Category:** ${f.category}`);
  lines.push(`- **Status:** ${f.status}`);
  if (f.tracker) lines.push(`- **Tracker:** ${f.tracker}`);
  if (f.labels.length) lines.push(`- **Labels:** ${f.labels.join(', ')}`);
  if (f.assignees.length) lines.push(`- **Assignees:** ${f.assignees.join(', ')}`);
  if (f.milestone) lines.push(`- **Milestone:** ${f.milestone}`);
  for (const [key, value] of Object.entries(f.custom)) {
    lines.push(`- **${key}:** ${value}`);
  }
  lines.push('');
  lines.push('---');
  lines.push('');
  lines.push(f.body.replace(/\n+$/, ''));
  return lines.join('\n').replace(/\n+$/, '') + '\n';
}

const CHANGELOG_FRAGMENT_RE = /^(.*)\.([a-z]+)\.md$/i;

/** Parse a changelog.d/<slug>.<type>.md fragment. The bullet text is the content. */
export function parseChangelogFragment(text: string, path: string): ChangelogFragment {
  const lint: string[] = [];
  const name = fileName(path);
  const m = name.match(CHANGELOG_FRAGMENT_RE);
  let slug = name.replace(/\.md$/i, '');
  let changeType = 'uncategorized';
  if (m) {
    slug = m[1];
    changeType = canonicalCategory(m[2]);
  } else {
    lint.push('Filename does not match `<slug>.<type>.md`.');
  }
  const body = text.trim();
  if (!body) {
    lint.push('Fragment content is empty.');
  }
  return { path, slug, changeType, text: body, lint };
}

export function renderChangelogFragment(f: ChangelogFragment): string {
  return f.text.replace(/\n+$/, '') + '\n';
}

export function changelogFragmentFileName(slug: string, changeType: string): string {
  return `${slugify(slug)}.${changeType}.md`;
}

// --- small path helpers (browser-safe, no node:path) ---

export function fileName(path: string): string {
  return path.split('/').pop() ?? path;
}

export function fileStem(path: string): string {
  return fileName(path).replace(/\.md$/i, '');
}

export function slugify(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function stripComment(value: string): string {
  // Drop a trailing `<!-- ... -->` HTML comment used for inline guidance.
  return value.replace(/<!--.*?-->\s*$/, '');
}
