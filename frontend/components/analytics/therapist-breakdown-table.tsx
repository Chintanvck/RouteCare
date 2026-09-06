"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatHours, formatMinutes, formatMiles, formatPct } from "./format";
import type { TherapistAnalytics } from "@/types/analytics";

interface TherapistBreakdownTableProps {
  therapists: TherapistAnalytics[];
  selectedTherapistId: string | null;
  onSelect: (therapistId: string | null) => void;
  selectable: boolean;
}

/** Clinic admins/schedulers can click a row to drill into that therapist's efficiency/optimization
 * panels below; a THERAPIST caller only ever gets their own single row back from the API, so
 * `selectable` is false and this just renders as a read-only summary of "me." */
export function TherapistBreakdownTable({
  therapists,
  selectedTherapistId,
  onSelect,
  selectable,
}: TherapistBreakdownTableProps) {
  if (therapists.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Therapist breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No active therapists in this clinic yet.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Therapist breakdown</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Therapist</TableHead>
              <TableHead className="text-right">Appointments</TableHead>
              <TableHead className="text-right">Working hrs</TableHead>
              <TableHead className="text-right">Scheduled hrs</TableHead>
              <TableHead className="text-right">Utilization</TableHead>
              <TableHead className="text-right">Driving</TableHead>
              <TableHead className="text-right">Distance</TableHead>
              <TableHead className="text-right">Time saved</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {therapists.map((t) => (
              <TableRow
                key={t.therapist_id}
                onClick={() => selectable && onSelect(selectedTherapistId === t.therapist_id ? null : t.therapist_id)}
                className={selectable ? "cursor-pointer" : undefined}
                data-state={selectedTherapistId === t.therapist_id ? "selected" : undefined}
              >
                <TableCell className="font-medium">{t.therapist_name}</TableCell>
                <TableCell className="text-right tabular-nums">{t.appointments}</TableCell>
                <TableCell className="text-right tabular-nums">{formatHours(t.working_hours)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatHours(t.scheduled_hours)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatPct(t.utilization_pct)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatMinutes(t.drive_minutes)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatMiles(t.distance_miles)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatMinutes(t.estimated_time_saved_minutes)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {selectable && (
          <p className="pt-3 text-xs text-muted-foreground">
            {selectedTherapistId ? "Showing efficiency and optimization details for the selected therapist below." : "Click a row to see one therapist's efficiency and optimization details."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
