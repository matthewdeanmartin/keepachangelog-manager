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
import { FileChange, RepoBackend, SaveResult } from './backend/repo-backend';
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
  readonly backendId = signal<string>(this.backend.id);

  readonly tasks = computed<TaskFragment[]>(() =>
    this.files()
      .filter((f) => TICKET_RE.test(f.path))
      .map((f) => parseTaskFragment(f.content, f.path))
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
    void this.scan();
  }

  /** Switch the active backend and reload from it. */
  async useBackend(backend: RepoBackend): Promise<void> {
    this.backend = backend;
    this.backendId.set(backend.id);
    await this.scan();
  }

  /** Load the workspace from the active backend. Clears dirty state. */
  async scan(): Promise<void> {
    const loaded = await this.backend.scan();
    this.files.set(loaded);
    this.dirty.set(new Map());
  }

  /** Reset the local-storage demo workspace to bundled samples. */
  async loadFixtures(): Promise<void> {
    if (this.backend instanceof LocalStorageBackend) {
      this.files.set(this.backend.reset());
      this.dirty.set(new Map());
    } else {
      await this.scan();
    }
  }

  /** Push all dirty changes through the backend (commit / PR / write). */
  async commit(): Promise<SaveResult> {
    const changes = Array.from(this.dirty().values());
    const result = await this.backend.save(changes);
    this.dirty.set(new Map());
    return result;
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
    const files = [...this.files()];
    const idx = files.findIndex((f) => f.path === path);
    if (idx >= 0) files[idx] = { path, content };
    else files.push({ path, content });
    this.files.set(files);
    this.markDirty({ path, content, op: 'upsert' });
    void this.autosave();
  }

  private remove(path: string): void {
    this.files.set(this.files().filter((f) => f.path !== path));
    this.markDirty({ path, op: 'delete' });
    void this.autosave();
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
  private async autosave(): Promise<void> {
    if (this.backend.capabilities.directWrite) {
      await this.backend.save(Array.from(this.dirty().values()));
      this.dirty.set(new Map());
    }
  }
}
