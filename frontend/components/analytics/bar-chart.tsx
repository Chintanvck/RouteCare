/**
 * RouteCare AI - dependency-free bar charts for the analytics dashboard.
 *
 * No charting library is added here on purpose - the project's existing
 * lib/api.ts docstring already sets the precedent ("the app's data needs
 * are simple enough that adding [a dependency] would be the kind of
 * dependency the coding standards explicitly warn against"), and a
 * label + proportional-width/height bar is all these charts need.
 */

interface BarItem {
  label: string;
  value: number;
}

const BAR_COLOR = "bg-primary";
const TRACK_COLOR = "bg-muted";

function formatValue(value: number, valueFormatter?: (v: number) => string): string {
  return valueFormatter ? valueFormatter(value) : String(value);
}

/** Horizontal bars - one row per item, bar width proportional to the largest value. Good for
 * comparing therapists (drive time by therapist, utilization by therapist). */
export function HorizontalBarList({
  items,
  valueFormatter,
}: {
  items: BarItem[];
  valueFormatter?: (v: number) => string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.label} className="space-y-1">
          <div className="flex items-center justify-between text-sm">
            <span className="truncate pr-2">{item.label}</span>
            <span className="shrink-0 font-medium tabular-nums">{formatValue(item.value, valueFormatter)}</span>
          </div>
          <div className={`h-2 w-full overflow-hidden rounded-full ${TRACK_COLOR}`}>
            <div
              className={`h-full rounded-full ${BAR_COLOR}`}
              style={{ width: `${Math.max(2, (item.value / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Vertical bars over a date-ordered series - for "appointments by day" / "driving time by day"
 * trend charts. */
export function DaySeriesChart({
  items,
  valueFormatter,
  dateFormatter,
}: {
  items: { date: string; value: number }[];
  valueFormatter?: (v: number) => string;
  dateFormatter?: (d: string) => string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="flex items-end gap-2" style={{ height: 140 }}>
      {items.map((item) => (
        <div key={item.date} className="flex flex-1 flex-col items-center gap-1">
          <span className="text-xs font-medium tabular-nums text-muted-foreground">
            {formatValue(item.value, valueFormatter)}
          </span>
          <div className={`flex w-full flex-1 items-end overflow-hidden rounded-t-sm ${TRACK_COLOR}`}>
            <div
              className={`w-full rounded-t-sm ${BAR_COLOR}`}
              style={{ height: `${Math.max(2, (item.value / max) * 100)}%` }}
            />
          </div>
          <span className="text-xs text-muted-foreground">
            {dateFormatter ? dateFormatter(item.date) : item.date.slice(5)}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Shown instead of a chart when there isn't enough data to make one meaningful - per the task's
 * explicit "avoid charts for metrics with too little data / show empty states." */
export function ChartEmptyState({ message }: { message: string }) {
  return (
    <div className="flex h-[140px] items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
      {message}
    </div>
  );
}
