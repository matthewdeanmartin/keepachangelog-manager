import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideRouter, withInMemoryScrolling } from '@angular/router';

import { routes } from './app.routes';
import { createDevBackendFromConfig, fetchDevConfig } from './core/backend/dev-autoconnect';
import { FetchLike } from './core/backend/github-client';
import { RepoService } from './core/repo.service';
import { SiteModeService, resolveSiteMode } from './core/site-mode';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withInMemoryScrolling({ anchorScrolling: 'enabled' })),
    // Before first render: resolve lite/server mode, then — in local dev,
    // where `npm start` generated /dev-katl.json from ~/katl/katl.env —
    // connect to the KATL server (zero-config dogfooding).
    provideAppInitializer(async () => {
      const siteMode = inject(SiteModeService);
      const repo = inject(RepoService);
      const fetchImpl = globalThis.fetch as unknown as FetchLike;
      const devConfig = await fetchDevConfig(fetchImpl);
      siteMode.mode.set(await resolveSiteMode(fetchImpl, { devConfigPresent: devConfig !== null }));
      if (devConfig) {
        const backend = await createDevBackendFromConfig(devConfig, fetchImpl);
        if (backend) {
          await repo.useBackend(backend).catch(() => {
            /* server offline: keep the default local workspace */
          });
        }
      }
    }),
  ],
};
