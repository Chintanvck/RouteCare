"use client";

import { useRouter } from "next/navigation";

import { AppHeader } from "@/components/layout/app-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TherapistForm, toApiPayload } from "@/components/therapists/therapist-form";
import { apiFetch, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { Therapist, TherapistFormValues } from "@/types/therapist";

export default function NewTherapistPage() {
  const { checked } = useRequireAuth();
  const router = useRouter();

  if (!checked) return null;

  async function handleSubmit(values: TherapistFormValues) {
    try {
      const therapist = await apiFetch<Therapist>("/therapists", {
        method: "POST",
        body: JSON.stringify(toApiPayload(values, "create")),
      });
      router.push(`/therapists/${therapist.id}`);
    } catch (err) {
      throw new Error(err instanceof ApiError ? err.message : "Could not create therapist.");
    }
  }

  return (
    <>
      <AppHeader />
      <main className="container max-w-2xl space-y-6 py-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Add therapist</h1>
          <p className="text-sm text-muted-foreground">
            Creates a login for the therapist and their profile in one step.
          </p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Therapist details</CardTitle>
          </CardHeader>
          <CardContent>
            <TherapistForm
              mode="create"
              submitLabel="Create therapist"
              onSubmit={handleSubmit}
              onCancel={() => router.push("/therapists")}
            />
          </CardContent>
        </Card>
      </main>
    </>
  );
}
