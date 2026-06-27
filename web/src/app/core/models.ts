// Domain models for KATL — grounded in the real keepachangelog-manager formats.
//
// Two on-disk artifacts:
//   * tickets/*.md            — task fragments: rigid markdown head + free body
//   * changelog.d/<slug>.<type>.md — changelog fragments: bullet text, type in filename
//
// These mirror changelogmanager/change_types.py (categories) and
// spec/TASK_FRAGMENTS_AND_UI.md + spec/fragments.md (file shapes). They are NOT
// the YAML-front-matter ".katl/" format the original web_gui.md draft invented;
// see spec/web_gui.md (revised) for why.

/** Keep a Changelog statuses for a task fragment head. */
export type TaskStatus = 'proposed' | 'accepted' | 'in-progress' | 'blocked' | 'done' | 'wontfix';

export const TASK_STATUSES: TaskStatus[] = [
  'proposed',
  'accepted',
  'in-progress',
  'blocked',
  'done',
  'wontfix',
];

/** A category as defined by changelogmanager/change_types.py. */
export interface Category {
  key: string;
  /** Human title used in CHANGELOG / TASKS headings. */
  title: string;
  /** GitHub-style emoji short name (matches the Python `emoji` field). */
  emoji: string;
  /** SemVer bump this category implies. */
  bump: 'major' | 'minor' | 'patch';
  /** Whether entries of this category may reach a user-facing CHANGELOG.md. */
  shipsToChangelog: boolean;
}

/** The six shipping Keep a Changelog categories. */
export const SHIPPING_CATEGORIES: Category[] = [
  { key: 'added', title: 'New Features', emoji: 'rocket', bump: 'minor', shipsToChangelog: true },
  {
    key: 'changed',
    title: 'Updated Features',
    emoji: 'scissors',
    bump: 'patch',
    shipsToChangelog: true,
  },
  {
    key: 'deprecated',
    title: 'Deprecation',
    emoji: 'warning',
    bump: 'patch',
    shipsToChangelog: true,
  },
  {
    key: 'removed',
    title: 'Removed',
    emoji: 'no_entry_sign',
    bump: 'major',
    shipsToChangelog: true,
  },
  { key: 'fixed', title: 'Bug Fixes', emoji: 'bug', bump: 'patch', shipsToChangelog: true },
  {
    key: 'security',
    title: 'Security Changes',
    emoji: 'closed_lock_with_key',
    bump: 'minor',
    shipsToChangelog: true,
  },
];

/** Non-shipping categories: real tracked work that must never reach CHANGELOG.md. */
const NON_SHIPPING_CATEGORIES: Category[] = [
  {
    key: 'internal',
    title: 'Internal',
    emoji: 'hammer_and_wrench',
    bump: 'patch',
    shipsToChangelog: false,
  },
  { key: 'chore', title: 'Chores', emoji: 'broom', bump: 'patch', shipsToChangelog: false },
  { key: 'docs', title: 'Docs', emoji: 'book', bump: 'patch', shipsToChangelog: false },
  { key: 'test', title: 'Tests', emoji: 'test_tube', bump: 'patch', shipsToChangelog: false },
  { key: 'spike', title: 'Spikes', emoji: 'microscope', bump: 'patch', shipsToChangelog: false },
];

export const ALL_CATEGORIES: Category[] = [...SHIPPING_CATEGORIES, ...NON_SHIPPING_CATEGORIES];

const CATEGORY_BY_KEY = new Map(ALL_CATEGORIES.map((c) => [c.key, c]));

/**
 * Normalize a free-text category to a known key, tolerating plurals and case —
 * the spirit of the Python `canonical_change_type()`. Unknown values are
 * returned lowercased (kept, treated as non-shipping by default).
 */
export function canonicalCategory(raw: string | undefined | null): string {
  if (!raw) return 'uncategorized';
  let key = raw.trim().toLowerCase();
  if (key.endsWith('s') && !CATEGORY_BY_KEY.has(key) && CATEGORY_BY_KEY.has(key.slice(0, -1))) {
    key = key.slice(0, -1);
  }
  return key;
}

export function lookupCategory(key: string): Category | undefined {
  return CATEGORY_BY_KEY.get(key);
}

/** Unknown categories default to non-shipping so typos never leak to CHANGELOG. */
export function shipsToChangelog(key: string | undefined | null): boolean {
  if (!key) return false;
  return CATEGORY_BY_KEY.get(canonicalCategory(key))?.shipsToChangelog ?? false;
}

/**
 * A parsed task fragment (tickets/*.md). Superset of the Python TaskItem.
 * Mirrors the TaskFragment dataclass in spec/TASK_FRAGMENTS_AND_UI.md.
 */
export interface TaskFragment {
  /** Filename stem, e.g. "0042-network-config". Cross-checked vs H1 id. */
  taskId: string;
  /** Full path within the repo, e.g. "tickets/0042-network-config.md". */
  path: string;
  /** H1 text after the id. */
  title: string;
  /** Raw category key (may be unknown). */
  category: string;
  status: TaskStatus | string;
  tracker?: string;
  labels: string[];
  assignees: string[];
  milestone?: string;
  /** Unknown head keys, casing + insertion order preserved. */
  custom: Record<string, string>;
  /** Verbatim free body below the divider. */
  body: string;
  /** Non-fatal warnings produced during parse. */
  lint: string[];
}

/** A parsed changelog fragment (changelog.d/<slug>.<type>.md). */
export interface ChangelogFragment {
  path: string;
  slug: string;
  changeType: string;
  /** The bullet text, without the leading "- ". */
  text: string;
  lint: string[];
}
