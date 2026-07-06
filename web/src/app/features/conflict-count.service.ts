import { Injectable, signal } from '@angular/core';

/**
 * Open-conflict count shared between the Conflicts screen (which sets it after
 * loading/resolving) and the top nav (which shows "Conflicts (n)"). Null means
 * "unknown" — e.g. not connected to a KATL Co server yet.
 */
@Injectable({ providedIn: 'root' })
export class ConflictCountService {
  readonly count = signal<number | null>(null);
}
