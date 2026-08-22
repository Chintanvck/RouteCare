"use client";

import { useRouter } from "next/navigation";

import { AppHeader } from "@/components/layout/app-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PatientForm, toApiPayload } from "@/components/patients/patient-form";
import { apiFetch, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { Patient, PatientFormValues } from "@/types/patient";

export default function NewPatientPage() {
  const { checked } = useRequireAuth();
  const router = useRouter();

  if (!checked) return null;

  async function handleSubmit(values: PatientFormValues) {
    try {
      const patient = await apiFetch<Patient>("/patients", {
        method: "POST",
        body: JSON.stringify(toApiPayload(values)),
      });
      router.push(`/patients/${patient.id}`);
    } catch (err) {
      throw new Error(err instanceof ApiError ? err.message : "Could not create patient.");
    }
  }

  return (
    <>
      <AppHeader />
      <main className="container max-w-2xl space-y-6 py-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Add patient</h1>
          <p className="text-sm text-muted-foreground">Enter the patient&apos;s scheduling information.</p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Patient details</CardTitle>
          </CardHeader>
          <CardContent>
            <PatientForm submitLabel="Create patient" onSubmit={handleSubmit} onCancel={() => router.push("/patients")} />
          </CardContent>
        </Card>
      </main>
    </>
  );
}
