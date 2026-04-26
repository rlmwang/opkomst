let _token: string | null = localStorage.getItem("token");

export function setToken(token: string): void {
  _token = token;
  localStorage.setItem("token", token);
}

export function clearToken(): void {
  _token = null;
  localStorage.removeItem("token");
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
export const del = <T>(path: string) => api<T>(path, { method: "DELETE" });
