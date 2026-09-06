// Mirrors backend/app/schemas/auth.py's UserPublic - keep in sync by hand.

export type UserRole = "SYSTEM_ADMIN" | "CLINIC_ADMIN" | "OFFICE_SCHEDULER" | "THERAPIST";

export interface CurrentUser {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  role: UserRole;
  clinic_id: string | null;
  is_active: boolean;
}
