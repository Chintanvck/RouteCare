"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { RecommendationCard } from "@/components/optimization/recommendation-card";
import { WhatIfPanel } from "@/components/optimization/what-if-panel";
import { apiFetch, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { Appointment } from "@/types/appointment";
import type {
  AcceptRecommendationResponse,
  OptimizationMode,
  OptimizationRecommendation,
  OptimizationRequest,
  WhatIfRequestPayload,
} from "@/types/optimization";
import type { PaginatedResponse, Patient } from "@/types/patient";
import type { Therapist } from "@/types/therapist";

const SELECT_CLASS =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

const MODE_LABELS: Record<OptimizationMode, string> = {
  DAY_SCHEDULE_OPTIMIZATION: "Optimize a day",
  WEEK_SCHEDULE_OPTIMIZATION: "Optimize a week",
  NEW_PATIENT_PLACEMENT: "Place a new patient",
};

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function startOfWeek(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  return addDays(iso, diff);
}

export default function OptimizePage() {
  const { checked } = useRequireAuth();

  const [therapists, setTherapists] = useState<Therapist[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);

  const [mode, setMode] = useState<OptimizationMode>("DAY_SCHEDULE_OPTIMIZATION");
  const [therapistId, setTherapistId] = useState("");
  const [targetDate, setTargetDate] = useState(todayIso());
  const [patientId, setPatientId] = useState("");

  const [request, setRequest] = useState<OptimizationRequest | null>(null);
  const [recommendations, setRecommendations] = useState<OptimizationRecommendation[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);

  const [starting, setStarting] = useState(false);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [whatIfScenario, setWhatIfScenario] = useState<Partial<WhatIfRequestPayload> | null>(null);

  useEffect(() => {
    if (!checked) return;
    (async () => {
      try {
        const [therapistResult, patientResult] = await Promise.all([
          apiFetch<PaginatedResponse<Therapist>>("/therapists?is_active=true&page_size=100"),
          apiFetch<PaginatedResponse<Patient>>("/patients?is_active=true&page_size=100"),
        ]);
        setTherapists(therapistResult.items);
        setPatients(patientResult.items);
      } catch {
        setError("Could not load therapists or patients.");
      }
    })();
  }, [checked]);

  const appointmentsById = useMemo(() => {
    const map: Record<string, Appointment> = {};
    for (const a of appointments) map[a.id] = a;
    return map;
  }, [appointments]);

  const patientsById = useMemo(() => {
    const map: Record<string, Patient> = {};
    for (const p of patients) map[p.id] = p;
    return map;
  }, [patients]);

  const loadAppointmentsForRange = useCallback(
    async (forTherapistId: string, startDate: string, endDate: string) => {
      try {
        const result = await apiFetch<PaginatedResponse<Appointment>>(
          `/appointments?therapist_id=${forTherapistId}&start_date=${startDate}&end_date=${endDate}&page_size=100`
        );
        setAppointments(result.items);
      } catch {
        // Non-fatal - the recommendation cards fall back to "Unknown patient" without this.
      }
    },
    []
  );

  const loadRecommendations = useCallback(async (requestId: string) => {
    const recs = await apiFetch<OptimizationRecommendation[]>(`/optimization/requests/${requestId}/recommendations`);
    setRecommendations(recs);
  }, []);

  const pollRequest = useCallback(
    async (requestId: string) => {
      setPolling(true);
      try {
        for (;;) {
          const current = await apiFetch<OptimizationRequest>(`/optimization/requests/${requestId}`);
          setRequest(current);
          if (current.status === "COMPLETED" || current.status === "FAILED") {
            if (current.status === "COMPLETED") {
              await loadRecommendations(requestId);
              const rangeStart = current.target_date;
              const rangeEnd =
                current.mode === "WEEK_SCHEDULE_OPTIMIZATION"
                  ? addDays(startOfWeek(current.target_date), 6)
                  : current.target_date;
              if (current.mode !== "NEW_PATIENT_PLACEMENT") {
                await loadAppointmentsForRange(current.therapist_id, rangeStart, rangeEnd);
              }
            }
            break;
          }
          await new Promise((resolve) => setTimeout(resolve, 1200));
        }
      } finally {
        setPolling(false);
      }
    },
    [loadAppointmentsForRange, loadRecommendations]
  );

  async function handleStart() {
    if (!therapistId) {
      setError("Select a therapist first.");
      return;
    }
    if (mode === "NEW_PATIENT_PLACEMENT" && !patientId) {
      setError("Select a patient to place.");
      return;
    }
    setStarting(true);
    setError(null);
    setRequest(null);
    setRecommendations([]);
    setAppointments([]);
    try {
      const effectiveDate = mode === "WEEK_SCHEDULE_OPTIMIZATION" ? startOfWeek(targetDate) : targetDate;
      const created = await apiFetch<OptimizationRequest>("/optimization/requests", {
        method: "POST",
        body: JSON.stringify({
          mode,
          therapist_id: therapistId,
          target_date: effectiveDate,
          ...(mode === "NEW_PATIENT_PLACEMENT" ? { patient_id: patientId } : {}),
        }),
      });
      setRequest(created);
      await pollRequest(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start optimization.");
    } finally {
      setStarting(false);
    }
  }

  async function refreshRecommendations() {
    if (request) await loadRecommendations(request.id);
  }

  async function handleAccept(recommendationId: string) {
    if (!request) return;
    try {
      await apiFetch<AcceptRecommendationResponse>(
        `/optimization/requests/${request.id}/recommendations/${recommendationId}/accept`,
        { method: "POST" }
      );
      await refreshRecommendations();
      const rangeStart = request.target_date;
      const rangeEnd =
        request.mode === "WEEK_SCHEDULE_OPTIMIZATION" ? addDays(startOfWeek(request.target_date), 6) : request.target_date;
      if (request.mode !== "NEW_PATIENT_PLACEMENT") {
        await loadAppointmentsForRange(request.therapist_id, rangeStart, rangeEnd);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not accept this recommendation.");
    }
  }

  async function handleReject(recommendationId: string) {
    if (!request) return;
    try {
      await apiFetch(`/optimization/requests/${request.id}/recommendations/${recommendationId}/reject`, {
        method: "POST",
      });
      await refreshRecommendations();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reject this recommendation.");
    }
  }

  const recommendationsByDate = useMemo(() => {
    const groups = new Map<string, OptimizationRecommendation[]>();
    for (const rec of recommendations) {
      const list = groups.get(rec.target_date) ?? [];
      list.push(rec);
      groups.set(rec.target_date, list);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [recommendations]);

  if (!checked) return null;

  return (
    <>
      <AppHeader />
      <main className="container max-w-4xl space-y-6 py-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Optimize Schedule</h1>
          <p className="text-sm text-muted-foreground">
            AI-recommended schedule changes. Nothing is applied to the calendar until you accept a recommendation.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Run optimization</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              {(Object.keys(MODE_LABELS) as OptimizationMode[]).map((m) => (
                <Button
                  key={m}
                  type="button"
                  size="sm"
                  variant={mode === m ? "default" : "outline"}
                  onClick={() => setMode(m)}
                >
                  {MODE_LABELS[m]}
                </Button>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="opt-therapist">Therapist</Label>
                <select
                  id="opt-therapist"
                  className={SELECT_CLASS}
                  value={therapistId}
                  onChange={(e) => setTherapistId(e.target.value)}
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

              <div className="space-y-1.5">
                <Label htmlFor="opt-date">{mode === "WEEK_SCHEDULE_OPTIMIZATION" ? "Any day in the week" : "Date"}</Label>
                <Input id="opt-date" type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
              </div>

              {mode === "NEW_PATIENT_PLACEMENT" && (
                <div className="space-y-1.5">
                  <Label htmlFor="opt-patient">Patient</Label>
                  <select
                    id="opt-patient"
                    className={SELECT_CLASS}
                    value={patientId}
                    onChange={(e) => setPatientId(e.target.value)}
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
              )}
            </div>

            <Button type="button" onClick={handleStart} disabled={starting || polling}>
              {starting || polling ? "Working..." : "Start optimization"}
            </Button>
          </CardContent>
        </Card>

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {request && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Status:</span>
              <span className="font-medium">{request.status}</span>
              {(request.status === "PENDING" || request.status === "PROCESSING") && (
                <span className="text-muted-foreground">Calculating...</span>
              )}
            </div>
            {request.status === "FAILED" && request.error_message && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {request.error_message}
              </div>
            )}
          </div>
        )}

        {polling && recommendations.length === 0 && (
          <div className="space-y-2">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        )}

        {recommendationsByDate.length > 0 && (
          <div className="space-y-6">
            <h2 className="text-lg font-semibold tracking-tight">Recommendations</h2>
            {recommendationsByDate.map(([date, recs]) => (
              <div key={date} className="space-y-3">
                {mode === "WEEK_SCHEDULE_OPTIMIZATION" && (
                  <h3 className="text-sm font-semibold text-muted-foreground">{date}</h3>
                )}
                {recs.map((rec) => (
                  <RecommendationCard
                    key={rec.id}
                    recommendation={rec}
                    mode={mode}
                    appointmentsById={appointmentsById}
                    patientsById={patientsById}
                    onAccept={() => handleAccept(rec.id)}
                    onReject={() => handleReject(rec.id)}
                    onModify={(scenario) => setWhatIfScenario(scenario)}
                  />
                ))}
              </div>
            ))}
          </div>
        )}

        <div id="what-if">
          <WhatIfPanel
            key={JSON.stringify(whatIfScenario)}
            therapists={therapists}
            patients={patients}
            appointments={appointments}
            initialScenario={whatIfScenario ?? undefined}
            onApplied={() => {
              if (request && request.mode !== "NEW_PATIENT_PLACEMENT") {
                const rangeStart = request.target_date;
                const rangeEnd =
                  request.mode === "WEEK_SCHEDULE_OPTIMIZATION"
                    ? addDays(startOfWeek(request.target_date), 6)
                    : request.target_date;
                loadAppointmentsForRange(request.therapist_id, rangeStart, rangeEnd);
              }
            }}
          />
        </div>
      </main>
    </>
  );
}
