// Mirrors backend/app/schemas/import_job.py - keep in sync by hand.

export type ImportStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "COMPLETED_WITH_ERRORS" | "FAILED";

export type RowClassification = "VALID" | "INVALID" | "DUPLICATE_EXACT" | "DUPLICATE_PROBABLE";

export interface ImportUploadResponse {
  id: string;
  status: ImportStatus;
  file_name: string;
  detected_headers: string[];
  suggested_mapping: Record<string, string>;
  total_records: number;
}

export interface ImportJob {
  id: string;
  clinic_id: string;
  uploaded_by: string;
  file_name: string;
  source_system: string;
  status: ImportStatus;
  detected_headers: string[] | null;
  column_mapping: Record<string, string> | null;
  total_records: number | null;
  processed_records: number;
  valid_records: number | null;
  invalid_records: number | null;
  duplicate_records: number | null;
  new_records: number | null;
  successful_records: number | null;
  failed_records: number | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface ImportRowError {
  field: string | null;
  message: string;
}

export interface ImportRow {
  row_number: number;
  mapped_data: Record<string, unknown>;
  classification: RowClassification;
  errors: ImportRowError[] | null;
  duplicate_patient_id: string | null;
  duplicate_of_row_number: number | null;
  duplicate_confidence: number | null;
  imported: boolean;
}

export interface ImportRowErrorEntry {
  row_number: number;
  field_name: string | null;
  error_message: string;
  created_at: string;
}

// Every mapping target Patient actually supports - kept in sync with
// backend/app/services/column_mapping.py's ALL_TARGETS.
export const MAPPING_TARGETS: { value: string; label: string; required: boolean }[] = [
  { value: "full_name", label: "Full Name", required: false },
  { value: "first_name", label: "First Name", required: false },
  { value: "last_name", label: "Last Name", required: false },
  { value: "address_line_1", label: "Street Address", required: true },
  { value: "address_line_2", label: "Address Line 2", required: false },
  { value: "city", label: "City", required: true },
  { value: "state", label: "State", required: true },
  { value: "zip_code", label: "ZIP Code", required: true },
  { value: "phone", label: "Phone", required: false },
  { value: "email", label: "Email", required: false },
  { value: "external_patient_id", label: "Patient ID", required: false },
  { value: "visit_duration_minutes", label: "Visit Duration (minutes)", required: false },
  { value: "priority_level", label: "Priority Level", required: false },
  { value: "scheduling_notes", label: "Scheduling Notes", required: false },
];
