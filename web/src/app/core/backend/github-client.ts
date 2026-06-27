// A thin GitHub REST client over fetch — just the endpoints the backend needs.
// No Octokit dependency: keeps the bundle small and the request logic trivially
// unit-testable by injecting a fake `fetch`.
//
// The token is held only here and sent only to api.github.com (see the security
// model in spec/web_gui.md §11).

export type FetchLike = (
  url: string,
  init: { method: string; headers: Record<string, string>; body?: string },
) => Promise<{ ok: boolean; status: number; json(): Promise<unknown>; text(): Promise<string> }>;

export interface GitHubClientOptions {
  token: string;
  /** Override for tests; defaults to global fetch. */
  fetchImpl?: FetchLike;
  /** Override for tests; defaults to the public API. */
  baseUrl?: string;
}

export class GitHubError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'GitHubError';
  }
}

export class GitHubClient {
  private readonly token: string;
  private readonly fetchImpl: FetchLike;
  private readonly baseUrl: string;

  constructor(opts: GitHubClientOptions) {
    this.token = opts.token;
    this.fetchImpl = opts.fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
    this.baseUrl = (opts.baseUrl ?? 'https://api.github.com').replace(/\/$/, '');
  }

  async request<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const res = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      let detail = '';
      try {
        detail = ((await res.json()) as { message?: string })?.message ?? '';
      } catch {
        detail = await res.text().catch(() => '');
      }
      throw new GitHubError(
        res.status,
        detail || `GitHub ${method} ${path} failed (${res.status})`,
      );
    }
    if (res.status === 204) return undefined as T;
    return res.json() as Promise<T>;
  }

  /** Verify the token and return the authenticated login. */
  async whoAmI(): Promise<string> {
    const user = await this.request<{ login: string }>('GET', '/user');
    return user.login;
  }
}
