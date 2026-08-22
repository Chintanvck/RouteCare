"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { Patient, PatientFormValues } from "@/types/patient";

const US_STATE_RE = /^[A-Za-z]{2}$/;
const ZIP_RE = /^\d{5}(-\d{4})?$/;
const PHONE_RE = /^\+?[0-9()\-.\s]{7,20}$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function emptyValues(): PatientFormValues {
  return {
    first_name: "",
    last_name: "",
    phone: "",
    email: "",
    address_line_1: "",
    address_line_2: "",
    city: "",
    state: "",
    zip_code: "",
    visit_duration_minutes: "",
    priority_level: "",
    scheduling_notes: "",
  };
}

export function valuesFromPatient(patient: Patient): PatientFormValues {
  return {
    first_name: patient.first_name,
    last_name: patient.last_name,
    phone: patient.phone ?? "",
    email: patient.email ?? "",
    address_line_1: patient.address_line_1,
    address_line_2: patient.address_line_2 ?? "",
    city: patient.city,
    state: patient.state,
    zip_code: patient.zip_code,
    visit_duration_minutes: patient.visit_duration_minutes?.toString() ?? "",
    priority_level: patient.priority_level?.toString() ?? "",
    scheduling_notes: patient.scheduling_notes ?? "",
  };
}

function validate(values: PatientFormValues): Partial<Record<keyof PatientFormValues, string>> {
  const errors: Partial<Record<keyof PatientFormValues, string>> = {};

  if (!values.first_name.trim()) errors.first_name = "First name is required.";
  if (!values.last_name.trim()) errors.last_name = "Last name is required.";
  if (!values.address_line_1.trim()) errors.address_line_1 = "Street address is required.";
  if (!values.city.trim()) errors.city = "City is required.";

  if (!values.state.trim()) {
    errors.state = "State is required.";
  } else if (!US_STATE_RE.test(values.state.trim())) {
    errors.state = "Use a 2-letter state abbreviation (e.g. NJ).";
  }

  if (!values.zip_code.trim()) {
    errors.zip_code = "ZIP code is required.";
  } else if (!ZIP_RE.test(values.zip_code.trim())) {
    errors.zip_code = "ZIP code must look like 12345 or 12345-6789.";
  }

  if (values.phone.trim() && !PHONE_RE.test(values.phone.trim())) {
    errors.phone = "Phone number format is invalid.";
  }

  if (values.email.trim() && !EMAIL_RE.test(values.email.trim())) {
    errors.email = "Enter a valid email address.";
  }

  if (values.visit_duration_minutes.trim()) {
    const n = Number(values.visit_duration_minutes);
    if (!Number.isInteger(n) || n <= 0 || n > 480) {
      errors.visit_duration_minutes = "Visit duration must be between 1 and 480 minutes.";
    }
  }

  if (values.priority_level.trim()) {
    const n = Number(values.priority_level);
    if (!Number.isInteger(n) || n < 1 || n > 5) {
      errors.priority_level = "Priority must be a whole number from 1 to 5.";
    }
  }

  return errors;
}

export function toApiPayload(values: PatientFormValues): Record<string, unknown> {
  return {
    first_name: values.first_name.trim(),
    last_name: values.last_name.trim(),
    phone: values.phone.trim() || null,
    email: values.email.trim() || null,
    address_line_1: values.address_line_1.trim(),
    address_line_2: values.address_line_2.trim() || null,
    city: values.city.trim(),
    state: values.state.trim().toUpperCase(),
    zip_code: values.zip_code.trim(),
    visit_duration_minutes: values.visit_duration_minutes.trim() ? Number(values.visit_duration_minutes) : null,
    priority_level: values.priority_level.trim() ? Number(values.priority_level) : null,
    scheduling_notes: values.scheduling_notes.trim() || null,
  };
}

interface PatientFormProps {
  initialValues?: PatientFormValues;
  submitLabel: string;
  onSubmit: (values: PatientFormValues) => Promise<void>;
  onCancel: () => void;
}

export function PatientForm({ initialValues, submitLabel, onSubmit, onCancel }: PatientFormProps) {
  const [values, setValues] = useState<PatientFormValues>(initialValues ?? emptyValues());
  const [errors, setErrors] = useState<Partial<Record<keyof PatientFormValues, string>>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function update<K extends keyof PatientFormValues>(field: K, value: string) {
    setValues((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitError(null);

    const validationErrors = validate(values);
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;

    setSubmitting(true);
    try {
      await onSubmit(values);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Could not save patient. Please try again.");
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
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            value={values.email}
            onChange={(e) => update("email", e.target.value)}
            aria-invalid={!!errors.email}
          />
          {errors.email && <p className="text-sm text-destructive">{errors.email}</p>}
        </div>
      </div>

      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="address_line_1">Street address</Label>
          <Input
            id="address_line_1"
            value={values.address_line_1}
            onChange={(e) => update("address_line_1", e.target.value)}
            aria-invalid={!!errors.address_line_1}
          />
          {errors.address_line_1 && <p className="text-sm text-destructive">{errors.address_line_1}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="address_line_2">Apartment, suite, etc. (optional)</Label>
          <Input
            id="address_line_2"
            value={values.address_line_2}
            onChange={(e) => update("address_line_2", e.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="city">City</Label>
            <Input
              id="city"
              value={values.city}
              onChange={(e) => update("city", e.target.value)}
              aria-invalid={!!errors.city}
            />
            {errors.city && <p className="text-sm text-destructive">{errors.city}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="state">State</Label>
            <Input
              id="state"
              value={values.state}
              onChange={(e) => update("state", e.target.value)}
              maxLength={2}
              placeholder="NJ"
              aria-invalid={!!errors.state}
            />
            {errors.state && <p className="text-sm text-destructive">{errors.state}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="zip_code">ZIP code</Label>
            <Input
              id="zip_code"
              value={values.zip_code}
              onChange={(e) => update("zip_code", e.target.value)}
              placeholder="07030"
              aria-invalid={!!errors.zip_code}
            />
            {errors.zip_code && <p className="text-sm text-destructive">{errors.zip_code}</p>}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="visit_duration_minutes">Visit duration (minutes)</Label>
          <Input
            id="visit_duration_minutes"
            inputMode="numeric"
            value={values.visit_duration_minutes}
            onChange={(e) => update("visit_duration_minutes", e.target.value)}
            aria-invalid={!!errors.visit_duration_minutes}
          />
          {errors.visit_duration_minutes && (
            <p className="text-sm text-destructive">{errors.visit_duration_minutes}</p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="priority_level">Priority (1-5, optional)</Label>
          <Input
            id="priority_level"
            inputMode="numeric"
            value={values.priority_level}
            onChange={(e) => update("priority_level", e.target.value)}
            aria-invalid={!!errors.priority_level}
          />
          {errors.priority_level && <p className="text-sm text-destructive">{errors.priority_level}</p>}
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="scheduling_notes">Scheduling notes (optional)</Label>
        <Textarea
          id="scheduling_notes"
          value={values.scheduling_notes}
          onChange={(e) => update("scheduling_notes", e.target.value)}
          rows={3}
        />
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
