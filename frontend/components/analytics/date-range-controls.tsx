"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { AnalyticsPeriod } from "@/types/analytics";

const PERIOD_LABELS: Record<AnalyticsPeriod, string> = {
  today: "Today",
  this_week: "This week",
  last_week: "Last week",
  this_month: "This month",
  custom: "Custom",
};

interface DateRangeControlsProps {
  period: AnalyticsPeriod;
  customStart: string;
  customEnd: string;
  onPeriodChange: (period: AnalyticsPeriod) => void;
  onCustomStartChange: (value: string) => void;
  onCustomEndChange: (value: string) => void;
}

export function DateRangeControls({
  period,
  customStart,
  customEnd,
  onPeriodChange,
  onCustomStartChange,
  onCustomEndChange,
}: DateRangeControlsProps) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex gap-2">
        {(Object.keys(PERIOD_LABELS) as AnalyticsPeriod[]).map((p) => (
          <Button key={p} type="button" size="sm" variant={period === p ? "default" : "outline"} onClick={() => onPeriodChange(p)}>
            {PERIOD_LABELS[p]}
          </Button>
        ))}
      </div>
      {period === "custom" && (
        <div className="flex items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor="range-start" className="text-xs">
              Start
            </Label>
            <Input
              id="range-start"
              type="date"
              value={customStart}
              onChange={(e) => onCustomStartChange(e.target.value)}
              className="h-9"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="range-end" className="text-xs">
              End
            </Label>
            <Input
              id="range-end"
              type="date"
              value={customEnd}
              onChange={(e) => onCustomEndChange(e.target.value)}
              className="h-9"
            />
          </div>
        </div>
      )}
    </div>
  );
}
