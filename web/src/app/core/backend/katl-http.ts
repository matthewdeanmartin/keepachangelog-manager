// Shared HTTP plumbing for the KATL Co server: X-Katl-Token auth, JSON
// bodies, and {"detail": "..."} error surfacing. Used by the katl-server
// backend and the conflicts client.

import { FetchLike } from './github-client';

export class KatlServerError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'KatlServerError';
  }
}

/** One authenticated JSON request against the KATL server. */
export async function katlRequest<T = unknown>(
  fetchImpl: FetchLike,
  token: string,
  method: string,
  url: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { 'X-Katl-Token': token };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetchImpl(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = '';
    try {
      detail = ((await res.json()) as { detail?: string })?.detail ?? '';
    } catch {
      detail = await res.text().catch(() => '');
    }
    throw new KatlServerError(
      res.status,
      detail || `KATL server ${method} ${url} failed (${res.status})`,
    );
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
