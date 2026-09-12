"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PatientCombobox } from "@/components/scheduling/patient-combobox";
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

/**
 * `omitAssignment` (Phase 11 fix) - a THERAPIST caller may only change date/start_time/duration/
 * status on their own appointment (see appointment_service._THERAPIST_UPDATABLE_FIELDS); the
 * backend rejects the request the moment `patient_id`/`therapist_id` are present in the payload
 * *at all*, even set to their current, unchanged value - `AppointmentUpdate` uses PATCH semantics
 * (`exclude_unset=True`), so simply including a key is what counts as "trying to change it," not
 * whether the value actually differs. Without this, editing (rescheduling) your own appointment
 * as a therapist always 403'd, since this form always populated every field from
 * valuesFromAppointment(). Omitting the two assignment fields entirely for that one case is
 * simpler and more robust than trying to diff values.
 */
export function toApiPayload(values: AppointmentFormValues, omitAssignment = false): Record<string, unknown> {
  return {
    ...(omitAssignment ? {} : { patient_id: values.patient_id, therapist_id: values.therapist_id }),
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
  /** "create" gets a searchable patient combobox (see PatientCombobox) instead of a `<select>` -
   * a plain dropdown would mean preloading every clinic patient into the browser just to pick one,
   * which doesn't scale and (for a THERAPIST picking a not-yet-assigned patient) isn't even the
   * same authorized set as their existing patient list. "edit" keeps the original `<select>`,
   * populated from `patients` - reassigning an existing appointment's patient is a separate,
   * unchanged workflow from "New Appointment." */
  mode: "create" | "edit";
  /** True when a THERAPIST is editing their own appointment - they can only change date/time/
   * duration/status (see toApiPayload's docstring), so the patient/therapist pickers are shown as
   * plain text instead of editable selects, matching what will actually be submitted. */
  restrictToOwnSchedule?: boolean;
  /** True when a THERAPIST is creating a new appointment for themselves - unlike
   * `restrictToOwnSchedule`, they still pick a patient (from their own authorized list, already
   * filtered server-side), just never a therapist: `initialValues.therapist_id` is expected to
   * already be their own id, and the backend overrides it regardless (see
   * appointment_service.create_appointment), so there's nothing for a picker to do here. */
  hideTherapistSelect?: boolean;
}

export function AppointmentForm({
  initialValues,
  patients,
  therapists,
  submitLabel,
  onSubmit,
  onCancel,
  excludeAppointmentId,
  mode,
  restrictToOwnSchedule,
  hideTherapistSelect,
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

      {restrictToOwnSchedule ? (
        <div className="rounded-md border bg-muted/30 px-3 py-2 text-sm">
          <p>
            <span className="text-muted-foreground">Patient: </span>
            {patients.find((p) => p.id === values.patient_id)?.first_name ?? "—"}{" "}
            {patients.find((p) => p.id === values.patient_id)?.last_name ?? ""}
          </p>
          <p className="text-xs text-muted-foreground">
            Only the date, time, and duration can be changed here - ask an admin or scheduler to reassign this visit.
          </p>
        </div>
      ) : (
        <>
          <div className="space-y-1.5">
            <Label htmlFor="patient_id">Patient</Label>
            {mode === "create" ? (
              <PatientCombobox value={values.patient_id} onChange={(id) => update("patient_id", id)} />
            ) : (
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
            )}
          </div>

          {!hideTherapistSelect && (
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
          )}
        </>
      )}

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
