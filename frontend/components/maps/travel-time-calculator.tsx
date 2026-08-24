"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { apiFetch, ApiError } from "@/lib/api";
import type { LocationRef, TravelTimeResponse } from "@/types/maps";

const SELECT_CLASS =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

export interface LocationOption {
  key: string;
  label: string;
  ref: LocationRef;
}

export function TravelTimeCalculator({ options }: { options: LocationOption[] }) {
  const [originKey, setOriginKey] = useState("");
  const [destinationKey, setDestinationKey] = useState("");
  const [result, setResult] = useState<TravelTimeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCalculate() {
    const origin = options.find((o) => o.key === originKey);
    const destination = options.find((o) => o.key === destinationKey);
    if (!origin || !destination) return;

    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await apiFetch<TravelTimeResponse>("/maps/travel-time", {
        method: "POST",
        body: JSON.stringify({ origin: origin.ref, destination: destination.ref }),
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not calculate travel time. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="travel-origin">From</Label>
        <select id="travel-origin" className={SELECT_CLASS} value={originKey} onChange={(e) => setOriginKey(e.target.value)}>
          <option value="">Select a location</option>
          {options.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="travel-destination">To</Label>
        <select
          id="travel-destination"
          className={SELECT_CLASS}
          value={destinationKey}
          onChange={(e) => setDestinationKey(e.target.value)}
        >
          <option value="">Select a location</option>
          {options.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <Button
        type="button"
        size="sm"
        onClick={handleCalculate}
        disabled={!originKey || !destinationKey || originKey === destinationKey || loading}
      >
        {loading ? "Calculating..." : "Calculate travel time"}
      </Button>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {result &&
        (result.reachable ? (
          <div className="rounded-md border bg-muted/40 p-3 text-sm">
            <p>
              <span className="font-medium">Distance:</span> {result.distance_miles} miles
            </p>
            <p>
              <span className="font-medium">Driving time:</span> {Math.round(result.duration_minutes ?? 0)} minutes
            </p>
            {result.cached && <p className="mt-1 text-xs text-muted-foreground">(cached result)</p>}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No driving route could be found between these two locations.</p>
        ))}
    </div>
  );
}
