"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { AppointmentCard } from "@/components/scheduling/appointment-card";
import { StatTile } from "@/components/analytics/stat-tile";
import { formatMiles, formatMinutes } from "@/components/analytics/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import type { AnalyticsOverview } from "@/types/analytics";
import type { Appointment } from "@/types/appointment";
import type { TravelTimeMatrixResponse } from "@/types/maps";
import type { PaginatedResponse } from "@/types/patient";
import type { Therapist } from "@/types/therapist";

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const UPCOMING_LIMIT = 5;

/**
 * The therapist-facing dashboard content (Phase 11) - deliberately not a second `/dashboard`
 * route: `app/dashboard/page.tsx` renders this instead of the clinic-wide analytics view when the
 * logged-in user is a THERAPIST, so there's exactly one dashboard *page* with role-aware content,
 * per the task's "do not duplicate dashboard implementations unnecessarily."
 *
 * Every request here already comes back scoped to "me" server-side (see
 * app.modules.appointments/analytics/maps routers' restrict_to_therapist_id) - this component
 * never filters anything client-side for security, only for presentation (e.g. picking the next
 * few upcoming appointments out of a week-long fetch).
 */
export function TherapistTodayPanel() {
  const [today, setToday] = useState<Appointment[]>([]);
  const [upcoming, setUpcoming] = useState<Appointment[]>([]);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [legMinutes, setLegMinutes] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        // "Today" must come from the backend (clinic-timezone-aware, see
        // analytics_service.resolve_date_range) rather than the browser's local clock - a
        // therapist's device clock/timezone can drift from the clinic's, and computing "today"
        // client-side made this panel's own schedule fetch disagree with its own stat tiles.
        const overviewResult = await apiFetch<AnalyticsOverview>("/analytics/overview?period=today");
        const todayDate = overviewResult.date_range.start_date;
        const weekEnd = addDays(todayDate, 6);

        const [todayResult, weekResult, therapistResult] = await Promise.all([
          apiFetch<PaginatedResponse<Appointment>>(
            `/appointments?start_date=${todayDate}&end_date=${todayDate}&page_size=100`
          ),
          apiFetch<PaginatedResponse<Appointment>>(
            `/appointments?start_date=${addDays(todayDate, 1)}&end_date=${weekEnd}&status=SCHEDULED&page_size=100`
          ),
          apiFetch<PaginatedResponse<Therapist>>("/therapists?page_size=1"),
        ]);

        const todaySorted = [...todayResult.items].sort((a, b) => a.start_time.localeCompare(b.start_time));
        setToday(todaySorted);
        setUpcoming(
          [...weekResult.items].sort((a, b) => (a.scheduled_date + a.start_time).localeCompare(b.scheduled_date + b.start_time)).slice(0, UPCOMING_LIMIT)
        );
        setOverview(overviewResult);

        // Best-effort per-appointment drive time for today, via the same travel-time-matrix
        // endpoint the map page uses - optional, since it needs the therapist's home geocoded
        // and every stop resolved, and a missing number here should never block the schedule
        // itself from showing.
        const me = therapistResult.items[0];
        const geocodedToday = todaySorted.filter((a) => a.patient_latitude != null && a.patient_longitude != null);
        if (me?.home_latitude != null && me.home_longitude != null && geocodedToday.length > 0) {
          try {
            const matrixResp = await apiFetch<TravelTimeMatrixResponse>("/maps/travel-time-matrix", {
              method: "POST",
              body: JSON.stringify({
                points: [
                  { therapist_id: me.id },
                  ...geocodedToday.map((a) => ({ patient_id: a.patient_id })),
                ],
              }),
            });
            const legs: Record<string, number> = {};
            for (let i = 0; i < geocodedToday.length; i++) {
              const cell = matrixResp.matrix[i][i + 1];
              if (cell?.reachable && cell.duration_minutes != null) {
                legs[geocodedToday[i].id] = cell.duration_minutes;
              }
            }
            setLegMinutes(legs);
          } catch {
            // Non-fatal - cards just render without a per-leg drive time.
          }
        }
      } catch {
        setError("Could not load your schedule. Please try again.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const nextAppointment = useMemo(
    () => today.find((a) => a.status === "SCHEDULED") ?? upcoming[0] ?? null,
    [today, upcoming]
  );

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm text-muted-foreground">
              {today.length === 0
                ? "No appointments scheduled today."
                : `${today.length} appointment${today.length === 1 ? "" : "s"} today${
                    nextAppointment ? ` · next: ${nextAppointment.patient_name} at ${nextAppointment.start_time.slice(0, 5)}` : ""
                  }`}
            </p>
          </div>
          <Button asChild>
            <Link href="/optimize">Optimize my day</Link>
          </Button>
        </CardContent>
      </Card>

      {overview && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Today's driving time" value={formatMinutes(overview.total_drive_minutes)} />
          <StatTile label="Today's driving distance" value={formatMiles(overview.total_distance_miles)} />
          <StatTile label="Appointments today" value={String(overview.total_appointments)} />
          {overview.recommendations_accepted > 0 && (
            <StatTile label="Time saved today" value={formatMinutes(overview.estimated_time_saved_minutes)} />
          )}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Today&apos;s schedule</CardTitle>
        </CardHeader>
        <CardContent>
          {today.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing on your calendar today - enjoy the break.</p>
          ) : (
            <div className="space-y-2">
              {today.map((appt) => (
                <AppointmentCard key={appt.id} appointment={appt} onClick={() => {}} travelTimeMinutes={legMinutes[appt.id]} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Upcoming</CardTitle>
        </CardHeader>
        <CardContent>
          {upcoming.length === 0 ? (
            <p className="text-sm text-muted-foreground">No upcoming appointments in the next week.</p>
          ) : (
            <div className="space-y-2">
              {upcoming.map((appt) => (
                <div key={appt.id} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                  <div>
                    <span className="font-medium">{appt.patient_name}</span>
                    <span className="ml-2 text-muted-foreground">
                      {appt.scheduled_date} at {appt.start_time.slice(0, 5)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
