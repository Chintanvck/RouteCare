"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartEmptyState, DaySeriesChart } from "./bar-chart";
import { formatMiles, formatMinutes, formatPct, formatShortDate } from "./format";
import { StatTile } from "./stat-tile";
import type { OptimizationImpact } from "@/types/analytics";

const MODE_LABELS: Record<string, string> = {
  DAY_SCHEDULE_OPTIMIZATION: "Day re-order",
  WEEK_SCHEDULE_OPTIMIZATION: "Week re-order",
  NEW_PATIENT_PLACEMENT: "New patient placement",
};

interface OptimizationImpactPanelProps {
  impact: OptimizationImpact;
}

/** Only ever renders numbers backed by ACCEPTED recommendations with a real before/after
 * comparison (see backend/app/services/analytics_service.py's compute_optimization_impact) - a
 * rejected recommendation or a What-If scenario can never appear here, so this component never
 * needs to second-guess what it's given. */
export function OptimizationImpactPanel({ impact }: OptimizationImpactPanelProps) {
  const hasSavings = impact.recommendations_with_savings > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Optimization impact</CardTitle>
        <p className="text-sm text-muted-foreground">
          Based on {impact.recommendations_accepted} accepted recommendation{impact.recommendations_accepted === 1 ? "" : "s"} this period.
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {hasSavings ? (
          <>
            <div className="rounded-md border border-primary/30 bg-primary/5 px-4 py-3 text-sm">
              RouteCare reduced estimated driving by <strong>{formatMinutes(impact.total_time_saved_minutes)}</strong>
              {impact.total_miles_saved ? (
                <>
                  {" "}
                  (<strong>{formatMiles(impact.total_miles_saved)}</strong>) this period by accepting {impact.recommendations_with_savings} schedule recommendation
                  {impact.recommendations_with_savings === 1 ? "" : "s"}.
                </>
              ) : (
                " this period."
              )}
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <StatTile label="Time saved" value={formatMinutes(impact.total_time_saved_minutes)} />
              <StatTile label="Distance saved" value={formatMiles(impact.total_miles_saved)} />
              <StatTile label="Improvement" value={formatPct(impact.percentage_improvement)} />
            </div>

            <div className="space-y-2">
              <p className="text-sm font-medium">Savings over time</p>
              {impact.savings_by_day.length >= 2 ? (
                <DaySeriesChart
                  items={impact.savings_by_day.map((d) => ({ date: d.date, value: d.time_saved_minutes }))}
                  valueFormatter={(v) => `${Math.round(v)}m`}
                  dateFormatter={formatShortDate}
                />
              ) : (
                <ChartEmptyState message="Not enough accepted days yet to chart a trend." />
              )}
            </div>

            <div className="space-y-2">
              <p className="text-sm font-medium">Recent accepted recommendations</p>
              <div className="space-y-2">
                {impact.recent_examples.map((example) => (
                  <div key={example.recommendation_id} className="rounded-md border px-3 py-2 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{example.therapist_name}</span>
                      <span className="text-xs text-muted-foreground">
                        {MODE_LABELS[example.mode] ?? example.mode} · {example.target_date}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                      <span>Before: {formatMinutes(example.before_drive_minutes)}</span>
                      <span>→</span>
                      <span>After: {formatMinutes(example.after_drive_minutes)}</span>
                      <span className="font-medium text-foreground">
                        Saved {formatMinutes(example.time_saved_minutes)} / {formatMiles(example.miles_saved)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            No accepted schedule-optimization recommendations with a measurable driving-time saving in this period yet.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
