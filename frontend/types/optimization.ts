// Mirrors backend/app/schemas/optimization.py - keep in sync by hand.

export type OptimizationMode = "DAY_SCHEDULE_OPTIMIZATION" | "NEW_PATIENT_PLACEMENT" | "WEEK_SCHEDULE_OPTIMIZATION";
export type OptimizationStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";

export interface OptimizationRequest {
  id: string;
  clinic_id: string;
  therapist_id: string;
  requested_by: string;
  mode: OptimizationMode;
  status: OptimizationStatus;
  target_date: string;
  search_days: number | null;
  new_patient_id: string | null;
  new_appointment_duration_minutes: number | null;
  error_message: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AppointmentChange {
  appointment_id: string;
  new_scheduled_date: string;
  new_start_time: string; // "HH:MM:SS"
}

export interface DayScheduleRecommendationData {
  appointments: AppointmentChange[];
}

export interface NewPatientRecommendationData {
  patient_id: string;
  therapist_id: string;
  scheduled_date: string;
  start_time: string;
  duration_minutes: number;
}

export interface OptimizationRecommendation {
  id: string;
  optimization_request_id: string;
  target_date: string;
  rank: number;
  efficiency_score: number;
  total_drive_minutes: number;
  total_distance_miles: number;
  time_saved_minutes: number | null;
  miles_saved: number | null;
  marginal_drive_minutes: number | null;
  marginal_distance_miles: number | null;
  reason_codes: string[];
  explanation: string;
  recommendation_data: DayScheduleRecommendationData | NewPatientRecommendationData | Record<string, never>;
  solver_status: "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "ERROR";
  accepted_at: string | null;
  rejected_at: string | null;
  created_at: string;
}

export interface AcceptRecommendationResponse {
  recommendation: OptimizationRecommendation;
  appointment_ids: string[];
}

export type WhatIfScenarioType = "MOVE" | "ADD" | "REMOVE";

export interface WhatIfRequestPayload {
  scenario_type: WhatIfScenarioType;
  appointment_id?: string;
  new_scheduled_date?: string;
  new_start_time?: string;
  new_duration_minutes?: number;
  patient_id?: string;
  therapist_id?: string;
}

export interface WhatIfDayImpact {
  target_date: string;
  current_drive_minutes: number;
  proposed_drive_minutes: number;
  current_distance_miles: number;
  proposed_distance_miles: number;
}

export interface WhatIfResponse {
  feasible: boolean;
  conflicts: string[];
  days: WhatIfDayImpact[];
  total_time_impact_minutes: number | null;
  total_distance_impact_miles: number | null;
  affected_appointment_ids: string[];
}

export interface WhatIfApplyResponse {
  applied: boolean;
  appointment_id: string | null;
  message: string;
}
