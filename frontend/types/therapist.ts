// Mirrors backend/app/schemas/therapist.py and availability.py - keep in sync by hand.

export interface Therapist {
  id: string;
  clinic_id: string;
  user_id: string;
  first_name: string;
  last_name: string;
  email: string;
  is_active: boolean;
  license_type: string | null;
  phone: string | null;
  home_address: string | null;
  home_latitude: number | null;
  home_longitude: number | null;
  max_daily_hours: number | null;
  max_drive_time_minutes: number | null;
  created_at: string;
  updated_at: string;
}

// 0=Monday ... 6=Sunday - matches Python's date.weekday(), see
// backend/app/models/therapist_availability.py.
export const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export interface TherapistAvailabilityRule {
  id: string;
  therapist_id: string;
  day_of_week: number;
  start_time: string; // "HH:MM:SS"
  end_time: string;
  is_available: boolean;
  created_at: string;
}

export interface TherapistFormValues {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  license_type: string;
  phone: string;
  home_address: string;
  max_daily_hours: string;
  max_drive_time_minutes: string;
}
