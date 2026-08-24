"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Therapist, TherapistFormValues } from "@/types/therapist";

const PHONE_RE = /^\+?[0-9()\-.\s]{7,20}$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function emptyValues(): TherapistFormValues {
  return {
    first_name: "",
    last_name: "",
    email: "",
    password: "",
    license_type: "",
    phone: "",
    home_address: "",
    max_daily_hours: "",
    max_drive_time_minutes: "",
  };
}

export function valuesFromTherapist(therapist: Therapist): TherapistFormValues {
  return {
    first_name: therapist.first_name,
    last_name: therapist.last_name,
    email: therapist.email,
    password: "",
    license_type: therapist.license_type ?? "",
    phone: therapist.phone ?? "",
    home_address: therapist.home_address ?? "",
    max_daily_hours: therapist.max_daily_hours?.toString() ?? "",
    max_drive_time_minutes: therapist.max_drive_time_minutes?.toString() ?? "",
  };
}

function validate(values: TherapistFormValues, mode: "create" | "edit"): Partial<Record<keyof TherapistFormValues, string>> {
  const errors: Partial<Record<keyof TherapistFormValues, string>> = {};

  if (!values.first_name.trim()) errors.first_name = "First name is required.";
  if (!values.last_name.trim()) errors.last_name = "Last name is required.";

  if (!values.email.trim()) {
    errors.email = "Email is required.";
  } else if (!EMAIL_RE.test(values.email.trim())) {
    errors.email = "Enter a valid email address.";
  }

  if (mode === "create") {
    if (values.password.length < 12) {
      errors.password = "Password must be at least 12 characters, with upper/lowercase, a number, and a symbol.";
    }
  }

  if (values.phone.trim() && !PHONE_RE.test(values.phone.trim())) {
    errors.phone = "Phone number format is invalid.";
  }

  if (values.max_daily_hours.trim()) {
    const n = Number(values.max_daily_hours);
    if (!Number.isInteger(n) || n <= 0 || n > 24) errors.max_daily_hours = "Must be a whole number from 1 to 24.";
  }

  if (values.max_drive_time_minutes.trim()) {
    const n = Number(values.max_drive_time_minutes);
    if (!Number.isInteger(n) || n <= 0 || n > 600) errors.max_drive_time_minutes = "Must be a whole number from 1 to 600.";
  }

  return errors;
}

export function toApiPayload(values: TherapistFormValues, mode: "create" | "edit"): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    first_name: values.first_name.trim(),
    last_name: values.last_name.trim(),
    email: values.email.trim(),
    license_type: values.license_type.trim() || null,
    phone: values.phone.trim() || null,
    home_address: values.home_address.trim() || null,
    max_daily_hours: values.max_daily_hours.trim() ? Number(values.max_daily_hours) : null,
    max_drive_time_minutes: values.max_drive_time_minutes.trim() ? Number(values.max_drive_time_minutes) : null,
  };
  if (mode === "create") {
    payload.password = values.password;
  }
  return payload;
}

interface TherapistFormProps {
  mode: "create" | "edit";
  initialValues?: TherapistFormValues;
  submitLabel: string;
  onSubmit: (values: TherapistFormValues) => Promise<void>;
  onCancel: () => void;
}

export function TherapistForm({ mode, initialValues, submitLabel, onSubmit, onCancel }: TherapistFormProps) {
  const [values, setValues] = useState<TherapistFormValues>(initialValues ?? emptyValues());
  const [errors, setErrors] = useState<Partial<Record<keyof TherapistFormValues, string>>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function update<K extends keyof TherapistFormValues>(field: K, value: string) {
    setValues((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitError(null);

    const validationErrors = validate(values, mode);
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;

    setSubmitting(true);
    try {
      await onSubmit(values);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Could not save therapist. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      {submitError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {submitError}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="first_name">First name</Label>
          <Input
            id="first_name"
            value={values.first_name}
            onChange={(e) => update("first_name", e.target.value)}
            aria-invalid={!!errors.first_name}
          />
          {errors.first_name && <p className="text-sm text-destructive">{errors.first_name}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="last_name">Last name</Label>
          <Input
            id="last_name"
            value={values.last_name}
            onChange={(e) => update("last_name", e.target.value)}
            aria-invalid={!!errors.last_name}
          />
          {errors.last_name && <p className="text-sm text-destructive">{errors.last_name}</p>}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            value={values.email}
            onChange={(e) => update("email", e.target.value)}
            disabled={mode === "edit"}
            aria-invalid={!!errors.email}
          />
          {errors.email && <p className="text-sm text-destructive">{errors.email}</p>}
        </div>
        {mode === "create" && (
          <div className="space-y-1.5">
            <Label htmlFor="password">Temporary password</Label>
            <Input
              id="password"
              type="password"
              value={values.password}
              onChange={(e) => update("password", e.target.value)}
              aria-invalid={!!errors.password}
            />
            {errors.password && <p className="text-sm text-destructive">{errors.password}</p>}
          </div>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="license_type">License type</Label>
          <Input
            id="license_type"
            placeholder="PT, OT, PTA, ..."
            value={values.license_type}
            onChange={(e) => update("license_type", e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="phone">Phone</Label>
          <Input
            id="phone"
            value={values.phone}
            onChange={(e) => update("phone", e.target.value)}
            placeholder="(201) 555-0100"
            aria-invalid={!!errors.phone}
          />
          {errors.phone && <p className="text-sm text-destructive">{errors.phone}</p>}
        </div>

        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="home_address">Home address (optional)</Label>
          <Input id="home_address" value={values.home_address} onChange={(e) => update("home_address", e.target.value)} />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="max_daily_hours">Max daily hours (optional)</Label>
          <Input
            id="max_daily_hours"
            inputMode="numeric"
            value={values.max_daily_hours}
            onChange={(e) => update("max_daily_hours", e.target.value)}
            aria-invalid={!!errors.max_daily_hours}
          />
          {errors.max_daily_hours && <p className="text-sm text-destructive">{errors.max_daily_hours}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="max_drive_time_minutes">Max drive time, minutes (optional)</Label>
          <Input
            id="max_drive_time_minutes"
            inputMode="numeric"
            value={values.max_drive_time_minutes}
            onChange={(e) => update("max_drive_time_minutes", e.target.value)}
            aria-invalid={!!errors.max_drive_time_minutes}
          />
          {errors.max_drive_time_minutes && <p className="text-sm text-destructive">{errors.max_drive_time_minutes}</p>}
        </div>
      </div>

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
