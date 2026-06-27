import { Injectable, computed, signal } from '@angular/core';
import {
  ChangelogFragment,
  TaskFragment,
} from './models';
import {
  changelogFragmentFileName,
  fileStem,
  parseChangelogFragment,
  parseTaskFragment,
  renderChangelogFragment,
  renderTaskFragment,
  slugify,
} from './fragment-parser';
import {
  FIXTURE_CHANGELOG_FRAGMENTS,
  FIXTURE_TICKETS,
  RawFile,
} from './fixtures';

const STORAGE_KEY = 'katl.workspace.v1';

interface PersistedWorkspace {
  tickets: RawFile[];
  changelog: RawFile[];
}

/**
 * The in-browser workspace: holds raw tickets/*.md and changelog.d/*.md files,
 * parses them into the domain model, and persists edits to localStorage.
 *
 * This is the "local fixtures first" backend. A GitHub-backed implementation can
 * later populate the same raw-file set (scan) and consume `dirtyFiles()` to open
 * a branch + PR, without the UI changing.
 */
@Injectable({ providedIn: 'root' })
export class RepoService {
  private readonly ticketFiles = signal<RawFile[]>([]);
  private readonly changelogFiles = signal<RawFile[]>([]);
  /** Paths edited since the workspace was loaded/scanned (for the PR layer). */
  private readonly dirty = signal<Set<string>>(new Set());

  readonly tasks = computed<TaskFragment[]>(() =>
    this.ticketFiles()
      .map((f) => parseTaskFragment(f.content, f.path))
      .sort((a, b) => a.taskId.localeCompare(b.taskId)),
  );

  readonly changelogFragments = computed<ChangelogFragment[]>(() =>
    this.changelogFiles()
      .map((f) => parseChangelogFragment(f.content, f.path))
      .sort((a, b) => a.slug.localeCompare(b.slug)),
  );

  readonly dirtyPaths = computed(() => Array.from(this.dirty()));

  constructor() {
    this.load();
  }

  /** Reset to the bundled sample workspace. */
  loadFixtures(): void {
    this.ticketFiles.set([...FIXTURE_TICKETS.map((f) => ({ ...f }))]);
    this.changelogFiles.set([...FIXTURE_CHANGELOG_FRAGMENTS.map((f) => ({ ...f }))]);
    this.dirty.set(new Set());
    this.persist();
  }

  private load(): void {
    const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
    if (!raw) {
      this.loadFixtures();
      return;
    }
    try {
      const data = JSON.parse(raw) as PersistedWorkspace;
      this.ticketFiles.set(data.tickets ?? []);
      this.changelogFiles.set(data.changelog ?? []);
    } catch {
      this.loadFixtures();
    }
  }

  private persist(): void {
    if (typeof localStorage === 'undefined') return;
    const data: PersistedWorkspace = {
      tickets: this.ticketFiles(),
      changelog: this.changelogFiles(),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  }

  getTask(taskId: string): TaskFragment | undefined {
    return this.tasks().find((t) => t.taskId === taskId);
  }

  /** Persist a task fragment, creating or replacing its tickets/*.md file. */
  saveTask(fragment: TaskFragment): void {
    const content = renderTaskFragment(fragment);
    const path = fragment.path || `tickets/${fragment.taskId}.md`;
    const files = [...this.ticketFiles()];
    const idx = files.findIndex((f) => f.path === path);
    if (idx >= 0) files[idx] = { path, content };
    else files.push({ path, content });
    this.ticketFiles.set(files);
    this.markDirty(path);
    this.persist();
  }

  deleteTask(taskId: string): void {
    const task = this.getTask(taskId);
    if (!task) return;
    this.ticketFiles.set(this.ticketFiles().filter((f) => f.path !== task.path));
    this.markDirty(task.path);
    this.persist();
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
    const content = renderChangelogFragment({ path, slug: fileStem(name), changeType, text, lint: [] });
    const files = [...this.changelogFiles()];
    const idx = files.findIndex((f) => f.path === path);
    if (idx >= 0) files[idx] = { path, content };
    else files.push({ path, content });
    this.changelogFiles.set(files);
    this.markDirty(path);
    this.persist();
    return path;
  }

  deleteChangelogFragment(path: string): void {
    this.changelogFiles.set(this.changelogFiles().filter((f) => f.path !== path));
    this.markDirty(path);
    this.persist();
  }

  private markDirty(path: string): void {
    const next = new Set(this.dirty());
    next.add(path);
    this.dirty.set(next);
  }

  clearDirty(): void {
    this.dirty.set(new Set());
  }
}
