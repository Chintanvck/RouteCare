import { Card, CardContent } from "@/components/ui/card";

interface StatTileProps {
  label: string;
  value: string;
  sublabel?: string;
}

/** A single dashboard number - always a formatted string (the caller decides "12" vs "—" vs
 * "3h 42m") so this component never has to guess how to render "not enough data." */
export function StatTile({ label, value, sublabel }: StatTileProps) {
  return (
    <Card>
      <CardContent className="space-y-1 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="text-2xl font-semibold tracking-tight">{value}</p>
        {sublabel && <p className="text-xs text-muted-foreground">{sublabel}</p>}
      </CardContent>
    </Card>
  );
}
