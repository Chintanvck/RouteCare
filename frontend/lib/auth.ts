/**
 * RouteCare AI - client-side token storage.
 *
 * Deliberately minimal: no auth context/provider, no global state
 * library. Tokens live in localStorage and are read/written directly -
 * enough for the login + protected-pages flow Phase 2 needs. A real
 * auth context (current user, role-based UI gating) can be layered on
 * top of this later without changing the storage contract.
 */

const ACCESS_TOKEN_KEY = "routecare_access_token";
const REFRESH_TOKEN_KEY = "routecare_refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(accessToken: string, refreshToken: string): void {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearTokens(): void {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return getAccessToken() !== null;
}
