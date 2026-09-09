// Lite vs server: the two product shapes of the same app (spec/sprint_09.md).
//
//   * lite   — the freemium static site. Everything that runs entirely in the
//              browser: sample workspace, local folder, GitHub PAT. The KATL
//              Co server backend is not offered; Conflicts is hidden.
//   * server — the paid hosted deployment (and local dev): the full app,
//              including the KATL Co server backend.
//
// The mode is a deploy-time switch, not an entitlement check: a hosted server
// still authenticates every request by token. Resolution order:
//   1. /site-mode.json ({"mode": "server"} | {"mode": "lite"}) — how a deploy
//      declares itself. Absent from the default static build, so the public
//      freemium site is lite by construction.
//   2. A present /dev-katl.json (local dev autoconnect) implies server.
//   3. Default: lite.

import { Injectable, computed, signal } from '@angular/core';
import { FetchLike } from './backend/github-client';

export type SiteMode = 'lite' | 'server';

export async function resolveSiteMode(
  fetchImpl: FetchLike,
  options: { devConfigPresent: boolean },
): Promise<SiteMode> {
  try {
    const response = await fetchImpl('/site-mode.json', { method: 'GET', headers: {} });
    if (response.ok) {
      const data = (await response.json()) as { mode?: string } | null;
      if (data?.mode === 'server' || data?.mode === 'lite') return data.mode;
    }
  } catch {
    // index.html comes back for unknown paths on some setups; .json() throws.
  }
  return options.devConfigPresent ? 'server' : 'lite';
}

@Injectable({ providedIn: 'root' })
export class SiteModeService {
  /** Resolved once at startup (app initializer); defaults to lite. */
  readonly mode = signal<SiteMode>('lite');
  readonly isLite = computed(() => this.mode() === 'lite');
}
