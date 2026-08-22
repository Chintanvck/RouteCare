// Mirrors backend/app/schemas/patient.py - keep in sync by hand until
// an OpenAPI-generated client is worth the added build step.

export interface Patient {
  id: string;
  clinic_id: string;
  external_patient_id: string | null;
  first_name: string;
  last_name: string;
  phone: string | null;
  email: string | null;
  address_line_1: string;
  address_line_2: string | null;
  city: string;
  state: string;
  zip_code: string;
  latitude: number | null;
  longitude: number | null;
  visit_duration_minutes: number | null;
  priority_level: number | null;
  scheduling_notes: string | null;
  source_system: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface PatientFormValues {
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  address_line_1: string;
  address_line_2: string;
  city: string;
  state: string;
  zip_code: string;
  visit_duration_minutes: string;
  priority_level: string;
  scheduling_notes: string;
}

export type SortBy = "name" | "created_at" | "zip_code";
export type SortOrder = "asc" | "desc";
