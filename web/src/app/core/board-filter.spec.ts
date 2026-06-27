import { describe, it, expect } from 'vitest';
import {
  filterTasks,
  distinctAssignees,
  distinctCategories,
  groupByMilestone,
  EMPTY_FILTER,
} from './board-filter';
import { TaskFragment } from './models';

function task(p: Partial<TaskFragment>): TaskFragment {
  return {
    taskId: 't',
    path: 'tickets/t.md',
    title: 'A task',
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

describe('filterTasks', () => {
  const tasks = [
    task({
      taskId: '1',
      title: 'Add OAuth',
      category: 'added',
      assignees: ['@a'],
      labels: ['auth'],
    }),
    task({ taskId: '2', title: 'Fix login', category: 'fixed', assignees: ['@b'] }),
  ];

  it('returns all with the empty filter', () => {
    expect(filterTasks(tasks, EMPTY_FILTER).length).toBe(2);
  });

  it('matches search against title, id, and labels', () => {
    expect(filterTasks(tasks, { ...EMPTY_FILTER, search: 'oauth' }).map((t) => t.taskId)).toEqual([
      '1',
    ]);
    expect(filterTasks(tasks, { ...EMPTY_FILTER, search: 'auth' }).map((t) => t.taskId)).toEqual([
      '1',
    ]);
    expect(filterTasks(tasks, { ...EMPTY_FILTER, search: '2' }).map((t) => t.taskId)).toEqual([
      '2',
    ]);
  });

  it('filters by assignee and category', () => {
    expect(filterTasks(tasks, { ...EMPTY_FILTER, assignee: '@b' }).map((t) => t.taskId)).toEqual([
      '2',
    ]);
    expect(filterTasks(tasks, { ...EMPTY_FILTER, category: 'added' }).map((t) => t.taskId)).toEqual(
      ['1'],
    );
  });
});

describe('distinct helpers', () => {
  const tasks = [
    task({ assignees: ['@a', '@b'], category: 'fixed' }),
    task({ assignees: ['@a'], category: 'added' }),
  ];
  it('lists distinct sorted assignees', () => {
    expect(distinctAssignees(tasks)).toEqual(['@a', '@b']);
  });
  it('lists distinct sorted categories', () => {
    expect(distinctCategories(tasks)).toEqual(['added', 'fixed']);
  });
});

describe('groupByMilestone', () => {
  it('groups by milestone with No milestone last', () => {
    const groups = groupByMilestone([
      task({ taskId: '1', milestone: '6.2.0' }),
      task({ taskId: '2' }),
      task({ taskId: '3', milestone: '6.1.0' }),
    ]);
    expect(groups.map((g) => g.milestone)).toEqual(['6.1.0', '6.2.0', 'No milestone']);
    expect(groups[2].tasks.map((t) => t.taskId)).toEqual(['2']);
  });
});
