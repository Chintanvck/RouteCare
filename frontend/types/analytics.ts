// Mirrors backend/app/schemas/analytics.py - keep in sync by hand.

export type AnalyticsPeriod = "today" | "this_week" | "last_week" | "this_month" | "custom";

export interface DateRange {
  period: AnalyticsPeriod;
  start_date: string;
  end_date: string;
}

export interface DayCount {
  date: string;
  count: number;
}

export interface DayMinutes {
  date: string;
  minutes: number;
}

export interface AnalyticsOverview {
  date_range: DateRange;
  total_appointments: number;
  completed_appointments: number;
  scheduled_appointments: number;
  cancelled_appointments: number;
  no_show_appointments: number;
  therapist_count: number;
  total_drive_minutes: number;
  total_distance_miles: number;
  average_utilization_pct: number | null;
  optimization_runs: number;
  recommendations_accepted: number;
  estimated_time_saved_minutes: number | null;
  estimated_miles_saved: number | null;
  appointments_by_day: DayCount[];
  drive_minutes_by_day: DayMinutes[];
}

export interface TherapistAnalytics {
  therapist_id: string;
  therapist_name: string;
  appointments: number;
  working_hours: number;
  scheduled_hours: number;
  utilization_pct: number | null;
  drive_minutes: number;
  distance_miles: number;
  estimated_time_saved_minutes: number | null;
  optimization_runs: number;
  recommendations_accepted: number;
}

export interface TherapistAnalyticsResponse {
  date_range: DateRange;
  therapists: TherapistAnalytics[];
}

export interface EfficiencyMetrics {
  date_range: DateRange;
  therapist_id: string | null;
  sample_size: number;
  has_sufficient_data: boolean;
  average_travel_minutes_between_appointments: number | null;
  average_gap_minutes: number | null;
  appointments_per_working_hour: number | null;
  schedule_occupied_pct: number | null;
  total_drive_minutes: number;
  total_distance_miles: number;
}

export interface OptimizationSavingsByDay {
  date: string;
  time_saved_minutes: number;
  miles_saved: number;
}

export interface AcceptedOptimizationExample {
  recommendation_id: string;
  therapist_id: string;
  therapist_name: string;
  target_date: string;
  mode: string;
  before_drive_minutes: number;
  after_drive_minutes: number;
  time_saved_minutes: number;
  miles_saved: number;
  accepted_at: string;
}

export interface OptimizationImpact {
  date_range: DateRange;
  therapist_id: string | null;
  recommendations_accepted: number;
  recommendations_with_savings: number;
  total_time_saved_minutes: number | null;
  total_miles_saved: number | null;
  percentage_improvement: number | null;
  savings_by_day: OptimizationSavingsByDay[];
  recent_examples: AcceptedOptimizationExample[];
}
