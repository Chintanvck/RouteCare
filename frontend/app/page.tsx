import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-3xl font-semibold tracking-tight">RouteCare AI</h1>
      <p className="max-w-md text-muted-foreground">
        Project foundation is set up: Next.js, TypeScript, Tailwind CSS, and
        shadcn/ui are wired together. Feature screens (calendar, patients,
        optimization) are built in later phases.
      </p>
      <Button>Foundation Ready</Button>
    </main>
  );
}