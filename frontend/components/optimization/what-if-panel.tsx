"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch, ApiError } from "@/lib/api";
import type { Appointment } from "@/types/appointment";
import type {
  WhatIfApplyResponse,
  WhatIfRequestPayload,
  WhatIfResponse,
  WhatIfScenarioType,
} from "@/types/optimization";
import type { Patient } from "@/types/patient";
import type { Therapist } from "@/types/therapist";

const SELECT_CLASS =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

interface WhatIfPanelProps {
  therapists: Therapist[];
  patients: Patient[];
  appointments: Appointment[];
  initialScenario?: Partial<WhatIfRequestPayload>;
  onApplied?: () => void;
}

function appointmentLabel(appt: Appointment): string {
  return `${appt.patient_name} — ${appt.scheduled_date} ${appt.start_time.slice(0, 5)}`;
}

export function WhatIfPanel({ therapists, patients, appointments, initialScenario, onApplied }: WhatIfPanelProps) {
  const [scenarioType, setScenarioType] = useState<WhatIfScenarioType>(initialScenario?.scenario_type ?? "MOVE");
  const [appointmentId, setAppointmentId] = useState(initialScenario?.appointment_id ?? "");
  const [patientId, setPatientId] = useState(initialScenario?.patient_id ?? "");
  const [therapistId, setTherapistId] = useState(initialScenario?.therapist_id ?? "");
  const [newDate, setNewDate] = useState(initialScenario?.new_scheduled_date ?? "");
  const [newTime, setNewTime] = useState(initialScenario?.new_start_time?.slice(0, 5) ?? "");
  const [newDuration, setNewDuration] = useState(
    initialScenario?.new_duration_minutes ? String(initialScenario.new_duration_minutes) : ""
  );

  const [result, setResult] = useState<WhatIfResponse | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [evaluateError, setEvaluateError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [applyResult, setApplyResult] = useState<WhatIfApplyResponse | null>(null);

  useEffect(() => {
    setResult(null);
    setApplyResult(null);
  }, [scenarioType, appointmentId, patientId, therapistId, newDate, newTime, newDuration]);

  function buildPayload(): WhatIfRequestPayload | null {
    if (scenarioType === "REMOVE") {
      if (!appointmentId) return null;
      return { scenario_type: "REMOVE", appointment_id: appointmentId };
    }
    if (scenarioType === "MOVE") {
      if (!appointmentId || !newDate || !newTime) return null;
      return {
        scenario_type: "MOVE",
        appointment_id: appointmentId,
        new_scheduled_date: newDate,
        new_start_time: `${newTime}:00`,
        ...(newDuration ? { new_duration_minutes: Number(newDuration) } : {}),
      };
    }
    // ADD
    if (!patientId || !therapistId || !newDate || !newTime || !newDuration) return null;
    return {
      scenario_type: "ADD",
      patient_id: patientId,
      therapist_id: therapistId,
      new_scheduled_date: newDate,
      new_start_time: `${newTime}:00`,
      new_duration_minutes: Number(newDuration),
    };
  }

  const payload = buildPayload();

  async function handleEvaluate() {
    if (!payload) return;
    setEvaluating(true);
    setEvaluateError(null);
    setApplyResult(null);
    try {
      const response = await apiFetch<WhatIfResponse>("/optimization/what-if", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setResult(response);
    } catch (err) {
      setEvaluateError(err instanceof ApiError ? err.message : "Could not evaluate this scenario.");
    } finally {
      setEvaluating(false);
    }
  }

  async function handleApply() {
    if (!payload) return;
    setApplying(true);
    try {
      const response = await apiFetch<WhatIfApplyResponse>("/optimization/what-if/apply", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setApplyResult(response);
      if (response.applied) {
        onApplied?.();
      }
    } catch (err) {
      setApplyResult({
        applied: false,
        appointment_id: null,
        message: err instanceof ApiError ? err.message : "Could not apply this scenario.",
      });
    } finally {
      setApplying(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>What-If</CardTitle>
        <CardDescription>
          Test a hypothetical schedule change. Nothing on the real calendar changes until you explicitly apply it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          {(["MOVE", "ADD", "REMOVE"] as WhatIfScenarioType[]).map((type) => (
            <Button
              key={type}
              type="button"
              size="sm"
              variant={scenarioType === type ? "default" : "outline"}
              onClick={() => setScenarioType(type)}
            >
              {type === "MOVE" ? "Move appointment" : type === "ADD" ? "Add patient" : "Remove appointment"}
            </Button>
          ))}
        </div>

        {(scenarioType === "MOVE" || scenarioType === "REMOVE") && (
          <div className="space-y-1.5">
            <Label htmlFor="wi-appointment">Appointment</Label>
            <select
              id="wi-appointment"
              className={SELECT_CLASS}
              value={appointmentId}
              onChange={(e) => setAppointmentId(e.target.value)}
            >
              <option value="" disabled>
                Select an appointment
              </option>
              {appointments.map((a) => (
                <option key={a.id} value={a.id}>
                  {appointmentLabel(a)}
                </option>
              ))}
            </select>
          </div>
        )}

        {scenarioType === "ADD" && (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="wi-patient">Patient</Label>
              <select id="wi-patient" className={SELECT_CLASS} value={patientId} onChange={(e) => setPatientId(e.target.value)}>
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
              <Label htmlFor="wi-therapist">Therapist</Label>
              <select
                id="wi-therapist"
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
          </>
        )}

        {(scenarioType === "MOVE" || scenarioType === "ADD") && (
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="wi-date">New date</Label>
              <Input id="wi-date" type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wi-time">New start time</Label>
              <Input id="wi-time" type="time" value={newTime} onChange={(e) => setNewTime(e.target.value)} />
            </div>
          </div>
        )}

        {(scenarioType === "MOVE" || scenarioType === "ADD") && (
          <div className="space-y-1.5">
            <Label htmlFor="wi-duration">
              Duration (minutes){scenarioType === "MOVE" ? " — leave blank to keep current" : ""}
            </Label>
            <Input
              id="wi-duration"
              type="number"
              min={5}
              step={5}
              value={newDuration}
              onChange={(e) => setNewDuration(e.target.value)}
            />
          </div>
        )}

        <Button type="button" onClick={handleEvaluate} disabled={!payload || evaluating}>
          {evaluating ? "Evaluating..." : "Evaluate scenario"}
        </Button>

        {evaluateError && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {evaluateError}
          </div>
        )}

        {result && (
          <div className="space-y-3 rounded-md border p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Hypothetical result — nothing has been changed
              </span>
              <span
                className={
                  result.feasible
                    ? "rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-400"
                    : "rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive"
                }
              >
                {result.feasible ? "Feasible" : "Not feasible"}
              </span>
            </div>

            {!result.feasible && (
              <ul className="list-disc space-y-0.5 pl-5 text-sm text-destructive">
                {result.conflicts.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            )}

            {result.feasible && result.days.length > 0 && (
              <div className="space-y-2 text-sm">
                {result.days.map((day) => (
                  <div key={day.target_date} className="flex items-center justify-between">
                    <span className="text-muted-foreground">{day.target_date}</span>
                    <span>
                      {day.current_drive_minutes} min → {day.proposed_drive_minutes} min driving (
                      {day.current_distance_miles} → {day.proposed_distance_miles} mi)
                    </span>
                  </div>
                ))}
                {result.total_time_impact_minutes !== null && (
                  <p className="font-medium">
                    Net change: {result.total_time_impact_minutes >= 0 ? "+" : ""}
                    {result.total_time_impact_minutes} min driving,{" "}
                    {result.total_distance_impact_miles !== null && result.total_distance_impact_miles >= 0 ? "+" : ""}
                    {result.total_distance_impact_miles} mi
                  </p>
                )}
              </div>
            )}

            {result.feasible && (
              <Button type="button" onClick={handleApply} disabled={applying}>
                {applying ? "Applying..." : "Apply this change"}
              </Button>
            )}
          </div>
        )}

        {applyResult && (
          <div
            className={
              applyResult.applied
                ? "rounded-md border border-primary/30 bg-primary/5 px-4 py-3 text-sm"
                : "rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive"
            }
          >
            {applyResult.message}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
