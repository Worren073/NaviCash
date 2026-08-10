// Cliente HTTP tipado hacia la API Django de NaviCash.
//
// - Access token JWT en memoria (nunca en localStorage).
// - Refresh en cookie httpOnly: se reintenta una vez si el access expira.
// - Timeout por defecto de 10s (AbortSignal.timeout) en requests sin signal.
// - Errores normalizados a { message, fieldErrors?, code? }.
// - Si el refresh falla para una petición autenticada se notifica a un
//   listener global (A11): la app hace logout limpio y navega al login.

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
let sessionExpiredListener: (() => void) | null = null;
let sessionExpiredFlag = false;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

/**
 * Registra el listener global de sesión expirada. Devuelve un unsubscribe.
 * Se invoca cuando el refresh falla para una petición autenticada.
 */
export function onSessionExpired(handler: () => void) {
  sessionExpiredListener = handler;
  return () => {
    if (sessionExpiredListener === handler) sessionExpiredListener = null;
  };
}

/** Lee y consume el flag de "sesión expirada" (para avisar en el login). */
export function consumeSessionExpired(): boolean {
  const expired = sessionExpiredFlag;
  sessionExpiredFlag = false;
  return expired;
}

function notifySessionExpired() {
  sessionExpiredFlag = true;
  sessionExpiredListener?.();
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

const DEFAULT_TIMEOUT_MS = 10_000;

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipAuth = false, signal, headers, ...rest } = options;
  const fetchSignal = signal ?? AbortSignal.timeout(DEFAULT_TIMEOUT_MS);

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
      signal: fetchSignal,
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
    });
  };

  let resp = await doFetch();

  // Access expirado: reintentar una vez tras refrescar. Si el refresh falla
  // en una petición autenticada, la sesión murió: notificar al listener (A11).
  if (resp.status === 401 && !skipAuth) {
    const hadAuth = Boolean(accessToken);
    const ok = await tryRefresh();
    if (ok) {
      resp = await doFetch();
    } else if (hadAuth) {
      notifySessionExpired();
    }
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

export function forgotPassword(email: string) {
  return api.post<{ detail: string }>("/auth/forgot-password", { email });
}

export function resetPassword(token: string, email: string, newPassword: string) {
  return api.post<{ detail: string }>("/auth/reset-password", {
    token,
    email,
    new_password: newPassword,
  });
}

export { BASE_URL };