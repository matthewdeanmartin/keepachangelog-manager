// Release-readiness report: cross-checks tickets against changelog fragments so
// a release manager sees gaps before opening the PR. Pure + tested; the Preview
// screen renders it. See spec/web_remaining_phases.md §7 (W4).

import { ChangelogFragment, TaskFragment, shipsToChangelog } from './models';

export interface ReadinessReport {
  /** done + shipping tickets with no changelog fragment whose slug == taskId. */
  doneMissingFragment: TaskFragment[];
  /** changelog fragments whose slug matches no ticket id. */
  orphanFragments: ChangelogFragment[];
  /** tickets that have been in-progress/blocked (i.e. started but not done). */
  stuckTickets: TaskFragment[];
  /** true when nothing blocks a clean release. */
  ready: boolean;
}

const STUCK_STATUSES = new Set(['in-progress', 'blocked']);

export function buildReadinessReport(
  tasks: TaskFragment[],
  fragments: ChangelogFragment[],
): ReadinessReport {
  const fragSlugs = new Set(fragments.map((f) => f.slug));
  const taskIds = new Set(tasks.map((t) => t.taskId));

  const doneMissingFragment = tasks.filter(
    (t) => t.status === 'done' && shipsToChangelog(t.category) && !fragSlugs.has(t.taskId),
  );
  const orphanFragments = fragments.filter((f) => !taskIds.has(f.slug));
  const stuckTickets = tasks.filter((t) => STUCK_STATUSES.has(t.status));

  return {
    doneMissingFragment,
    orphanFragments,
    stuckTickets,
    ready: doneMissingFragment.length === 0 && orphanFragments.length === 0,
  };
}
