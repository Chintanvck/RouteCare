"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { clearTokens } from "@/lib/auth";

export function AppHeader() {
  const router = useRouter();

  function handleLogout() {
    clearTokens();
    router.push("/login");
  }

  return (
    <header className="border-b bg-background">
      <div className="container flex h-14 items-center justify-between">
        <nav className="flex items-center gap-6">
          <Link href="/patients" className="font-semibold tracking-tight">
            RouteCare AI
          </Link>
          <Link href="/patients" className="text-sm text-muted-foreground hover:text-foreground">
            Patients
          </Link>
          <Link href="/therapists" className="text-sm text-muted-foreground hover:text-foreground">
            Therapists
          </Link>
          <Link href="/schedule" className="text-sm text-muted-foreground hover:text-foreground">
            Schedule
          </Link>
        </nav>
        <Button variant="ghost" size="sm" onClick={handleLogout}>
          Log out
        </Button>
      </div>
    </header>
  );
}
