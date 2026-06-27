// Generate a Keep a Changelog "[Unreleased]" preview from changelog fragments
// and/or done shipping task fragments — mirrors `fragments collect` /
// `tasks assemble --changelog` grouping.

import { ChangelogFragment, SHIPPING_CATEGORIES, TaskFragment, shipsToChangelog } from './models';

interface PreviewEntry {
  text: string;
  /** Where this bullet came from, for the "tasks without changelog text" report. */
  source: 'changelog-fragment' | 'task';
}

export interface PreviewGroup {
  changeType: string;
  title: string;
  entries: PreviewEntry[];
}

/** Group shipping entries by Keep a Changelog category, in canonical KAC order. */
export function buildUnreleasedGroups(
  changelogFragments: ChangelogFragment[],
  doneTasks: TaskFragment[],
): PreviewGroup[] {
  const byType = new Map<string, PreviewEntry[]>();

  const push = (type: string, entry: PreviewEntry) => {
    if (!shipsToChangelog(type)) return;
    const list = byType.get(type) ?? [];
    list.push(entry);
    byType.set(type, list);
  };

  for (const f of [...changelogFragments].sort((a, b) => a.slug.localeCompare(b.slug))) {
    push(f.changeType, { text: f.text, source: 'changelog-fragment' });
  }
  for (const t of doneTasks) {
    if (t.status !== 'done') continue;
    push(t.category, { text: t.title, source: 'task' });
  }

  const groups: PreviewGroup[] = [];
  for (const cat of SHIPPING_CATEGORIES) {
    const entries = byType.get(cat.key);
    if (entries && entries.length) {
      groups.push({ changeType: cat.key, title: cat.title, entries });
    }
  }
  return groups;
}

/** Render groups to a Markdown [Unreleased] section. */
export function renderUnreleasedMarkdown(groups: PreviewGroup[]): string {
  const out: string[] = ['## [Unreleased]', ''];
  if (!groups.length) {
    out.push('_No shipping changes yet._', '');
    return out.join('\n');
  }
  for (const g of groups) {
    out.push(`### ${kacHeading(g.changeType)}`, '');
    for (const e of g.entries) {
      out.push(`- ${indentContinuation(e.text)}`);
    }
    out.push('');
  }
  return out.join('\n');
}

/** Keep a Changelog headings use the section name, not the project title. */
function kacHeading(changeType: string): string {
  // The KAC section headings are the capitalized category keys.
  return changeType.charAt(0).toUpperCase() + changeType.slice(1);
}

function indentContinuation(text: string): string {
  return text.split('\n').join('\n  ');
}

/** Done shipping tasks that have no matching changelog fragment slug. */
export function tasksMissingChangelog(
  tasks: TaskFragment[],
  fragments: ChangelogFragment[],
): TaskFragment[] {
  const fragSlugs = new Set(fragments.map((f) => f.slug));
  return tasks.filter(
    (t) => t.status === 'done' && shipsToChangelog(t.category) && !fragSlugs.has(t.taskId),
  );
}
