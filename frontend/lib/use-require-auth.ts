"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { isAuthenticated } from "./auth";

/**
 * Client-side route guard. There's no server-side session (the access
 * token lives in localStorage, not a cookie), so this can only redirect
 * after the initial render - acceptable for an internal clinic tool
 * where a one-frame flash isn't a real concern. `checked` gates
 * rendering the protected content until the redirect decision is made.
 */
export function useRequireAuth(): { checked: boolean } {
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
    } else {
      setChecked(true);
    }
  }, [router]);

  return { checked };
}
