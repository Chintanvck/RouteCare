"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { AppHeader } from "@/components/layout/app-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { LocationCard } from "@/components/maps/location-card";
import { PatientForm, toApiPayload, valuesFromPatient } from "@/components/patients/patient-form";
import { apiFetch, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { Patient, PatientFormValues } from "@/types/patient";
import type { PatientGeocodeResponse } from "@/types/maps";

export default function PatientDetailPage() {
  const { checked } = useRequireAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();

  const [patient, setPatient] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!checked) return;
    let cancelled = false;

    (async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await apiFetch<Patient>(`/patients/${params.id}`);
        if (!cancelled) setPatient(result);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError && err.status === 404
              ? "This patient could not be found."
              : "Could not load this patient. Please try again."
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [checked, params.id]);

  async function handleUpdate(values: PatientFormValues) {
    try {
      const updated = await apiFetch<Patient>(`/patients/${params.id}`, {
        method: "PATCH",
        body: JSON.stringify(toApiPayload(values)),
      });
      setPatient(updated);
      setEditing(false);
    } catch (err) {
      throw new Error(err instanceof ApiError ? err.message : "Could not update patient.");
    }
  }

  async function handleDelete() {
    try {
      await apiFetch<void>(`/patients/${params.id}`, { method: "DELETE" });
      router.push("/patients");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete patient. Please try again.");
    }
  }

  if (!checked) return null;

  return (
    <>
      <AppHeader />
      <main className="container max-w-2xl space-y-6 py-8">
        {loading && (
          <div className="space-y-3">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-48 w-full" />
          </div>
        )}

        {!loading && error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {!loading && !error && patient && !editing && (
          <>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">
                  {patient.first_name} {patient.last_name}
                </h1>
                <Badge variant={patient.is_active ? "default" : "secondary"} className="mt-1">
                  {patient.is_active ? "Active" : "Inactive"}
                </Badge>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setEditing(true)}>
                  Edit
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="destructive">Delete</Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete this patient?</AlertDialogTitle>
                      <AlertDialogDescription>
                        {patient.first_name} {patient.last_name} will be removed from your active patient list.
                        This can be reversed by an administrator if needed.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction onClick={handleDelete}>Delete patient</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Basic information</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
                <Field label="Phone" value={patient.phone} />
                <Field label="Email" value={patient.email} />
                <Field
                  label="Address"
                  value={`${patient.address_line_1}${patient.address_line_2 ? ", " + patient.address_line_2 : ""}, ${patient.city}, ${patient.state} ${patient.zip_code}`}
                />
                <Field
                  label="Visit duration"
                  value={patient.visit_duration_minutes ? `${patient.visit_duration_minutes} minutes` : null}
                />
                <Field label="Priority" value={patient.priority_level ? String(patient.priority_level) : null} />
                <Field label="Notes" value={patient.scheduling_notes} />
              </CardContent>
            </Card>

            <LocationCard
              latitude={patient.latitude}
              longitude={patient.longitude}
              geocodingStatus={patient.geocoding_status}
              geocodedAt={patient.geocoded_at}
              locationVerified={patient.location_verified}
              onGeocode={async () => {
                const result = await apiFetch<PatientGeocodeResponse>(`/patients/${params.id}/geocode`, { method: "POST" });
                setPatient(result.patient);
                return { success: result.success, normalizedAddress: result.normalized_address };
              }}
            />
          </>
        )}

        {!loading && !error && patient && editing && (
          <Card>
            <CardHeader>
              <CardTitle>Edit patient</CardTitle>
            </CardHeader>
            <CardContent>
              <PatientForm
                initialValues={valuesFromPatient(patient)}
                submitLabel="Save changes"
                onSubmit={handleUpdate}
                onCancel={() => setEditing(false)}
              />
            </CardContent>
          </Card>
        )}
      </main>
    </>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="text-muted-foreground">{label}</p>
      <p className="font-medium">{value || "—"}</p>
    </div>
  );
}
