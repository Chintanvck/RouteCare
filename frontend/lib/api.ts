/**
 * RouteCare AI - API client.
 *
 * Thin fetch wrapper, not a generated client or a data-fetching library
 * (no react-query/SWR) - the app's data needs are simple enough that
 * adding one would be the kind of dependency Phase 1C's coding
 * standards explicitly warn against.
 *
 * Every backend error follows one envelope (see
 * docs/13_Coding_Standards.md section 5):
 *   {"success": false, "error": {"code","message","details"}, "request_id"}
 * ApiError below carries that shape through to callers.
 */
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./auth";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string; details?: Record<string, unknown> };
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ErrorBody = {};
  try {
    body = await response.json();
  } catch {
    // Non-JSON error body (e.g. a proxy/gateway failure) - fall through to the generic message below.
  }
  return new ApiError(
    response.status,
    body.error?.code ?? "UNKNOWN_ERROR",
    body.error?.message ?? "Something went wrong. Please try again.",
    body.error?.details ?? {}
  );
}

async function tryRefreshAccessToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return false;

  const body = await response.json();
  setTokens(body.access_token, body.refresh_token);
  return true;
}

interface ApiFetchOptions extends RequestInit {
  /** Set false to skip the automatic 401 -> refresh -> retry cycle (used by the refresh call itself). */
  retryOn401?: boolean;
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { retryOn401 = true, headers, ...rest } = options;

  // FormData (file uploads) must NOT get an explicit Content-Type - the
  // browser sets its own multipart boundary, and overriding it breaks parsing.
  const isFormData = typeof FormData !== "undefined" && rest.body instanceof FormData;

  const accessToken = getAccessToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
  });

  if (response.status === 401 && retryOn401) {
    const refreshed = await tryRefreshAccessToken();
    if (refreshed) {
      return apiFetch<T>(path, { ...options, retryOn401: false });
    }
    clearTokens();
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
