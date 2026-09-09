import { Injectable, computed, signal } from '@angular/core';
import { ChangelogFragment, TaskFragment } from './models';
import {
  changelogFragmentFileName,
  fileStem,
  parseChangelogFragment,
  parseTaskFragment,
  renderChangelogFragment,
  renderTaskFragment,
  slugify,
} from './fragment-parser';
import { RawFile } from './fixtures';
import { FileChange, RepoBackend, SaveResult, WorkspaceIdentity } from './backend/repo-backend';
import { LocalStorageBackend } from './backend/local-storage-backend';

const TICKET_RE = /^tickets\//;
const FRAGMENT_RE = /^changelog\.d\//;

/**
 * The in-browser workspace. Holds raw tickets/*.md and changelog.d/*.md files,
 * parses them into the domain model, tracks dirty edits, and delegates IO to a
 * pluggable {@link RepoBackend} (local-storage today; GitHub PR / filesystem
 * next). The UI never knows which backend is active.
 */
@Injectable({ providedIn: 'root' })
export class RepoService {
  private readonly files = signal<RawFile[]>([]);
  /** path -> change since last scan/commit; null content means delete. */
  private readonly dirty = signal<Map<string, FileChange>>(new Map());
  private backend: RepoBackend = new LocalStorageBackend();
  private saveQueue: Promise<unknown> = Promise.resolve();
  private loadGeneration = 0;
  readonly saveError = signal<string | null>(null);
  readonly backendId = signal<string>(this.backend.id);
  /** Human identity of the active workspace, for the topbar chip etc. */
  readonly identity = signal<WorkspaceIdentity>(this.backend.describe());
  /** True for view-only workspaces (the merged all-projects board): every
   * mutation below is a no-op and the UI hides its editing affordances. */
  readonly readOnly = signal<boolean>(this.backend.capabilities.readOnly === true);

  readonly tasks = computed<TaskFragment[]>(() =>
    this.files()
      .filter((f) => TICKET_RE.test(f.path))
      // repo/project ride alongside the file (server metadata), never inside it.
      .map((f) => ({
        ...parseTaskFragment(f.content, f.path),
        repo: f.repo ?? undefined,
        project: f.project ?? undefined,
      }))
      .sort((a, b) => a.taskId.localeCompare(b.taskId)),
  );

  readonly changelogFragments = computed<ChangelogFragment[]>(() =>
    this.files()
      .filter((f) => FRAGMENT_RE.test(f.path))
      .map((f) => parseChangelogFragment(f.content, f.path))
      .sort((a, b) => a.slug.localeCompare(b.slug)),
  );

  readonly dirtyPaths = computed(() => Array.from(this.dirty().keys()));
  readonly canOpenPr = computed(() => this.backend.capabilities.pullRequest);

  constructor() {
    void this.scan().catch((error: unknown) => this.reportSaveError(error));
  }

  /** The active backend, for backend-specific features (e.g. server conflicts). */
  get activeBackend(): RepoBackend {
    return this.backend;
  }

  /** Switch the active backend and reload from it. */
  async useBackend(backend: RepoBackend): Promise<void> {
    await this.saveQueue;
    if (this.dirty().size) throw new Error('Save pending changes before switching workspaces.');
    const generation = ++this.loadGeneration;
    const loaded = await backend.scan();
    if (generation !== this.loadGeneration) return;
    if (this.dirty().size) throw new Error('The workspace changed while connecting. Save first.');
    this.backend = backend;
    this.backendId.set(backend.id);
    this.identity.set(backend.describe());
    this.readOnly.set(backend.capabilities.readOnly === true);
    this.files.set(loaded);
    this.saveError.set(null);
  }

  /** Load the workspace from the active backend. Clears dirty state. */
  async scan(): Promise<void> {
    const generation = ++this.loadGeneration;
    if (this.dirty().size) throw new Error('Save pending changes before reloading.');
    const loaded = await this.backend.scan();
    if (generation !== this.loadGeneration) return;
    if (this.dirty().size) throw new Error('The workspace changed while loading. Save first.');
    this.files.set(loaded);
    this.dirty.set(new Map());
  }

  /** Reset the local-storage demo workspace to bundled samples. */
  async loadFixtures(): Promise<void> {
    await this.saveQueue;
    if (this.dirty().size) throw new Error('Save pending changes before resetting.');
    ++this.loadGeneration;
    if (this.backend instanceof LocalStorageBackend) {
      this.files.set(this.backend.reset());
      this.dirty.set(new Map());
    } else {
      await this.scan();
    }
  }

  /** Push all dirty changes through the backend (commit / PR / write). */
  async commit(): Promise<SaveResult> {
    const backend = this.backend;
    const pending = this.saveQueue.then(async () => {
      if (backend !== this.backend) throw new Error('Workspace changed before saving.');
      const changes = Array.from(this.dirty().values());
      const result = await backend.save(changes);
      const remaining = new Map(this.dirty());
      for (const change of changes) {
        // Object identity is the revision: an edit during save replaces it.
        if (remaining.get(change.path) === change) remaining.delete(change.path);
      }
      this.dirty.set(remaining);
      this.saveError.set(null);
      return result;
    });
    this.saveQueue = pending.catch((error: unknown) => this.reportSaveError(error));
    return pending;
  }

  getTask(taskId: string): TaskFragment | undefined {
    return this.tasks().find((t) => t.taskId === taskId);
  }

  /** Persist a task fragment, creating or replacing its tickets/*.md file. */
  saveTask(fragment: TaskFragment): void {
    const path = fragment.path || `tickets/${fragment.taskId}.md`;
    this.upsert(path, renderTaskFragment(fragment));
  }

  deleteTask(taskId: string): void {
    const task = this.getTask(taskId);
    if (task) this.remove(task.path);
  }

  /** Update just a ticket's status (used by board drag-and-drop). No-op if the
   * status is unchanged, so a drop onto the same column is a no-op diff. */
  setTaskStatus(taskId: string, status: string): void {
    const task = this.getTask(taskId);
    if (!task || task.status === status) return;
    this.saveTask({ ...task, status });
  }

  /** Create the next sequential ticket id, e.g. "0006-my-slug". */
  nextTaskId(summary: string): string {
    const nums = this.tasks()
      .map((t) => parseInt(t.taskId.split('-')[0], 10))
      .filter((n) => !isNaN(n));
    const next = (nums.length ? Math.max(...nums) : 0) + 1;
    const padded = String(next).padStart(4, '0');
    const slug = slugify(summary) || 'task';
    return `${padded}-${slug}`;
  }

  saveChangelogFragment(slug: string, changeType: string, text: string): string {
    const name = changelogFragmentFileName(slug, changeType);
    const path = `changelog.d/${name}`;
    const content = renderChangelogFragment({
      path,
      slug: fileStem(name),
      changeType,
      text,
      lint: [],
    });
    this.upsert(path, content);
    return path;
  }

  deleteChangelogFragment(path: string): void {
    this.remove(path);
  }

  // --- internal mutation helpers ---

  private upsert(path: string, content: string): void {
    if (this.readOnly()) return;
    const files = [...this.files()];
    const idx = files.findIndex((f) => f.path === path);
    // Spread keeps backend metadata (e.g. repo) across edits.
    if (idx >= 0) files[idx] = { ...files[idx], path, content };
    else files.push({ path, content });
    this.files.set(files);
    this.markDirty({ path, content, op: 'upsert' });
    this.autosave();
  }

  private remove(path: string): void {
    if (this.readOnly()) return;
    this.files.set(this.files().filter((f) => f.path !== path));
    this.markDirty({ path, op: 'delete' });
    this.autosave();
  }

  private markDirty(change: FileChange): void {
    const next = new Map(this.dirty());
    next.set(change.path, change);
    this.dirty.set(next);
  }

  /**
   * Direct-write backends (localStorage, filesystem) persist edits immediately
   * so nothing is lost on refresh. PR backends defer to an explicit commit().
   */
  private autosave(): void {
    if (this.backend.capabilities.directWrite) {
      void this.commit().catch((error: unknown) => this.reportSaveError(error));
    }
  }

  private reportSaveError(error: unknown): void {
    this.saveError.set(error instanceof Error ? error.message : String(error));
  }
}
