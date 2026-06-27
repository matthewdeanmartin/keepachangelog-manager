import { describe, it, expect } from 'vitest';
import {
  buildUnreleasedGroups,
  renderUnreleasedMarkdown,
  tasksMissingChangelog,
} from './changelog-preview';
import { ChangelogFragment, TaskFragment } from './models';

function task(partial: Partial<TaskFragment>): TaskFragment {
  return {
    taskId: 't',
    path: 'tickets/t.md',
    title: 'A task',
    category: 'added',
    status: 'done',
    labels: [],
    assignees: [],
    custom: {},
    body: '',
    lint: [],
    ...partial,
  };
}

function frag(partial: Partial<ChangelogFragment>): ChangelogFragment {
  return { path: 'changelog.d/x.added.md', slug: 'x', changeType: 'added', text: 't', lint: [], ...partial };
}

describe('buildUnreleasedGroups', () => {
  it('groups shipping fragments and done shipping tasks by KAC category', () => {
    const groups = buildUnreleasedGroups(
      [frag({ slug: 'a', changeType: 'added', text: 'Added thing' })],
      [task({ taskId: 'b', category: 'fixed', title: 'Fixed thing', status: 'done' })],
    );
    expect(groups.map((g) => g.changeType)).toEqual(['added', 'fixed']);
  });

  it('excludes non-shipping categories', () => {
    const groups = buildUnreleasedGroups(
      [],
      [task({ category: 'internal', status: 'done' })],
    );
    expect(groups).toEqual([]);
  });

  it('excludes non-done tasks', () => {
    const groups = buildUnreleasedGroups(
      [],
      [task({ category: 'added', status: 'in-progress' })],
    );
    expect(groups).toEqual([]);
  });

  it('treats unknown categories as non-shipping', () => {
    const groups = buildUnreleasedGroups([frag({ changeType: 'wibble' })], []);
    expect(groups).toEqual([]);
  });
});

describe('renderUnreleasedMarkdown', () => {
  it('renders KAC headings', () => {
    const md = renderUnreleasedMarkdown(
      buildUnreleasedGroups([frag({ text: 'Added thing' })], []),
    );
    expect(md).toContain('## [Unreleased]');
    expect(md).toContain('### Added');
    expect(md).toContain('- Added thing');
  });

  it('shows a placeholder when empty', () => {
    expect(renderUnreleasedMarkdown([])).toContain('No shipping changes');
  });
});

describe('tasksMissingChangelog', () => {
  it('flags done shipping tasks with no matching fragment slug', () => {
    const missing = tasksMissingChangelog(
      [task({ taskId: 'orphan', category: 'added', status: 'done' })],
      [frag({ slug: 'something-else' })],
    );
    expect(missing.map((t) => t.taskId)).toEqual(['orphan']);
  });

  it('does not flag tasks that have a matching fragment', () => {
    const missing = tasksMissingChangelog(
      [task({ taskId: 'matched', category: 'added', status: 'done' })],
      [frag({ slug: 'matched' })],
    );
    expect(missing).toEqual([]);
  });
});
