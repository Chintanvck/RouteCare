"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Appointment } from "@/types/appointment";
import type {
  DayScheduleRecommendationData,
  NewPatientRecommendationData,
  OptimizationMode,
  OptimizationRecommendation,
  WhatIfRequestPayload,
} from "@/types/optimization";
import type { Patient } from "@/types/patient";

interface RecommendationCardProps {
  recommendation: OptimizationRecommendation;
  mode: OptimizationMode;
  appointmentsById: Record<string, Appointment>;
  patientsById: Record<string, Patient>;
  onAccept: () => Promise<void>;
  onReject: () => Promise<void>;
  onModify: (scenario: Partial<WhatIfRequestPayload>) => void;
}

function isDaySchedule(mode: OptimizationMode): boolean {
  return mode === "DAY_SCHEDULE_OPTIMIZATION" || mode === "WEEK_SCHEDULE_OPTIMIZATION";
}

const STATUS_LABEL: Record<string, string> = {
  OPTIMAL: "Optimal",
  FEASIBLE: "Feasible",
  INFEASIBLE: "No feasible schedule",
  ERROR: "Could not run",
};

export function RecommendationCard({
  recommendation,
  mode,
  appointmentsById,
  patientsById,
  onAccept,
  onReject,
  onModify,
}: RecommendationCardProps) {
  const [busy, setBusy] = useState(false);

  const actionable = recommendation.solver_status !== "INFEASIBLE" && recommendation.solver_status !== "ERROR";
  const alreadyDecided = recommendation.accepted_at !== null;

  async function handleAccept() {
    setBusy(true);
    try {
      await onAccept();
    } finally {
      setBusy(false);
    }
  }

  async function handleReject() {
    setBusy(true);
    try {
      await onReject();
    } finally {
      setBusy(false);
    }
  }

  const changes = isDaySchedule(mode)
    ? (recommendation.recommendation_data as DayScheduleRecommendationData).appointments ?? []
    : [];
  const newPatientData = !isDaySchedule(mode) ? (recommendation.recommendation_data as NewPatientRecommendationData) : null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle className="text-base">
            {isDaySchedule(mode) ? recommendation.target_date : "Recommended slot"}
          </CardTitle>
          <p className="text-sm text-muted-foreground">{recommendation.explanation}</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Badge variant={actionable ? "default" : "secondary"}>{STATUS_LABEL[recommendation.solver_status]}</Badge>
          {recommendation.accepted_at && <Badge variant="secondary">Accepted</Badge>}
          {recommendation.rejected_at && !recommendation.accepted_at && <Badge variant="outline">Rejected</Badge>}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <Metric label="Efficiency" value={`${Math.round(recommendation.efficiency_score)}%`} />
          <Metric label="Driving" value={`${recommendation.total_drive_minutes} min`} />
          <Metric label="Distance" value={`${recommendation.total_distance_miles} mi`} />
          {recommendation.time_saved_minutes !== null && recommendation.time_saved_minutes !== undefined && (
            <Metric label="Time saved" value={`${recommendation.time_saved_minutes} min`} />
          )}
          {recommendation.marginal_drive_minutes !== null && recommendation.marginal_drive_minutes !== undefined && (
            <Metric label="Added driving" value={`${recommendation.marginal_drive_minutes} min`} />
          )}
        </div>

        {changes.length > 0 && (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Patient</th>
                  <th className="px-3 py-2">Current time</th>
                  <th className="px-3 py-2">Recommended time</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {changes.map((change) => {
                  const appt = appointmentsById[change.appointment_id];
                  return (
                    <tr key={change.appointment_id} className="border-t">
                      <td className="px-3 py-2">{appt?.patient_name ?? "Unknown patient"}</td>
                      <td className="px-3 py-2 text-muted-foreground">{appt?.start_time.slice(0, 5) ?? "—"}</td>
                      <td className="px-3 py-2 font-medium">{change.new_start_time.slice(0, 5)}</td>
                      <td className="px-3 py-2 text-right">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            onModify({
                              scenario_type: "MOVE",
                              appointment_id: change.appointment_id,
                              new_scheduled_date: change.new_scheduled_date,
                              new_start_time: change.new_start_time,
                            })
                          }
                        >
                          Modify
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {changes.length === 0 && isDaySchedule(mode) && actionable && (
          <p className="text-sm text-muted-foreground">No changes needed - this day is already efficient.</p>
        )}

        {newPatientData && (
          <div className="rounded-md border p-3 text-sm">
            <p>
              <span className="font-medium">{patientsById[newPatientData.patient_id]?.first_name ?? "Patient"}{" "}
              {patientsById[newPatientData.patient_id]?.last_name ?? ""}</span>{" "}
              on {newPatientData.scheduled_date} at {newPatientData.start_time.slice(0, 5)} (
              {newPatientData.duration_minutes} min)
            </p>
            <div className="mt-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() =>
                  onModify({
                    scenario_type: "ADD",
                    patient_id: newPatientData.patient_id,
                    therapist_id: newPatientData.therapist_id,
                    new_scheduled_date: newPatientData.scheduled_date,
                    new_start_time: newPatientData.start_time,
                    new_duration_minutes: newPatientData.duration_minutes,
                  })
                }
              >
                Modify
              </Button>
            </div>
          </div>
        )}

        {recommendation.reason_codes.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {recommendation.reason_codes.map((code) => (
              <Badge key={code} variant="outline" className="text-xs font-normal">
                {code.replaceAll("_", " ").toLowerCase()}
              </Badge>
            ))}
          </div>
        )}

        {actionable && !alreadyDecided && (
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={handleReject} disabled={busy}>
              Reject
            </Button>
            <Button type="button" size="sm" onClick={handleAccept} disabled={busy}>
              {busy ? "Working..." : "Accept"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-medium">{value}</p>
    </div>
  );
}
