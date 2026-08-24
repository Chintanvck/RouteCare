"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { AppHeader } from "@/components/layout/app-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AvailabilityEditor } from "@/components/therapists/availability-editor";
import { TherapistForm, toApiPayload, valuesFromTherapist } from "@/components/therapists/therapist-form";
import { apiFetch, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { Appointment } from "@/types/appointment";
import type { PaginatedResponse } from "@/types/patient";
import type { Therapist, TherapistAvailabilityRule, TherapistFormValues } from "@/types/therapist";

export default function TherapistDetailPage() {
  const { checked } = useRequireAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();

  const [therapist, setTherapist] = useState<Therapist | null>(null);
  const [availability, setAvailability] = useState<TherapistAvailabilityRule[]>([]);
  const [upcoming, setUpcoming] = useState<Appointment[]>([]);
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
        const [therapistResult, availabilityResult, upcomingResult] = await Promise.all([
          apiFetch<Therapist>(`/therapists/${params.id}`),
          apiFetch<TherapistAvailabilityRule[]>(`/therapists/${params.id}/availability`),
          apiFetch<PaginatedResponse<Appointment>>(
            `/appointments?therapist_id=${params.id}&status=SCHEDULED&start_date=${today()}&page_size=5&sort=asc`
          ),
        ]);
        if (!cancelled) {
          setTherapist(therapistResult);
          setAvailability(availabilityResult);
          setUpcoming(upcomingResult.items);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError && err.status === 404
              ? "This therapist could not be found."
              : "Could not load this therapist. Please try again."
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

  async function handleUpdate(values: TherapistFormValues) {
    try {
      const updated = await apiFetch<Therapist>(`/therapists/${params.id}`, {
        method: "PATCH",
        body: JSON.stringify(toApiPayload(values, "edit")),
      });
      setTherapist(updated);
      setEditing(false);
    } catch (err) {
      throw new Error(err instanceof ApiError ? err.message : "Could not update therapist.");
    }
  }

  async function handleToggleActive() {
    if (!therapist) return;
    try {
      const updated = await apiFetch<Therapist>(`/therapists/${params.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !therapist.is_active }),
      });
      setTherapist(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update therapist status.");
    }
  }

  if (!checked) return null;

  return (
    <>
      <AppHeader />
      <main className="container max-w-3xl space-y-6 py-8">
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

        {!loading && !error && therapist && !editing && (
          <>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">
                  {therapist.first_name} {therapist.last_name}
                </h1>
                <Badge variant={therapist.is_active ? "default" : "secondary"} className="mt-1">
                  {therapist.is_active ? "Active" : "Inactive"}
                </Badge>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setEditing(true)}>
                  Edit
                </Button>
                <Button variant={therapist.is_active ? "destructive" : "default"} onClick={handleToggleActive}>
                  {therapist.is_active ? "Deactivate" : "Activate"}
                </Button>
              </div>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Basic information</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
                <Field label="Email" value={therapist.email} />
                <Field label="Phone" value={therapist.phone} />
                <Field label="License type" value={therapist.license_type} />
                <Field label="Home address" value={therapist.home_address} />
                <Field label="Max daily hours" value={therapist.max_daily_hours ? String(therapist.max_daily_hours) : null} />
                <Field
                  label="Max drive time"
                  value={therapist.max_drive_time_minutes ? `${therapist.max_drive_time_minutes} minutes` : null}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Schedule summary</CardTitle>
              </CardHeader>
              <CardContent>
                {upcoming.length === 0 && <p className="text-sm text-muted-foreground">No upcoming appointments.</p>}
                <ul className="space-y-2">
                  {upcoming.map((appt) => (
                    <li key={appt.id} className="flex justify-between text-sm">
                      <span>
                        {appt.scheduled_date} at {appt.start_time.slice(0, 5)} &middot; {appt.patient_name}
                      </span>
                      <span className="text-muted-foreground">{appt.duration_minutes} min</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            <AvailabilityEditor therapistId={therapist.id} initialRules={availability} />
          </>
        )}

        {!loading && !error && therapist && editing && (
          <Card>
            <CardHeader>
              <CardTitle>Edit therapist</CardTitle>
            </CardHeader>
            <CardContent>
              <TherapistForm
                mode="edit"
                initialValues={valuesFromTherapist(therapist)}
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

function today(): string {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="text-muted-foreground">{label}</p>
      <p className="font-medium">{value || "—"}</p>
    </div>
  );
}
