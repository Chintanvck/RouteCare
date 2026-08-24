// Mirrors backend/app/schemas/maps.py - keep in sync by hand.

import type { Patient } from "./patient";
import type { Therapist } from "./therapist";

export interface LocationRef {
  patient_id?: string;
  therapist_id?: string;
  latitude?: number;
  longitude?: number;
}

export interface ResolvedPoint {
  type: "patient" | "therapist" | "coordinates";
  id: string | null;
  label: string;
  latitude: number;
  longitude: number;
}

export interface TravelTimeResponse {
  reachable: boolean;
  distance_miles: number | null;
  duration_minutes: number | null;
  calculated_at: string | null;
  cached: boolean;
}

export interface MatrixCell {
  reachable: boolean;
  distance_miles: number | null;
  duration_minutes: number | null;
  cached: boolean;
}

export interface TravelTimeMatrixResponse {
  points: ResolvedPoint[];
  matrix: (MatrixCell | null)[][];
  calculated_at: string;
}

export interface PatientGeocodeResponse {
  success: boolean;
  normalized_address: string | null;
  patient: Patient;
}

export interface TherapistGeocodeResponse {
  success: boolean;
  normalized_address: string | null;
  therapist: Therapist;
}
