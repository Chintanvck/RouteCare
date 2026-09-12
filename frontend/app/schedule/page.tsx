"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { AppHeader } from "@/components/layout/app-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AppointmentCard } from "@/components/scheduling/appointment-card";
import { AppointmentForm, toApiPayload, valuesFromAppointment } from "@/components/scheduling/appointment-form";
import { apiFetch, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/lib/use-current-user";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { Appointment, AppointmentFormValues } from "@/types/appointment";
import type { PaginatedResponse, Patient } from "@/types/patient";
import type { Therapist } from "@/types/therapist";

const SELECT_CLASS =
  "flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const STATUS_BADGE_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  SCHEDULED: "default",
  COMPLETED: "secondary",
  CANCELLED: "outline",
  NO_SHOW: "destructive",
};

function toISODate(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return toISODate(d);
}

function startOfWeek(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return toISODate(d);
}

function formatHeading(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}

type ModalState =
  | { mode: "create"; initialValues: Partial<AppointmentFormValues> }
  | { mode: "edit"; appointment: Appointment };

export default function SchedulePage() {
  const { checked } = useRequireAuth();
  const { user: currentUser } = useCurrentUser(checked);
  const isTherapist = currentUser?.role === "THERAPIST";

  const [view, setView] = useState<"day" | "week">("day");
  const [selectedDate, setSelectedDate] = useState(() => toISODate(new Date()));
  const [therapistFilter, setTherapistFilter] = useState<string>("all");

  const [therapists, setTherapists] = useState<Therapist[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const [updatingStatusId, setUpdatingStatusId] = useState<string | null>(null);

  const rangeStart = view === "day" ? selectedDate : startOfWeek(selectedDate);
  const rangeEnd = view === "day" ? selectedDate : addDays(rangeStart, 6);

  // For a THERAPIST, GET /therapists already comes back restricted to just their own record (see
  // app.services.therapist_service.list_therapists' restrict_to_therapist_id) - so this is their
  // own id, available without a separate lookup.
  const ownTherapistId = isTherapist ? therapists[0]?.id : undefined;

  useEffect(() => {
    if (!checked) return;
    (async () => {
      try {
        // `for_scheduling=true` lets a THERAPIST pick any active clinic patient here, not just
        // ones they already have an appointment with - needed so they can create a first
        // appointment for a new patient (see backend/app/modules/patients/router.py). It's a
        // no-op for CLINIC_ADMIN/OFFICE_SCHEDULER, who already see every clinic patient, and it
        // only affects this page's own patient-picker state, not the general /patients page.
        const [therapistResult, patientResult] = await Promise.all([
          apiFetch<PaginatedResponse<Therapist>>("/therapists?is_active=true&page_size=100"),
          apiFetch<PaginatedResponse<Patient>>("/patients?is_active=true&page_size=100&for_scheduling=true"),
        ]);
        setTherapists(therapistResult.items);
        setPatients(patientResult.items);
      } catch {
        setError("Could not load therapists or patients.");
      }
    })();
  }, [checked]);

  useEffect(() => {
    if (view === "week" && therapistFilter === "all" && therapists.length > 0) {
      setTherapistFilter(therapists[0].id);
    }
  }, [view, therapistFilter, therapists]);

  const loadAppointments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        start_date: rangeStart,
        end_date: rangeEnd,
        page_size: "100",
      });
      if (therapistFilter !== "all") params.set("therapist_id", therapistFilter);
      const result = await apiFetch<PaginatedResponse<Appointment>>(`/appointments?${params.toString()}`);
      setAppointments(result.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load appointments. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [rangeStart, rangeEnd, therapistFilter]);

  useEffect(() => {
    if (checked) loadAppointments();
  }, [checked, loadAppointments]);

  const dayAppointments = useMemo(() => {
    const byDay = new Map<string, Appointment[]>();
    for (const appt of appointments) {
      const list = byDay.get(appt.scheduled_date) ?? [];
      list.push(appt);
      byDay.set(appt.scheduled_date, list);
    }
    for (const list of byDay.values()) {
      list.sort((a, b) => a.start_time.localeCompare(b.start_time));
    }
    return byDay;
  }, [appointments]);

  const groupedByTherapist = useMemo(() => {
    if (view !== "day" || therapistFilter !== "all" || isTherapist) return null;
    const groups = new Map<string, Appointment[]>();
    for (const appt of dayAppointments.get(selectedDate) ?? []) {
      const list = groups.get(appt.therapist_name) ?? [];
      list.push(appt);
      groups.set(appt.therapist_name, list);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [view, therapistFilter, isTherapist, dayAppointments, selectedDate]);

  function shiftDate(days: number) {
    setSelectedDate((prev) => addDays(prev, view === "day" ? days : days * 7));
  }

  async function handleCreate(values: AppointmentFormValues) {
    try {
      await apiFetch<Appointment>("/appointments", { method: "POST", body: JSON.stringify(toApiPayload(values)) });
      closeModal();
      await loadAppointments();
    } catch (err) {
      throw new Error(err instanceof ApiError ? err.message : "Could not create appointment.");
    }
  }

  async function handleUpdate(appointmentId: string, values: AppointmentFormValues) {
    try {
      await apiFetch<Appointment>(`/appointments/${appointmentId}`, {
        method: "PATCH",
        body: JSON.stringify(toApiPayload(values, isTherapist)),
      });
      closeModal();
      await loadAppointments();
    } catch (err) {
      throw new Error(err instanceof ApiError ? err.message : "Could not update appointment.");
    }
  }

  function closeModal() {
    setModal(null);
    setConfirmingCancel(false);
  }

  async function handleCancel(appointmentId: string) {
    setCancellingId(appointmentId);
    try {
      await apiFetch<void>(`/appointments/${appointmentId}`, { method: "DELETE" });
      closeModal();
      await loadAppointments();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not cancel appointment. Please try again.");
    } finally {
      setCancellingId(null);
    }
  }

  async function handleMarkStatus(appointmentId: string, status: "COMPLETED" | "NO_SHOW") {
    setUpdatingStatusId(appointmentId);
    try {
      await apiFetch<Appointment>(`/appointments/${appointmentId}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      closeModal();
      await loadAppointments();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update appointment status. Please try again.");
    } finally {
      setUpdatingStatusId(null);
    }
  }

  if (!checked) return null;

  return (
    <>
      <AppHeader />
      <main className="container space-y-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{isTherapist ? "My Schedule" : "Schedule"}</h1>
            <p className="text-sm text-muted-foreground">
              {isTherapist ? "View and reschedule your own appointments." : "View and manage appointments across your clinic."}
            </p>
          </div>
          {/* A THERAPIST can schedule appointments too, but only for themselves - the backend
              enforces that regardless of what's sent (see appointment_service.create_appointment),
              and the form never shows them a therapist picker to begin with (see
              hideTherapistSelect below), so there's nothing left for this button to gate on. */}
          <Button
            onClick={() =>
              setModal({
                mode: "create",
                initialValues: {
                  scheduled_date: selectedDate,
                  ...(isTherapist
                    ? ownTherapistId
                      ? { therapist_id: ownTherapistId }
                      : {}
                    : therapistFilter !== "all"
                      ? { therapist_id: therapistFilter }
                      : {}),
                },
              })
            }
          >
            + New Appointment
          </Button>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => shiftDate(-1)}>
              &larr; Prev
            </Button>
            <Button variant="outline" size="sm" onClick={() => setSelectedDate(toISODate(new Date()))}>
              Today
            </Button>
            <Button variant="outline" size="sm" onClick={() => shiftDate(1)}>
              Next &rarr;
            </Button>
            <span className="ml-2 text-sm font-medium">
              {view === "day" ? formatHeading(selectedDate) : `${formatHeading(rangeStart)} – ${formatHeading(rangeEnd)}`}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* A THERAPIST's own schedule is the only one the backend will ever return for them
                (see app.modules.scheduling.router's restrict_to_therapist_id) - a selector that
                only ever offers their own name is just noise, so it's hidden rather than shown
                with one option. Retained for CLINIC_ADMIN/OFFICE_SCHEDULER, who manage the whole
                clinic's schedule. */}
            {!isTherapist && (
              <select
                className={SELECT_CLASS}
                value={therapistFilter}
                onChange={(e) => setTherapistFilter(e.target.value)}
              >
                {view === "day" && <option value="all">All therapists</option>}
                {therapists.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.first_name} {t.last_name}
                  </option>
                ))}
              </select>
            )}
            <select className={SELECT_CLASS} value={view} onChange={(e) => setView(e.target.value as "day" | "week")}>
              <option value="day">Day</option>
              <option value="week">Week</option>
            </select>
          </div>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {loading && (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        )}

        {!loading && view === "day" && (
          <div className="space-y-6">
            {therapistFilter === "all" && !isTherapist ? (
              groupedByTherapist && groupedByTherapist.length > 0 ? (
                groupedByTherapist.map(([therapistName, appts]) => (
                  <div key={therapistName} className="space-y-2">
                    <h2 className="text-sm font-semibold text-muted-foreground">{therapistName}</h2>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {appts.map((appt) => (
                        <AppointmentCard key={appt.id} appointment={appt} onClick={() => setModal({ mode: "edit", appointment: appt })} />
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No appointments scheduled for this day.</p>
              )
            ) : (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {(dayAppointments.get(selectedDate) ?? []).length === 0 && (
                  <p className="text-sm text-muted-foreground">No appointments scheduled for this day.</p>
                )}
                {(dayAppointments.get(selectedDate) ?? []).map((appt) => (
                  <AppointmentCard key={appt.id} appointment={appt} onClick={() => setModal({ mode: "edit", appointment: appt })} />
                ))}
              </div>
            )}
          </div>
        )}

        {!loading && view === "week" && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-7">
            {Array.from({ length: 7 }).map((_, i) => {
              const date = addDays(rangeStart, i);
              const appts = dayAppointments.get(date) ?? [];
              return (
                <div key={date} className="space-y-2">
                  <h2 className="text-sm font-semibold">
                    {DAY_LABELS[i]} <span className="text-muted-foreground">{date.slice(5)}</span>
                  </h2>
                  <div className="space-y-2">
                    {appts.length === 0 && <p className="text-xs text-muted-foreground">No appointments.</p>}
                    {appts.map((appt) => (
                      <AppointmentCard key={appt.id} appointment={appt} onClick={() => setModal({ mode: "edit", appointment: appt })} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>

      <AlertDialog open={modal !== null} onOpenChange={(open) => !open && closeModal()}>
        <AlertDialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              {modal?.mode === "edit" ? "Edit appointment" : "New appointment"}
              {modal?.mode === "edit" && (
                <Badge variant={STATUS_BADGE_VARIANT[modal.appointment.status] ?? "default"}>
                  {modal.appointment.status}
                </Badge>
              )}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {modal?.mode === "edit"
                ? "Changes are validated against therapist availability and existing appointments before they're saved."
                : isTherapist
                  ? "Pick a patient and a time. Scheduling a new patient's first appointment adds them to your schedule."
                  : "Pick a patient, therapist, and time. We'll check for conflicts before saving."}
            </AlertDialogDescription>
          </AlertDialogHeader>

          {modal && !confirmingCancel && (
            <AppointmentForm
              patients={patients}
              therapists={therapists}
              initialValues={modal.mode === "edit" ? valuesFromAppointment(modal.appointment) : modal.initialValues}
              excludeAppointmentId={modal.mode === "edit" ? modal.appointment.id : undefined}
              submitLabel={modal.mode === "edit" ? "Save changes" : "Create appointment"}
              onSubmit={(values) => (modal.mode === "edit" ? handleUpdate(modal.appointment.id, values) : handleCreate(values))}
              onCancel={closeModal}
              mode={modal.mode}
              restrictToOwnSchedule={isTherapist && modal.mode === "edit"}
              hideTherapistSelect={isTherapist && modal.mode === "create"}
            />
          )}

          {/* Status only ever moves forward from SCHEDULED to one explicit outcome - once it's
              COMPLETED/NO_SHOW/CANCELLED there's nothing left to mark here, matching the backend's
              one-way state machine (appointment_service never transitions status on its own). */}
          {modal?.mode === "edit" && modal.appointment.status === "SCHEDULED" && !confirmingCancel && (
            <AlertDialogFooter className="flex-col gap-2 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={updatingStatusId === modal.appointment.id}
                  onClick={() => handleMarkStatus(modal.appointment.id, "COMPLETED")}
                >
                  Mark completed
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={updatingStatusId === modal.appointment.id}
                  onClick={() => handleMarkStatus(modal.appointment.id, "NO_SHOW")}
                >
                  Mark no-show
                </Button>
              </div>
              <Button type="button" variant="destructive" size="sm" onClick={() => setConfirmingCancel(true)}>
                Cancel appointment
              </Button>
            </AlertDialogFooter>
          )}

          {modal?.mode === "edit" && confirmingCancel && (
            <div className="space-y-4">
              <p className="text-sm">
                {modal.appointment.patient_name}&apos;s appointment on {modal.appointment.scheduled_date} at{" "}
                {modal.appointment.start_time.slice(0, 5)} will be marked as cancelled. This does not delete the record.
              </p>
              <AlertDialogFooter>
                <Button type="button" variant="outline" onClick={() => setConfirmingCancel(false)}>
                  Keep it
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  disabled={cancellingId === modal.appointment.id}
                  onClick={() => handleCancel(modal.appointment.id)}
                >
                  Cancel appointment
                </Button>
              </AlertDialogFooter>
            </div>
          )}
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
