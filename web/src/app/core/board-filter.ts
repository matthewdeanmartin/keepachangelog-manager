// Pure filter/grouping helpers for the board. Kept out of the component so the
// logic is unit-testable. See spec/web_remaining_phases.md §6 (W3).

import { TaskFragment } from './models';

export interface BoardFilter {
  /** Free-text match against title, id, and labels. */
  search: string;
  /** Exact assignee match, or '' for any. */
  assignee: string;
  /** Exact category key, or '' for any. */
  category: string;
}

export const EMPTY_FILTER: BoardFilter = { search: '', assignee: '', category: '' };

export function filterTasks(tasks: TaskFragment[], filter: BoardFilter): TaskFragment[] {
  const q = filter.search.trim().toLowerCase();
  return tasks.filter((t) => {
    if (filter.assignee && !t.assignees.includes(filter.assignee)) return false;
    if (filter.category && t.category !== filter.category) return false;
    if (q) {
      const hay = [t.title, t.taskId, ...t.labels].join(' ').toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

/** Distinct assignees across tasks, sorted. */
export function distinctAssignees(tasks: TaskFragment[]): string[] {
  return [...new Set(tasks.flatMap((t) => t.assignees))].sort();
}

/** Distinct category keys across tasks, sorted. */
export function distinctCategories(tasks: TaskFragment[]): string[] {
  return [...new Set(tasks.map((t) => t.category))].sort();
}

export interface MilestoneGroup {
  milestone: string;
  tasks: TaskFragment[];
}

/** Group tasks by milestone, preserving a stable order; unset → "No milestone",
 * always sorted last. */
export function groupByMilestone(tasks: TaskFragment[]): MilestoneGroup[] {
  const NONE = 'No milestone';
  const byMs = new Map<string, TaskFragment[]>();
  for (const t of tasks) {
    const key = t.milestone?.trim() || NONE;
    (byMs.get(key) ?? byMs.set(key, []).get(key)!).push(t);
  }
  return [...byMs.keys()]
    .sort((a, b) => {
      if (a === NONE) return 1;
      if (b === NONE) return -1;
      return a.localeCompare(b);
    })
    .map((milestone) => ({ milestone, tasks: byMs.get(milestone)! }));
}
