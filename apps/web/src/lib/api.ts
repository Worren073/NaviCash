// Cliente HTTP tipado hacia la API Django de NaviCash.
//
// - Access token JWT en memoria (nunca en localStorage).
// - Refresh en cookie httpOnly: se reintenta una vez si el access expira.
// - Errores normalizados a { message, fieldErrors?, code? }.

export interface ApiError {
  message: string;
  code?: string;
  fieldErrors?: Record<string, string[]>;
}

export class ApiErrorClass extends Error {
  status: number;
  code?: string;
  fieldErrors?: Record<string, string[]>;

  constructor(status: number, err: ApiError) {
    super(err.message);
    this.name = "ApiError";
    this.status = status;
    this.code = err.code;
    this.fieldErrors = err.fieldErrors;
  }
}

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";

let accessToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  skipAuth?: boolean;
}

async function tryRefresh(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      const resp = await fetch(`${BASE_URL}/auth/refresh`, { method: "POST", credentials: "include" });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.access) {
        setAccessToken(data.access);
        return true;
      }
      setAccessToken(null);
      return false;
    } catch {
      setAccessToken(null);
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

function normalizeError(status: number, payload: unknown): ApiError {
  if (payload && typeof payload === "object") {
    const p = payload as Record<string, unknown>;
    const message =
      typeof p.detail === "string"
        ? p.detail
        : typeof p.message === "string"
          ? p.message
          : `Error inesperado (${status}).`;
    const fieldErrors: Record<string, string[]> = {};
    if (p.errors && typeof p.errors === "object") {
      for (const [key, value] of Object.entries(p.errors as Record<string, unknown>)) {
        fieldErrors[key] = Array.isArray(value) ? value.map(String) : [String(value)];
      }
    }
    return { message, code: typeof p.code === "string" ? p.code : undefined, fieldErrors };
  }
  return { message: `Error inesperado (${status}).` };
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipAuth = false, headers, ...rest } = options;

  const doFetch = async (): Promise<Response> => {
    const finalHeaders: Record<string, string> = {
      ...(headers as Record<string, string> | undefined),
    };
    if (body !== undefined && !(body instanceof FormData)) {
      finalHeaders["Content-Type"] = "application/json";
    }
    if (!skipAuth && accessToken) {
      finalHeaders["Authorization"] = `Bearer ${accessToken}`;
    }
    return fetch(`${BASE_URL}${path}`, {
      ...rest,
      credentials: "include",
      headers: finalHeaders,
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
    });
  };

  let resp = await doFetch();

  // Access expirado: reintentar una vez tras refrescar.
  if (resp.status === 401 && !skipAuth) {
    const ok = await tryRefresh();
    if (ok) resp = await doFetch();
  }

  if (resp.status === 204) return undefined as T;

  const payload = await resp.json().catch(() => null);

  if (!resp.ok) {
    throw new ApiErrorClass(resp.status, normalizeError(resp.status, payload));
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "DELETE" }),
};

export { BASE_URL };