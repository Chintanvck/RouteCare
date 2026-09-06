export function formatMinutes(minutes: number | null): string {
  if (minutes === null) return "—";
  const rounded = Math.round(minutes);
  const hours = Math.floor(rounded / 60);
  const mins = rounded % 60;
  if (hours === 0) return `${mins}m`;
  if (mins === 0) return `${hours}h`;
  return `${hours}h ${mins}m`;
}

export function formatMiles(miles: number | null): string {
  if (miles === null) return "—";
  return `${miles.toFixed(1)} mi`;
}

export function formatPct(pct: number | null): string {
  if (pct === null) return "—";
  return `${pct.toFixed(0)}%`;
}

export function formatHours(hours: number): string {
  return `${hours.toFixed(1)}h`;
}

export function formatShortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
