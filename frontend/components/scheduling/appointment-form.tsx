"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import type { Appointment, AppointmentFormValues, AppointmentValidateResponse } from "@/types/appointment";
import type { Patient } from "@/types/patient";
import type { Therapist } from "@/types/therapist";

const SELECT_CLASS =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

function emptyValues(defaults?: Partial<AppointmentFormValues>): AppointmentFormValues {
  return {
    patient_id: "",
    therapist_id: "",
    scheduled_date: "",
    start_time: "",
    duration_minutes: "45",
    ...defaults,
  };
}

export function valuesFromAppointment(appt: Appointment): AppointmentFormValues {
  return {
    patient_id: appt.patient_id,
    therapist_id: appt.therapist_id,
    scheduled_date: appt.scheduled_date,
    start_time: appt.start_time.slice(0, 5),
    duration_minutes: String(appt.duration_minutes),
  };
}

export function toApiPayload(values: AppointmentFormValues): Record<string, unknown> {
  return {
    patient_id: values.patient_id,
    therapist_id: values.therapist_id,
    scheduled_date: values.scheduled_date,
    start_time: `${values.start_time}:00`,
    duration_minutes: Number(values.duration_minutes),
  };
}

interface AppointmentFormProps {
  initialValues?: Partial<AppointmentFormValues>;
  patients: Patient[];
  therapists: Therapist[];
  submitLabel: string;
  onSubmit: (values: AppointmentFormValues) => Promise<void>;
  onCancel: () => void;
  excludeAppointmentId?: string;
}

export function AppointmentForm({
  initialValues,
  patients,
  therapists,
  submitLabel,
  onSubmit,
  onCancel,
  excludeAppointmentId,
}: AppointmentFormProps) {
  const [values, setValues] = useState<AppointmentFormValues>(emptyValues(initialValues));
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [checking, setChecking] = useState(false);
  const [conflicts, setConflicts] = useState<string[] | null>(null);

  function update<K extends keyof AppointmentFormValues>(field: K, value: string) {
    setValues((prev) => ({ ...prev, [field]: value }));
    setConflicts(null);
  }

  const canValidate = Boolean(
    values.patient_id && values.therapist_id && values.scheduled_date && values.start_time && values.duration_minutes
  );

  useEffect(() => {
    if (!canValidate) {
      setConflicts(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      setChecking(true);
      try {
        const result = await apiFetch<AppointmentValidateResponse>("/appointments/validate", {
          method: "POST",
          body: JSON.stringify({
            ...toApiPayload(values),
            exclude_appointment_id: excludeAppointmentId,
          }),
        });
        if (!cancelled) setConflicts(result.valid ? [] : result.errors);
      } catch {
        if (!cancelled) setConflicts(null);
      } finally {
        if (!cancelled) setChecking(false);
      }
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values.patient_id, values.therapist_id, values.scheduled_date, values.start_time, values.duration_minutes, canValidate]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      await onSubmit(values);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Could not save appointment.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {submitError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {submitError}
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="patient_id">Patient</Label>
        <select
          id="patient_id"
          className={SELECT_CLASS}
          value={values.patient_id}
          onChange={(e) => update("patient_id", e.target.value)}
          required
        >
          <option value="" disabled>
            Select a patient
          </option>
          {patients.map((p) => (
            <option key={p.id} value={p.id}>
              {p.first_name} {p.last_name}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="therapist_id">Therapist</Label>
        <select
          id="therapist_id"
          className={SELECT_CLASS}
          value={values.therapist_id}
          onChange={(e) => update("therapist_id", e.target.value)}
          required
        >
          <option value="" disabled>
            Select a therapist
          </option>
          {therapists.map((t) => (
            <option key={t.id} value={t.id}>
              {t.first_name} {t.last_name}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="scheduled_date">Date</Label>
          <Input
            id="scheduled_date"
            type="date"
            value={values.scheduled_date}
            onChange={(e) => update("scheduled_date", e.target.value)}
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="start_time">Start time</Label>
          <Input
            id="start_time"
            type="time"
            value={values.start_time}
            onChange={(e) => update("start_time", e.target.value)}
            required
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="duration_minutes">Duration (minutes)</Label>
        <Input
          id="duration_minutes"
          type="number"
          min={5}
          step={5}
          value={values.duration_minutes}
          onChange={(e) => update("duration_minutes", e.target.value)}
          required
        />
      </div>

      {checking && <p className="text-sm text-muted-foreground">Checking availability...</p>}
      {conflicts && conflicts.length > 0 && (
        <div className="rounded-md border border-amber-500/50 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-400">
          <p className="font-medium">This time won&apos;t work:</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {conflicts.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      {conflicts && conflicts.length === 0 && (
        <p className="text-sm text-emerald-700 dark:text-emerald-400">No conflicts — this time is available.</p>
      )}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving..." : submitLabel}
        </Button>
      </div>
    </form>
  );
}
