import { brand, isPersonalApp } from "@/lib/branding";

// The session is per organisation, not per browser. localStorage is
// shared by everything on the origin, so a single ``token`` key meant
// that signing in to one tenant carried straight over to another
// tenant's URLs: the page wore their brand and showed ours. The API
// scopes every read by the token's own tenant, so nothing leaked
// across — but the page and the session disagreed, which is its own
// bug. Keying by tenant makes them agree, and lets someone hold two
// sessions in two tabs.
// The root's key is ``token:personal``, not the house brand's slug: the
// key names the app you are signed in to, and every personal account
// shares one app. An organisation session and a personal one can then
// sit in two tabs without either standing in for the other.
const TOKEN_KEY = isPersonalApp() ? "token:personal" : `token:${brand().slug}`;

let _token: string | null = localStorage.getItem(TOKEN_KEY);

export function setToken(token: string): void {
  _token = token;
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  _token = null;
  localStorage.removeItem(TOKEN_KEY);
}

export function getToken(): string | null {
  return _token;
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

/** The first field-level problem in a FastAPI 422 response, or ``null``
 * for any other error. Lets a form surface *which* field and *why* in
 * the user's language instead of collapsing everything to a generic
 * "save failed". ``field`` is the last string segment of Pydantic's
 * ``loc`` (skipping the ``"body"`` prefix); ``limit`` is the character
 * cap for a ``string_too_long``. */
export interface FieldError {
  field: string;
  type: string;
  limit?: number;
}

export function firstFieldError(err: unknown): FieldError | null {
  if (!(err instanceof ApiError) || err.status !== 422) return null;
  const detail = (err.body as { detail?: unknown } | undefined)?.detail;
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const first = detail[0] as {
    loc?: unknown[];
    type?: string;
    ctx?: { max_length?: number };
  };
  const loc = Array.isArray(first.loc) ? first.loc : [];
  const field = [...loc]
    .reverse()
    .find((p): p is string => typeof p === "string" && p !== "body");
  return {
    field: field ?? "",
    type: String(first.type ?? ""),
    limit: first.ctx?.max_length,
  };
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (_token) headers["Authorization"] = `Bearer ${_token}`;

  const resp = await fetch(path, { ...init, headers });

  if (resp.status === 401) {
    clearToken();
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    let body: unknown = undefined;
    try {
      body = await resp.json();
      if (body && typeof (body as { detail?: unknown }).detail === "string") {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      /* non-JSON */
    }
    throw new ApiError(resp.status, detail, body);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const get = <T>(path: string) => api<T>(path);
export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined });
export const patch = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "PATCH",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
export const put = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "PUT", body: body !== undefined ? JSON.stringify(body) : undefined });
export const del = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "DELETE",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

/** ``POST`` a multipart form with a single ``file`` part. Used by
 * the event-image upload route. The default ``Content-Type:
 * application/json`` is dropped — ``fetch`` infers
 * ``multipart/form-data; boundary=…`` from the ``FormData`` body
 * and a manual override would corrupt it. */
export async function postFile<T>(path: string, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  const headers: Record<string, string> = {};
  if (_token) headers["Authorization"] = `Bearer ${_token}`;
  const resp = await fetch(path, { method: "POST", body: fd, headers });
  if (resp.status === 401) clearToken();
  if (!resp.ok) {
    let detail = resp.statusText;
    let body: unknown = undefined;
    try {
      body = await resp.json();
      if (body && typeof (body as { detail?: unknown }).detail === "string") {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      /* non-JSON */
    }
    throw new ApiError(resp.status, detail, body);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}
