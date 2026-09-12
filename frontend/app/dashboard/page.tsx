"use client";

import { useCallback, useEffect, useState } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { ChartEmptyState, DaySeriesChart } from "@/components/analytics/bar-chart";
import { DateRangeControls } from "@/components/analytics/date-range-controls";
import { EfficiencyPanel } from "@/components/analytics/efficiency-panel";
import { formatMiles, formatMinutes, formatPct, formatShortDate } from "@/components/analytics/format";
import { OptimizationImpactPanel } from "@/components/analytics/optimization-impact-panel";
import { StatTile } from "@/components/analytics/stat-tile";
import { TherapistBreakdownTable } from "@/components/analytics/therapist-breakdown-table";
import { TherapistTodayPanel } from "@/components/dashboard/therapist-today-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/lib/use-current-user";
import { useRequireAuth } from "@/lib/use-require-auth";
import type {
  AnalyticsOverview,
  AnalyticsPeriod,
  EfficiencyMetrics,
  OptimizationImpact,
  TherapistAnalyticsResponse,
} from "@/types/analytics";

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function buildDateParams(period: AnalyticsPeriod, customStart: string, customEnd: string): URLSearchParams {
  const params = new URLSearchParams({ period });
  if (period === "custom") {
    params.set("start_date", customStart);
    params.set("end_date", customEnd);
  }
  return params;
}

export default function DashboardPage() {
  const { checked } = useRequireAuth();
  const { user: currentUser, loading: userLoading } = useCurrentUser(checked);

  const [period, setPeriod] = useState<AnalyticsPeriod>("this_week");
  const [customStart, setCustomStart] = useState(todayIso());
  const [customEnd, setCustomEnd] = useState(todayIso());
  const [selectedTherapistId, setSelectedTherapistId] = useState<string | null>(null);

  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [therapistData, setTherapistData] = useState<TherapistAnalyticsResponse | null>(null);
  const [efficiency, setEfficiency] = useState<EfficiencyMetrics | null>(null);
  const [impact, setImpact] = useState<OptimizationImpact | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isAdminOrScheduler = currentUser?.role === "CLINIC_ADMIN" || currentUser?.role === "OFFICE_SCHEDULER";
  const isTherapist = currentUser?.role === "THERAPIST";

  const loadDashboard = useCallback(async () => {
    if (period === "custom" && (!customStart || !customEnd)) return;
    setLoading(true);
    setError(null);
    try {
      const dateParams = buildDateParams(period, customStart, customEnd).toString();
      const detailParams = new URLSearchParams(dateParams);
      if (selectedTherapistId) detailParams.set("therapist_id", selectedTherapistId);

      const [overviewResult, therapistResult, efficiencyResult, impactResult] = await Promise.all([
        apiFetch<AnalyticsOverview>(`/analytics/overview?${dateParams}`),
        apiFetch<TherapistAnalyticsResponse>(`/analytics/therapists?${dateParams}`),
        apiFetch<EfficiencyMetrics>(`/analytics/efficiency?${detailParams.toString()}`),
        apiFetch<OptimizationImpact>(`/analytics/optimization-impact?${detailParams.toString()}`),
      ]);
      setOverview(overviewResult);
      setTherapistData(therapistResult);
      setEfficiency(efficiencyResult);
      setImpact(impactResult);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the dashboard. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [period, customStart, customEnd, selectedTherapistId]);

  useEffect(() => {
    if (checked && currentUser && !isTherapist) loadDashboard();
  }, [checked, currentUser, isTherapist, loadDashboard]);

  if (!checked || userLoading) return null;

  if (isTherapist) {
    return (
      <>
        <AppHeader />
        <main className="container max-w-4xl space-y-6 py-8">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Your schedule</h1>
            <p className="text-sm text-muted-foreground">Today&apos;s appointments, driving time, and optimization - just for you.</p>
          </div>
          <TherapistTodayPanel />
        </main>
      </>
    );
  }

  return (
    <>
      <AppHeader />
      <main className="container max-w-6xl space-y-6 py-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            How efficiently the clinic is scheduled - appointment volume, driving time, therapist utilization, and
            optimization results actually accepted.
          </p>
        </div>

        <DateRangeControls
          period={period}
          customStart={customStart}
          customEnd={customEnd}
          onPeriodChange={setPeriod}
          onCustomStartChange={setCustomStart}
          onCustomEndChange={setCustomEnd}
        />

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {loading && !overview && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        )}

        {overview && (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatTile label="Total appointments" value={String(overview.total_appointments)} />
              <StatTile label="Completed" value={String(overview.completed_appointments)} />
              <StatTile label="Scheduled" value={String(overview.scheduled_appointments)} />
              <StatTile
                label="Cancelled / no-show"
                value={`${overview.cancelled_appointments} / ${overview.no_show_appointments}`}
              />
              <StatTile label="Total driving time" value={formatMinutes(overview.total_drive_minutes)} />
              <StatTile label="Total driving distance" value={formatMiles(overview.total_distance_miles)} />
              <StatTile label="Avg. utilization" value={formatPct(overview.average_utilization_pct)} />
              <StatTile label="Optimization runs" value={String(overview.optimization_runs)} />
            </div>

            {overview.recommendations_accepted > 0 && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-2">
                <StatTile label="Estimated time saved" value={formatMinutes(overview.estimated_time_saved_minutes)} sublabel={`${overview.recommendations_accepted} accepted recommendation${overview.recommendations_accepted === 1 ? "" : "s"}`} />
                <StatTile label="Estimated distance saved" value={formatMiles(overview.estimated_miles_saved)} />
              </div>
            )}

            <div className="grid gap-6 sm:grid-cols-2">
              <div className="space-y-2">
                <p className="text-sm font-medium">Appointments by day</p>
                {overview.appointments_by_day.length >= 2 ? (
                  <DaySeriesChart
                    items={overview.appointments_by_day.map((d) => ({ date: d.date, value: d.count }))}
                    dateFormatter={formatShortDate}
                  />
                ) : (
                  <ChartEmptyState message="Not enough days with appointments to chart yet." />
                )}
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">Driving time by day</p>
                {overview.drive_minutes_by_day.length >= 2 ? (
                  <DaySeriesChart
                    items={overview.drive_minutes_by_day.map((d) => ({ date: d.date, value: d.minutes }))}
                    valueFormatter={(v) => `${Math.round(v)}m`}
                    dateFormatter={formatShortDate}
                  />
                ) : (
                  <ChartEmptyState message="Not enough days with driving data to chart yet." />
                )}
              </div>
            </div>
          </>
        )}

        {therapistData && (
          <TherapistBreakdownTable
            therapists={therapistData.therapists}
            selectedTherapistId={selectedTherapistId}
            onSelect={setSelectedTherapistId}
            selectable={Boolean(isAdminOrScheduler)}
          />
        )}

        {efficiency && therapistData && (
          <EfficiencyPanel
            efficiency={efficiency}
            therapists={therapistData.therapists}
            showTherapistComparisons={Boolean(isAdminOrScheduler) && !selectedTherapistId}
          />
        )}

        {impact && <OptimizationImpactPanel impact={impact} />}
      </main>
    </>
  );
}
