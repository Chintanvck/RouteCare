"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { MapMarkerData } from "@/components/maps/map-view";
import { TravelTimeCalculator, type LocationOption } from "@/components/maps/travel-time-calculator";
import { apiFetch, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { PaginatedResponse, Patient } from "@/types/patient";
import type { Therapist } from "@/types/therapist";

// Leaflet touches `window` at import time - must never be part of the server-rendered bundle.
const MapView = dynamic(() => import("@/components/maps/map-view").then((mod) => mod.MapView), { ssr: false });

export default function MapPage() {
  const { checked } = useRequireAuth();

  const [patients, setPatients] = useState<Patient[]>([]);
  const [therapists, setTherapists] = useState<Therapist[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  useEffect(() => {
    if (!checked) return;
    let cancelled = false;

    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [patientResult, therapistResult] = await Promise.all([
          apiFetch<PaginatedResponse<Patient>>("/patients?is_active=true&page_size=100"),
          apiFetch<PaginatedResponse<Therapist>>("/therapists?is_active=true&page_size=100"),
        ]);
        if (!cancelled) {
          setPatients(patientResult.items);
          setTherapists(therapistResult.items);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load locations. Please try again.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [checked]);

  const geocodedPatients = useMemo(() => patients.filter((p) => p.latitude !== null && p.longitude !== null), [patients]);
  const geocodedTherapists = useMemo(
    () => therapists.filter((t) => t.home_latitude !== null && t.home_longitude !== null),
    [therapists]
  );
  const ungeocodedPatients = useMemo(() => patients.filter((p) => p.latitude === null || p.longitude === null), [patients]);

  const markers: MapMarkerData[] = useMemo(
    () => [
      ...geocodedPatients.map((p) => ({
        key: `patient:${p.id}`,
        type: "patient" as const,
        label: `${p.first_name} ${p.last_name}`,
        sublabel: `${p.address_line_1}, ${p.city}, ${p.state}`,
        latitude: p.latitude as number,
        longitude: p.longitude as number,
      })),
      ...geocodedTherapists.map((t) => ({
        key: `therapist:${t.id}`,
        type: "therapist" as const,
        label: `${t.first_name} ${t.last_name}`,
        sublabel: "Therapist start location",
        latitude: t.home_latitude as number,
        longitude: t.home_longitude as number,
      })),
    ],
    [geocodedPatients, geocodedTherapists]
  );

  const travelTimeOptions: LocationOption[] = useMemo(
    () => [
      ...geocodedPatients.map((p) => ({
        key: `patient:${p.id}`,
        label: `${p.first_name} ${p.last_name} (patient)`,
        ref: { patient_id: p.id },
      })),
      ...geocodedTherapists.map((t) => ({
        key: `therapist:${t.id}`,
        label: `${t.first_name} ${t.last_name} (therapist)`,
        ref: { therapist_id: t.id },
      })),
    ],
    [geocodedPatients, geocodedTherapists]
  );

  const selectedPatient = selectedKey?.startsWith("patient:")
    ? patients.find((p) => `patient:${p.id}` === selectedKey)
    : undefined;
  const selectedTherapist = selectedKey?.startsWith("therapist:")
    ? therapists.find((t) => `therapist:${t.id}` === selectedKey)
    : undefined;

  if (!checked) return null;

  return (
    <>
      <AppHeader />
      <main className="container space-y-6 py-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Map</h1>
          <p className="text-sm text-muted-foreground">Patient and therapist locations across your clinic.</p>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {loading ? (
          <Skeleton className="h-[500px] w-full" />
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_360px]">
            <div className="h-[500px] overflow-hidden rounded-lg border">
              <MapView markers={markers} selectedKey={selectedKey} onSelect={(m) => setSelectedKey(m.key)} />
            </div>

            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Selected location</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {selectedPatient ? (
                    <>
                      <p className="font-medium">
                        {selectedPatient.first_name} {selectedPatient.last_name}
                      </p>
                      <p className="text-muted-foreground">
                        {selectedPatient.address_line_1}, {selectedPatient.city}, {selectedPatient.state}{" "}
                        {selectedPatient.zip_code}
                      </p>
                      <p className="text-muted-foreground">
                        {selectedPatient.latitude?.toFixed(5)}, {selectedPatient.longitude?.toFixed(5)}
                      </p>
                      <Link href={`/patients/${selectedPatient.id}`} className="inline-block text-primary hover:underline">
                        View patient
                      </Link>
                    </>
                  ) : selectedTherapist ? (
                    <>
                      <p className="font-medium">
                        {selectedTherapist.first_name} {selectedTherapist.last_name}
                      </p>
                      <p className="text-muted-foreground">{selectedTherapist.home_address || "No address on file"}</p>
                      <p className="text-muted-foreground">
                        {selectedTherapist.home_latitude?.toFixed(5)}, {selectedTherapist.home_longitude?.toFixed(5)}
                      </p>
                      <Link href={`/therapists/${selectedTherapist.id}`} className="inline-block text-primary hover:underline">
                        View therapist
                      </Link>
                    </>
                  ) : (
                    <p className="text-muted-foreground">Click a marker to see its details here.</p>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Travel time</CardTitle>
                </CardHeader>
                <CardContent>
                  {travelTimeOptions.length < 2 ? (
                    <p className="text-sm text-muted-foreground">
                      Need at least two geocoded locations to calculate travel time.
                    </p>
                  ) : (
                    <TravelTimeCalculator options={travelTimeOptions} />
                  )}
                </CardContent>
              </Card>

              {ungeocodedPatients.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>Not yet located</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <p className="text-sm text-muted-foreground">
                      {ungeocodedPatients.length} patient{ungeocodedPatients.length === 1 ? "" : "s"} without map
                      coordinates.
                    </p>
                    <ul className="space-y-1 text-sm">
                      {ungeocodedPatients.slice(0, 8).map((p) => (
                        <li key={p.id} className="flex items-center justify-between gap-2">
                          <Link href={`/patients/${p.id}`} className="hover:underline">
                            {p.first_name} {p.last_name}
                          </Link>
                          <Badge variant={p.geocoding_status === "FAILED" ? "destructive" : "secondary"}>
                            {p.geocoding_status === "FAILED" ? "Failed" : "Pending"}
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}
      </main>
    </>
  );
}
