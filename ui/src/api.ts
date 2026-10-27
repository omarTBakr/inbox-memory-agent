// Thin client for the FastAPI backend (/api, proxied by Vite in dev).

export type Option = { value: string | number; label: string; [extra: string]: unknown };

export type FieldError = { loc: (string | number)[]; msg: string };

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
  }
  get fieldErrors(): FieldError[] {
    return Array.isArray(this.detail) ? (this.detail as FieldError[]) : [];
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const res = await fetch(`/api${path}`, init);
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? res.statusText);
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

export type SectionConfig = {
  data: Record<string, any>;
  source: "saved" | "default";
  meta: { version: number; updated_at: string } | null;
  valid: boolean;
  errors: FieldError[];
  secrets: Record<string, boolean>;
};

export type SectionSchema = {
  schema: any;
  secrets: { name: string; description: string }[];
};

export type Check = { ok: boolean; detail: string; ms?: number };
