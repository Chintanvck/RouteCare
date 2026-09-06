"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartEmptyState, HorizontalBarList } from "./bar-chart";
import { formatMinutes, formatMiles, formatPct } from "./format";
import { StatTile } from "./stat-tile";
import type { EfficiencyMetrics, TherapistAnalytics } from "@/types/analytics";

interface EfficiencyPanelProps {
  efficiency: EfficiencyMetrics;
  therapists: TherapistAnalytics[];
  showTherapistComparisons: boolean;
}

/** `showTherapistComparisons` is false once a single therapist is selected (or for a THERAPIST
 * caller, who only ever gets one row back) - comparing one therapist against itself isn't a chart. */
export function EfficiencyPanel({ efficiency, therapists, showTherapistComparisons }: EfficiencyPanelProps) {
  if (!efficiency.has_sufficient_data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Schedule efficiency</CardTitle>
        </CardHeader>
        <CardContent>
          <ChartEmptyState message="Not enough scheduled days in this period to calculate efficiency metrics." />
        </CardContent>
      </Card>
    );
  }

  const driveByTherapist = therapists.filter((t) => t.appointments > 0).map((t) => ({ label: t.therapist_name, value: t.drive_minutes }));
  const utilizationByTherapist = therapists
    .filter((t) => t.utilization_pct !== null)
    .map((t) => ({ label: t.therapist_name, value: t.utilization_pct as number }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Schedule efficiency</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Avg. travel between visits" value={formatMinutes(efficiency.average_travel_minutes_between_appointments)} />
          <StatTile label="Avg. schedule gap" value={formatMinutes(efficiency.average_gap_minutes)} />
          <StatTile label="Visits / working hour" value={efficiency.appointments_per_working_hour?.toFixed(2) ?? "—"} />
          <StatTile label="Schedule occupied" value={formatPct(efficiency.schedule_occupied_pct)} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <StatTile label="Total driving time" value={formatMinutes(efficiency.total_drive_minutes)} />
          <StatTile label="Total driving distance" value={formatMiles(efficiency.total_distance_miles)} />
        </div>

        {showTherapistComparisons && (
          <div className="grid gap-6 sm:grid-cols-2">
            <div className="space-y-2">
              <p className="text-sm font-medium">Driving time by therapist</p>
              {driveByTherapist.length > 0 ? (
                <HorizontalBarList items={driveByTherapist} valueFormatter={(v) => formatMinutes(v)} />
              ) : (
                <ChartEmptyState message="No driving data for this period." />
              )}
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium">Utilization by therapist</p>
              {utilizationByTherapist.length > 0 ? (
                <HorizontalBarList items={utilizationByTherapist} valueFormatter={(v) => `${v.toFixed(0)}%`} />
              ) : (
                <ChartEmptyState message="No configured working hours to calculate utilization." />
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
