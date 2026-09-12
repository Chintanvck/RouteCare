"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";

import { UserMenu } from "@/components/layout/user-menu";
import { useCurrentUser } from "@/lib/use-current-user";

interface NavLink {
  href: string;
  label: string;
}

export function AppHeader() {
  // AppHeader only ever mounts on an already-authenticated page (every page renders it after its
  // own useRequireAuth check passes), so there's no "not logged in yet" case to gate this on.
  const { user } = useCurrentUser(true);
  const isTherapist = user?.role === "THERAPIST";
  const [mobileOpen, setMobileOpen] = useState(false);

  // A route change (or resizing past the mobile breakpoint) should never leave the panel open
  // underneath the new page.
  useEffect(() => {
    setMobileOpen(false);
  }, [isTherapist]);

  const links: NavLink[] = [
    { href: "/dashboard", label: "Dashboard" },
    { href: "/schedule", label: isTherapist ? "My Schedule" : "Schedule" },
    { href: "/patients", label: "Patients" },
    // A THERAPIST's own /therapists list is just their own single record (see
    // app.services.therapist_service.list_therapists' restrict_to_therapist_id) - not worth a nav
    // link of its own for them.
    ...(isTherapist ? [] : [{ href: "/therapists", label: "Therapists" }]),
    { href: "/map", label: "Map" },
    { href: "/optimize", label: "Optimize" },
  ];

  return (
    <header className="relative border-b bg-background">
      <div className="container flex h-14 items-center justify-between gap-2">
        <Link
          href={isTherapist ? "/dashboard" : "/patients"}
          className="shrink-0 font-semibold tracking-tight"
          onClick={() => setMobileOpen(false)}
        >
          RouteCare AI
        </Link>

        {/* Tablet/desktop: the full link row inline, same as before. */}
        <nav className="hidden flex-1 items-center gap-6 px-6 sm:flex">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="shrink-0 text-sm text-muted-foreground hover:text-foreground"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-1">
          {/* Mobile: a hamburger toggle instead of forcing every link into one scrolling row. */}
          <button
            type="button"
            onClick={() => setMobileOpen((prev) => !prev)}
            aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
            aria-expanded={mobileOpen}
            aria-controls="mobile-nav-panel"
            className="flex h-9 w-9 items-center justify-center rounded-md text-foreground hover:bg-accent sm:hidden"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          {user && <UserMenu user={user} />}
        </div>
      </div>

      {mobileOpen && (
        <nav id="mobile-nav-panel" className="border-t bg-background sm:hidden">
          <ul className="flex flex-col py-1">
            {links.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  onClick={() => setMobileOpen(false)}
                  className="block px-4 py-3 text-base text-foreground hover:bg-accent"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </header>
  );
}
