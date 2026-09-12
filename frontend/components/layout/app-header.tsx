"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { clearTokens } from "@/lib/auth";
import { useCurrentUser } from "@/lib/use-current-user";

export function AppHeader() {
  const router = useRouter();
  // AppHeader only ever mounts on an already-authenticated page (every page renders it after its
  // own useRequireAuth check passes), so there's no "not logged in yet" case to gate this on.
  const { user } = useCurrentUser(true);
  const isTherapist = user?.role === "THERAPIST";

  function handleLogout() {
    clearTokens();
    router.push("/login");
  }

  return (
    <header className="border-b bg-background">
      <div className="container flex h-14 items-center justify-between gap-2">
        <nav className="flex items-center gap-4 overflow-x-auto sm:gap-6">
          <Link href={isTherapist ? "/dashboard" : "/patients"} className="shrink-0 font-semibold tracking-tight">
            RouteCare AI
          </Link>
          <Link href="/dashboard" className="shrink-0 text-sm text-muted-foreground hover:text-foreground">
            Dashboard
          </Link>
          <Link href="/schedule" className="shrink-0 text-sm text-muted-foreground hover:text-foreground">
            {isTherapist ? "My Schedule" : "Schedule"}
          </Link>
          <Link href="/patients" className="shrink-0 text-sm text-muted-foreground hover:text-foreground">
            Patients
          </Link>
          {/* A THERAPIST's own /therapists list is just their own single record (see
              app.services.therapist_service.list_therapists' restrict_to_therapist_id) - not
              worth a nav link of its own for them. */}
          {!isTherapist && (
            <Link href="/therapists" className="shrink-0 text-sm text-muted-foreground hover:text-foreground">
              Therapists
            </Link>
          )}
          <Link href="/map" className="shrink-0 text-sm text-muted-foreground hover:text-foreground">
            Map
          </Link>
          <Link href="/optimize" className="shrink-0 text-sm text-muted-foreground hover:text-foreground">
            Optimize
          </Link>
        </nav>
        <Button variant="ghost" size="sm" className="shrink-0" onClick={handleLogout}>
          Log out
        </Button>
      </div>
    </header>
  );
}
