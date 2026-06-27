import { defineConfig } from 'vitest/config';

// The test suite covers the pure parser/writer/preview logic in src/app/core,
// which has zero Angular or DOM dependency — so it runs in plain Node, no
// browser, no Karma, no puppeteer.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/app/core/**/*.spec.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/app/core/**/*.ts'],
      exclude: ['src/app/core/**/*.spec.ts', 'src/app/core/fixtures.ts'],
    },
  },
});
