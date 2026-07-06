// Pure state + helpers for the Conflicts screen. Kept Angular-DOM-free so it
// runs under the plain-Node vitest suite; the feature component is a thin
// template over ConflictsScreen.

import { computed, signal } from '@angular/core';
import { ConflictChoice, KatlConflict, KatlConflictsClient } from './backend/katl-conflicts-client';
import { KatlServerError } from './backend/katl-http';

/** Sentinel field: the ticket's file was deleted remotely. */
export const FILE_FIELD = '__file__';

export const FILE_CONFLICT_MESSAGE =
  'A developer deleted this file — deleting a file does not close a ticket.';

export function isFileConflict(c: KatlConflict): boolean {
  return c.field === FILE_FIELD;
}

export function isBodyConflict(c: KatlConflict): boolean {
  return c.field === 'body_md';
}

/** Human label for a conflict field name. */
export function conflictFieldLabel(field: string): string {
  if (field === FILE_FIELD) return 'file deleted';
  if (field === 'body_md') return 'body';
  const custom = /^custom\.(.+)$/.exec(field);
  if (custom) return `${custom[1]} (custom field)`;
  return field;
}

export interface ConflictGroup {
  taskId: string;
  conflicts: KatlConflict[];
}

/** Group conflicts by task id (groups sorted by id, rows by field then id). */
export function groupConflicts(conflicts: KatlConflict[]): ConflictGroup[] {
  const byTask = new Map<string, KatlConflict[]>();
  for (const c of conflicts) {
    const list = byTask.get(c.task_id);
    if (list) list.push(c);
    else byTask.set(c.task_id, [c]);
  }
  return Array.from(byTask.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([taskId, list]) => ({
      taskId,
      conflicts: [...list].sort((a, b) => a.field.localeCompare(b.field) || a.id - b.id),
    }));
}

/** What just happened, for the status line. */
function resolvedMessage(c: KatlConflict, choice: ConflictChoice): string {
  const what = isFileConflict(c)
    ? choice === 'theirs'
      ? 'Archived ticket'
      : 'Restored file'
    : choice === 'ours'
      ? 'Kept server value'
      : choice === 'theirs'
        ? 'Took incoming value'
        : 'Used custom value';
  return `${what} for ${c.task_id} · ${conflictFieldLabel(c.field)}.`;
}

/** Signal-based screen state: load the conflict list, resolve rows one by one. */
export class ConflictsScreen {
  readonly conflicts = signal<KatlConflict[]>([]);
  readonly groups = computed(() => groupConflicts(this.conflicts()));
  readonly loading = signal(false);
  readonly loaded = signal(false);
  readonly status = signal('');
  readonly isError = signal(false);

  constructor(private readonly client: KatlConflictsClient) {}

  async load(): Promise<void> {
    this.loading.set(true);
    this.isError.set(false);
    this.status.set('');
    try {
      this.conflicts.set(await this.client.listConflicts());
      this.loaded.set(true);
    } catch (e) {
      this.isError.set(true);
      this.status.set(this.describe(e));
    } finally {
      this.loading.set(false);
    }
  }

  /** Resolve one conflict; on success remove its row and report what happened. */
  async resolve(conflict: KatlConflict, choice: ConflictChoice, value?: string): Promise<void> {
    this.isError.set(false);
    this.status.set('');
    try {
      await this.client.resolveConflict(conflict.id, choice, value);
      this.conflicts.update((list) => list.filter((c) => c.id !== conflict.id));
      this.status.set(resolvedMessage(conflict, choice));
    } catch (e) {
      this.isError.set(true);
      this.status.set(this.describe(e));
    }
  }

  private describe(e: unknown): string {
    return e instanceof KatlServerError
      ? `KATL server error (${e.status}): ${e.message}`
      : `Failed: ${(e as Error).message}`;
  }
}
