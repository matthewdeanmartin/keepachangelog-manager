// Zero-config local dev (npm prestart): if ~/katl/katl.env exists (written
// by `katl init`), emit public/dev-katl.json so the app auto-connects to the
// local KATL server. The output is gitignored and holds a secret — it must
// never be committed or shipped; without katl.env any stale copy is removed.

import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const envPath = join(homedir(), 'katl', 'katl.env');
const outPath = fileURLToPath(new URL('../public/dev-katl.json', import.meta.url));

if (!existsSync(envPath)) {
  rmSync(outPath, { force: true });
  process.exit(0);
}

const text = readFileSync(envPath, 'utf8');
const read = (name) => text.match(new RegExp(`^export ${name}=(\\S+)`, 'm'))?.[1];
const token = read('KATL_TOKEN');
const baseUrl = read('KATL_URL') ?? 'http://localhost:8000';

if (!token) {
  rmSync(outPath, { force: true });
  console.warn(`gen-dev-config: no KATL_TOKEN in ${envPath}; skipping auto-connect`);
  process.exit(0);
}

mkdirSync(fileURLToPath(new URL('../public', import.meta.url)), { recursive: true });
writeFileSync(outPath, JSON.stringify({ baseUrl, token }, null, 2) + '\n');
console.log(`gen-dev-config: wrote public/dev-katl.json (gitignored, local dev only) → ${baseUrl}`);
