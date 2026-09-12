"use client";

import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { PaginatedResponse, Patient } from "@/types/patient";

const MIN_QUERY_LENGTH = 2;
const DEBOUNCE_MS = 300;
const RESULT_LIMIT = 8;

/** Matches Appointment.patient_address's format on the backend (see app/models/appointment.py) -
 * one line, line 2 only when present. */
function formatAddress(p: Patient): string {
  const line2 = p.address_line_2 ? ` ${p.address_line_2}` : "";
  return `${p.address_line_1}${line2}, ${p.city}, ${p.state} ${p.zip_code}`;
}

interface PatientComboboxProps {
  value: string;
  onChange: (patientId: string) => void;
  disabled?: boolean;
}

/**
 * Searchable patient picker for the New Appointment form - replaces a plain `<select>` that
 * preloaded every patient into the browser. Search runs server-side (GET /patients?search=...),
 * so it's the backend - not this component - that decides which patients a given caller is even
 * allowed to see: `for_scheduling=true` is passed unconditionally (a no-op for CLINIC_ADMIN/
 * OFFICE_SCHEDULER, who already see the whole clinic; for a THERAPIST it's what allows finding a
 * same-clinic patient they've never been scheduled with before - see
 * appointment_service.create_appointment for why that's now authorized). This component never
 * decides who's authorized for whom; it just displays whatever the backend returns.
 */
export function PatientCombobox({ value, onChange, disabled }: PatientComboboxProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(false);
  const [errored, setErrored] = useState(false);
  const [selected, setSelected] = useState<Patient | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleOutsideClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  useEffect(() => {
    if (!open) return;
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setResults([]);
      setLoading(false);
      setErrored(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setErrored(false);
    const timer = setTimeout(async () => {
      try {
        const params = new URLSearchParams({
          search: trimmed,
          for_scheduling: "true",
          page_size: String(RESULT_LIMIT),
        });
        const result = await apiFetch<PaginatedResponse<Patient>>(`/patients?${params.toString()}`);
        if (!cancelled) setResults(result.items);
      } catch {
        if (!cancelled) {
          setErrored(true);
          setResults([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, open]);

  function handleSelect(patient: Patient) {
    setSelected(patient);
    setQuery("");
    setOpen(false);
    onChange(patient.id);
  }

  function handleClear() {
    setSelected(null);
    setQuery("");
    onChange("");
  }

  const trimmedQuery = query.trim();
  const showPanel = open && !selected;

  return (
    <div ref={containerRef} className="relative">
      {selected ? (
        <button
          type="button"
          disabled={disabled}
          onClick={() => setOpen(true)}
          className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span>
            {selected.first_name} {selected.last_name}
          </span>
          <span
            role="button"
            aria-label="Clear selected patient"
            onClick={(e) => {
              e.stopPropagation();
              handleClear();
            }}
            className="text-muted-foreground hover:text-foreground"
          >
            &times;
          </span>
        </button>
      ) : (
        <Input
          placeholder="Search patients by name..."
          value={query}
          disabled={disabled}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          autoComplete="off"
        />
      )}

      {showPanel && (
        <div className="absolute z-50 mt-1 max-h-64 w-full overflow-y-auto rounded-md border bg-card text-card-foreground shadow-lg">
          {trimmedQuery.length < MIN_QUERY_LENGTH && (
            <p className="px-3 py-2.5 text-sm text-muted-foreground">
              Type at least {MIN_QUERY_LENGTH} characters to search.
            </p>
          )}
          {trimmedQuery.length >= MIN_QUERY_LENGTH && loading && (
            <p className="px-3 py-2.5 text-sm text-muted-foreground">Searching...</p>
          )}
          {trimmedQuery.length >= MIN_QUERY_LENGTH && !loading && errored && (
            <p className="px-3 py-2.5 text-sm text-destructive">Could not search patients. Please try again.</p>
          )}
          {trimmedQuery.length >= MIN_QUERY_LENGTH && !loading && !errored && results.length === 0 && (
            <p className="px-3 py-2.5 text-sm text-muted-foreground">No patients found.</p>
          )}
          {!loading && !errored && results.length > 0 && (
            <div className="divide-y">
              {results.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleSelect(p)}
                  className="block w-full px-3 py-2.5 text-left text-sm hover:bg-accent"
                >
                  <div className="font-medium">
                    {p.first_name} {p.last_name}
                  </div>
                  <div className="text-xs text-muted-foreground">{formatAddress(p)}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
