"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import { DAY_NAMES, type TherapistAvailabilityRule } from "@/types/therapist";

interface EditableRule {
  day_of_week: number;
  start_time: string;
  end_time: string;
  is_available: boolean;
}

function toEditable(rules: TherapistAvailabilityRule[]): EditableRule[] {
  return rules.map((r) => ({
    day_of_week: r.day_of_week,
    start_time: r.start_time.slice(0, 5),
    end_time: r.end_time.slice(0, 5),
    is_available: r.is_available,
  }));
}

export function AvailabilityEditor({
  therapistId,
  initialRules,
}: {
  therapistId: string;
  initialRules: TherapistAvailabilityRule[];
}) {
  const [rules, setRules] = useState<EditableRule[]>(toEditable(initialRules));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  function addRow(day: number) {
    setRules((prev) => [...prev, { day_of_week: day, start_time: "09:00", end_time: "17:00", is_available: true }]);
  }

  function removeRow(index: number) {
    setRules((prev) => prev.filter((_, i) => i !== index));
  }

  function updateRow(index: number, patch: Partial<EditableRule>) {
    setRules((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSavedMessage(null);
    try {
      await apiFetch(`/therapists/${therapistId}/availability`, {
        method: "PUT",
        body: JSON.stringify({
          rules: rules.map((r) => ({
            day_of_week: r.day_of_week,
            start_time: `${r.start_time}:00`,
            end_time: `${r.end_time}:00`,
            is_available: r.is_available,
          })),
        }),
      });
      setSavedMessage("Availability saved.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save availability.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Weekly Availability</CardTitle>
        <CardDescription>
          Add working hours per day. Add an &ldquo;unavailable&rdquo; block within a day for breaks (e.g. lunch). A
          day with no rows at all is a day off.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}
        {savedMessage && <div className="rounded-md border border-primary/30 bg-primary/5 px-4 py-3 text-sm">{savedMessage}</div>}

        {DAY_NAMES.map((dayName, day) => {
          const dayRules = rules
            .map((r, i) => ({ ...r, index: i }))
            .filter((r) => r.day_of_week === day);

          return (
            <div key={day} className="space-y-2 border-b pb-4 last:border-b-0">
              <div className="flex items-center justify-between">
                <p className="font-medium">{dayName}</p>
                <Button type="button" variant="outline" size="sm" onClick={() => addRow(day)}>
                  Add time block
                </Button>
              </div>

              {dayRules.length === 0 && <p className="text-sm text-muted-foreground">Not working this day.</p>}

              {dayRules.map((rule) => (
                <div key={rule.index} className="flex flex-wrap items-center gap-2">
                  <input
                    type="time"
                    className="flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                    value={rule.start_time}
                    onChange={(e) => updateRow(rule.index, { start_time: e.target.value })}
                  />
                  <span className="text-muted-foreground">to</span>
                  <input
                    type="time"
                    className="flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                    value={rule.end_time}
                    onChange={(e) => updateRow(rule.index, { end_time: e.target.value })}
                  />
                  <label className="flex items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={rule.is_available}
                      onChange={(e) => updateRow(rule.index, { is_available: e.target.checked })}
                    />
                    Available (uncheck for a break)
                  </label>
                  <Button type="button" variant="ghost" size="sm" onClick={() => removeRow(rule.index)}>
                    Remove
                  </Button>
                </div>
              ))}
            </div>
          );
        })}

        <div className="flex justify-end">
          <Button type="button" onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save Availability"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
