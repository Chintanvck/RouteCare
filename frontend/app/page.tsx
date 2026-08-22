import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-3xl font-semibold tracking-tight">RouteCare AI</h1>
      <p className="max-w-md text-muted-foreground">
        AI-powered scheduling and route optimization for home healthcare
        providers. Patient management is live; scheduling, imports, and
        optimization are built in later phases.
      </p>
      <Button asChild>
        <Link href="/login">Sign in</Link>
      </Button>
    </main>
  );
}