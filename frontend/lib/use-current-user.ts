"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "./api";
import type { CurrentUser } from "@/types/user";

/**
 * Fetches the logged-in user's profile once per mount - shared by every page that needs to
 * render differently by role (Phase 11: dashboard, schedule, optimize, the header nav) so the
 * `/auth/me` call and its loading state aren't reimplemented per page. Callers should gate
 * role-dependent rendering on `loading` being false, since `user` is null both before the fetch
 * resolves and if it fails.
 */
export function useCurrentUser(enabled: boolean): { user: CurrentUser | null; loading: boolean } {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    apiFetch<CurrentUser>("/auth/me")
      .then((result) => {
        if (!cancelled) setUser(result);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { user, loading };
}
