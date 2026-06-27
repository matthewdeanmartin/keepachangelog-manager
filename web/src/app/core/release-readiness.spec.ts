import { describe, it, expect } from 'vitest';
import { buildReadinessReport } from './release-readiness';
import { ChangelogFragment, TaskFragment } from './models';

function task(p: Partial<TaskFragment>): TaskFragment {
  return {
    taskId: 't',
    path: 'tickets/t.md',
    title: 'T',
    category: 'added',
    status: 'proposed',
    labels: [],
    assignees: [],
    custom: {},
    body: '',
    lint: [],
    ...p,
  };
}

function frag(p: Partial<ChangelogFragment>): ChangelogFragment {
  return {
    path: 'changelog.d/x.added.md',
    slug: 'x',
    changeType: 'added',
    text: 't',
    lint: [],
    ...p,
  };
}

describe('buildReadinessReport', () => {
  it('flags done shipping tickets with no matching fragment', () => {
    const r = buildReadinessReport([task({ taskId: 'a', status: 'done', category: 'added' })], []);
    expect(r.doneMissingFragment.map((t) => t.taskId)).toEqual(['a']);
    expect(r.ready).toBe(false);
  });

  it('does not flag a done ticket that has a matching fragment', () => {
    const r = buildReadinessReport(
      [task({ taskId: 'a', status: 'done', category: 'added' })],
      [frag({ slug: 'a' })],
    );
    expect(r.doneMissingFragment).toEqual([]);
    expect(r.ready).toBe(true);
  });

  it('ignores non-shipping done tickets', () => {
    const r = buildReadinessReport(
      [task({ taskId: 'a', status: 'done', category: 'internal' })],
      [],
    );
    expect(r.doneMissingFragment).toEqual([]);
  });

  it('flags orphan fragments with no matching ticket', () => {
    const r = buildReadinessReport([task({ taskId: 'a' })], [frag({ slug: 'ghost' })]);
    expect(r.orphanFragments.map((f) => f.slug)).toEqual(['ghost']);
    expect(r.ready).toBe(false);
  });

  it('lists stuck (in-progress/blocked) tickets but they do not block readiness', () => {
    const r = buildReadinessReport(
      [task({ taskId: 'a', status: 'in-progress' }), task({ taskId: 'b', status: 'blocked' })],
      [],
    );
    expect(r.stuckTickets.map((t) => t.taskId)).toEqual(['a', 'b']);
    expect(r.ready).toBe(true);
  });
});
