"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { clearTokens } from "@/lib/auth";
import type { CurrentUser } from "@/types/user";

/** SYSTEM_ADMIN -> "System Admin", OFFICE_SCHEDULER -> "Office Scheduler", etc. - generic so a
 * future role enum value formats correctly without a hardcoded lookup table. */
function formatRole(role: string): string {
  return role
    .toLowerCase()
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function initialsOf(user: CurrentUser): string {
  const first = user.first_name.trim().charAt(0);
  const last = user.last_name.trim().charAt(0);
  return `${first}${last}`.toUpperCase();
}

interface UserMenuProps {
  user: CurrentUser;
}

/**
 * Avatar + name/role indicator for the app header, with a small dropdown (name, role, email,
 * logout). There's no profile-photo support anywhere in the data model, so the avatar is always
 * the initials fallback the task explicitly allows - never a placeholder that needs an upload
 * flow. Reuses the exact same logout mechanism app-header.tsx already had (clearTokens + redirect
 * to /login); this component doesn't introduce any new auth behavior, just relocates that one
 * button into the menu.
 */
export function UserMenu({ user }: UserMenuProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleOutsideClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  function handleLogout() {
    clearTokens();
    router.push("/login");
  }

  const fullName = `${user.first_name} ${user.last_name}`;
  const roleLabel = formatRole(user.role);

  return (
    <div ref={containerRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-md px-1.5 py-1 text-sm hover:bg-accent sm:px-2"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
          {initialsOf(user)}
        </span>
        <span className="hidden text-left leading-tight sm:block">
          <span className="block font-medium">{fullName}</span>
          <span className="block text-xs text-muted-foreground">{roleLabel}</span>
        </span>
        <span className="hidden text-muted-foreground sm:inline" aria-hidden="true">
          &#9662;
        </span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-2 w-56 rounded-md border bg-card text-card-foreground shadow-lg"
        >
          <div className="border-b px-3 py-2.5">
            <p className="text-sm font-medium">{fullName}</p>
            <p className="text-xs text-muted-foreground">{roleLabel}</p>
            <p className="mt-1 text-xs text-muted-foreground">{user.email}</p>
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={handleLogout}
            className="block w-full rounded-b-md px-3 py-2.5 text-left text-sm hover:bg-accent"
          >
            Log out
          </button>
        </div>
      )}
    </div>
  );
}
