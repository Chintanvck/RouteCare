"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { GeocodingStatus } from "@/types/patient";

const STATUS_LABEL: Record<GeocodingStatus, string> = {
  PENDING: "Not geocoded yet",
  GEOCODED: "Geocoded",
  FAILED: "Geocoding failed",
  MANUAL: "Manually set",
};

const STATUS_VARIANT: Record<GeocodingStatus, "default" | "secondary" | "destructive" | "outline"> = {
  PENDING: "secondary",
  GEOCODED: "default",
  FAILED: "destructive",
  MANUAL: "outline",
};

interface LocationCardProps {
  latitude: number | null;
  longitude: number | null;
  geocodingStatus: GeocodingStatus;
  geocodedAt: string | null;
  locationVerified: boolean;
  onGeocode: () => Promise<{ success: boolean; normalizedAddress: string | null }>;
}

export function LocationCard({ latitude, longitude, geocodingStatus, geocodedAt, locationVerified, onGeocode }: LocationCardProps) {
  const [geocoding, setGeocoding] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleGeocode() {
    setGeocoding(true);
    setError(null);
    setMessage(null);
    try {
      const result = await onGeocode();
      if (result.success) {
        setMessage(result.normalizedAddress ? `Found: ${result.normalizedAddress}` : "Location updated.");
      } else {
        setError("This address could not be located. Please check it for typos or missing details (e.g. a ZIP code).");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not geocode this address. Please try again.");
    } finally {
      setGeocoding(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Location</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={STATUS_VARIANT[geocodingStatus]}>{STATUS_LABEL[geocodingStatus]}</Badge>
          {locationVerified && <Badge variant="outline">Verified</Badge>}
        </div>

        {latitude !== null && longitude !== null ? (
          <p className="text-muted-foreground">
            {latitude.toFixed(5)}, {longitude.toFixed(5)}
            {geocodedAt && <> &middot; geocoded {new Date(geocodedAt).toLocaleDateString()}</>}
          </p>
        ) : (
          <p className="text-muted-foreground">No coordinates on file yet.</p>
        )}

        {error && <p className="text-destructive">{error}</p>}
        {message && <p className="text-emerald-700 dark:text-emerald-400">{message}</p>}

        <Button type="button" variant="outline" size="sm" onClick={handleGeocode} disabled={geocoding}>
          {geocoding ? "Locating..." : geocodingStatus === "GEOCODED" || geocodingStatus === "MANUAL" ? "Re-geocode" : "Geocode now"}
        </Button>
      </CardContent>
    </Card>
  );
}
