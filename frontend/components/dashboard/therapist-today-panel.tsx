"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Navigation } from "lucide-react";

import { AppointmentCard } from "@/components/scheduling/appointment-card";
import { StatTile } from "@/components/analytics/stat-tile";
import { formatMiles, formatMinutes } from "@/components/analytics/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { buildNavigationUrl } from "@/lib/navigation";
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

function formatFriendlyDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
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
 *
 * Section order is deliberately mobile-first: date -> next appointment (with its own Navigate
 * action) -> optimize CTA -> daily metrics -> today's full schedule -> upcoming. A therapist
 * checking their phone between visits shouldn't have to scroll past a metrics grid to find out
 * who/when/where their next stop is.
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

  const nextAppointmentNavUrl = useMemo(
    () =>
      nextAppointment
        ? buildNavigationUrl({
            latitude: nextAppointment.patient_latitude,
            longitude: nextAppointment.patient_longitude,
            address: nextAppointment.patient_address,
          })
        : null,
    [nextAppointment]
  );

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-24 w-full" />
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
    <div className="space-y-4 sm:space-y-6">
      {overview && (
        <p className="text-sm font-medium text-muted-foreground">{formatFriendlyDate(overview.date_range.start_date)}</p>
      )}

      {/* Next appointment - the single most important thing on this page: who, when, where, and a
          one-tap way to get there. Everything else is supporting detail. */}
      <Card className="border-primary/30 bg-primary/[0.03]">
        <CardContent className="space-y-2 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-primary">Next appointment</p>
          {nextAppointment ? (
            <>
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-lg font-semibold leading-tight">{nextAppointment.patient_name}</p>
                <p className="shrink-0 text-sm font-medium text-muted-foreground">
                  {nextAppointment.start_time.slice(0, 5)}
                </p>
              </div>
              <p className="text-sm leading-snug text-muted-foreground">{nextAppointment.patient_address}</p>
              {legMinutes[nextAppointment.id] != null && (
                <p className="text-sm text-muted-foreground">~{Math.round(legMinutes[nextAppointment.id])} min drive</p>
              )}
              {nextAppointmentNavUrl && (
                <a
                  href={nextAppointmentNavUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-primary text-sm font-medium text-primary-foreground hover:bg-primary/90 sm:w-auto sm:px-6"
                >
                  <Navigation className="h-4 w-4" />
                  Navigate
                </a>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No appointments today - enjoy the break.</p>
          )}
        </CardContent>
      </Card>

      {/* Optimize CTA - kept short; the "who/when" detail already lives in the card above, so this
          only needs to say how many and offer the action. */}
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">
            {today.length === 0
              ? "No appointments scheduled today."
              : `${today.length} appointment${today.length === 1 ? "" : "s"} today`}
          </p>
          <Button asChild className="h-10 w-full sm:w-auto">
            <Link href="/optimize">Optimize my day</Link>
          </Button>
        </CardContent>
      </Card>

      {overview && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile label="Today's driving time" value={formatMinutes(overview.total_drive_minutes)} />
          <StatTile label="Today's driving distance" value={formatMiles(overview.total_distance_miles)} />
          <StatTile label="Appointments today" value={String(overview.total_appointments)} />
          {overview.recommendations_accepted > 0 && (
            <StatTile label="Time saved today" value={formatMinutes(overview.estimated_time_saved_minutes)} />
          )}
        </div>
      )}

      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-base">Today&apos;s schedule</CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
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
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-base">Upcoming</CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
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
