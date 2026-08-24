// Mirrors backend/app/schemas/appointment.py - keep in sync by hand.

export type AppointmentStatus = "SCHEDULED" | "COMPLETED" | "CANCELLED" | "NO_SHOW";

export interface Appointment {
  id: string;
  clinic_id: string;
  patient_id: string;
  therapist_id: string;
  scheduled_date: string; // "YYYY-MM-DD"
  start_time: string; // "HH:MM:SS"
  end_time: string;
  duration_minutes: number;
  status: AppointmentStatus;
  appointment_source: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  patient_name: string;
  therapist_name: string;
}

export interface AppointmentFormValues {
  patient_id: string;
  therapist_id: string;
  scheduled_date: string;
  start_time: string;
  duration_minutes: string;
}

export interface AppointmentValidateResponse {
  valid: boolean;
  errors: string[];
}
