// Zero-config local dev: `npm start` generates /dev-katl.json from
// ~/katl/katl.env (see scripts/gen-dev-config.mjs; the file is gitignored
// and absent in production builds). When it exists, the app connects to the
// KATL server at startup — the end user is never asked to wire up a server.

import { FetchLike } from './github-client';
import { ALL_PROJECTS, KatlMergedBackend, KatlServerBackend } from './katl-server-backend';

const PROJECT_OVERRIDE_KEY = 'katl.workspace.project-override.v1';

/** Remember the user's project choice so a refresh doesn't undo it. */
export function writeProjectOverride(project: string): void {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem(PROJECT_OVERRIDE_KEY, project);
}

export function readProjectOverride(): string | null {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem(PROJECT_OVERRIDE_KEY);
}

export interface DevKatlConfig {
  baseUrl: string;
  token: string;
  /** Optional pinned project; defaults to the server's first project. */
  project?: string;
}

/** The dev config, or null when not running against a generated dev setup. */
export async function fetchDevConfig(fetchImpl: FetchLike): Promise<DevKatlConfig | null> {
  try {
    const response = await fetchImpl('/dev-katl.json', { method: 'GET', headers: {} });
    if (!response.ok) return null;
    const data = (await response.json()) as Partial<DevKatlConfig> | null;
    if (typeof data?.baseUrl === 'string' && typeof data?.token === 'string') {
      return { baseUrl: data.baseUrl, token: data.token, project: data.project };
    }
    return null;
  } catch {
    // index.html comes back for unknown paths on some setups; .json() throws.
    return null;
  }
}

/**
 * A connected-and-ready KATL backend from the dev config, or null when there
 * is no dev config, the server is down, or it has no projects yet. Never
 * throws: auto-connect failing must not break the app's normal startup.
 */
export async function createDevBackend(
  fetchImpl: FetchLike = globalThis.fetch as unknown as FetchLike,
): Promise<KatlServerBackend | null> {
  const config = await fetchDevConfig(fetchImpl);
  if (!config) return null;
  return createDevBackendFromConfig(config, fetchImpl);
}

/** As {@link createDevBackend}, for a caller that already fetched the config. */
export async function createDevBackendFromConfig(
  config: DevKatlConfig,
  fetchImpl: FetchLike = globalThis.fetch as unknown as FetchLike,
): Promise<KatlServerBackend | null> {
  let project = config.project;
  if (!project) {
    try {
      const base = config.baseUrl.replace(/\/$/, '');
      const response = await fetchImpl(`${base}/projects`, {
        method: 'GET',
        headers: { 'X-Katl-Token': config.token },
      });
      if (!response.ok) return null;
      const projects = (await response.json()) as { key: string }[];
      // A project the user picked in the UI beats "whatever came first" —
      // but only if it still exists on the server. "All projects" persists too.
      const override = readProjectOverride();
      if (override === ALL_PROJECTS) {
        return new KatlMergedBackend({ baseUrl: config.baseUrl, token: config.token, fetchImpl });
      }
      project = override && projects.some((p) => p.key === override) ? override : projects[0]?.key;
    } catch {
      return null;
    }
  }
  if (!project) return null;
  return new KatlServerBackend({
    baseUrl: config.baseUrl,
    token: config.token,
    project,
    fetchImpl,
  });
}
