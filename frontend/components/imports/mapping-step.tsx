"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { MAPPING_TARGETS } from "@/types/import";

interface MappingStepProps {
  detectedHeaders: string[];
  suggestedMapping: Record<string, string>;
  onSubmit: (mapping: Record<string, string>) => Promise<void>;
  onCancel: () => void;
}

const UNMAPPED = "";

export function MappingStep({ detectedHeaders, suggestedMapping, onSubmit, onCancel }: MappingStepProps) {
  const [selections, setSelections] = useState<Record<string, string>>(() => ({ ...suggestedMapping }));
  const [submitting, setSubmitting] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);

  const usedHeaders = new Set(Object.values(selections).filter(Boolean));

  function setTarget(target: string, header: string) {
    setSelections((prev) => {
      const next = { ...prev };
      if (header === UNMAPPED) {
        delete next[target];
      } else {
        next[target] = header;
      }
      return next;
    });
  }

  async function handleSubmit() {
    setProblems([]);
    setSubmitting(true);
    try {
      await onSubmit(selections);
    } catch (err) {
      const details = (err as { details?: { problems?: string[] } })?.details;
      setProblems(details?.problems ?? [(err as Error).message ?? "Could not save this mapping."]);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Column Mapping</CardTitle>
        <CardDescription>
          Match each RouteCare field to a column from your file. Map either &ldquo;Full Name&rdquo;, or both
          &ldquo;First Name&rdquo; and &ldquo;Last Name&rdquo;.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {problems.length > 0 && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <ul className="list-disc space-y-1 pl-4">
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          </div>
        )}

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>RouteCare Field</TableHead>
              <TableHead>Excel Column</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {MAPPING_TARGETS.map((target) => (
              <TableRow key={target.value}>
                <TableCell className="font-medium">
                  {target.label}
                  {target.required && <span className="ml-1 text-destructive">*</span>}
                </TableCell>
                <TableCell>
                  <select
                    className="flex h-9 w-full max-w-xs rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                    value={selections[target.value] ?? UNMAPPED}
                    onChange={(e) => setTarget(target.value, e.target.value)}
                  >
                    <option value={UNMAPPED}>-- Not mapped --</option>
                    {detectedHeaders.map((header) => (
                      <option
                        key={header}
                        value={header}
                        disabled={usedHeaders.has(header) && selections[target.value] !== header}
                      >
                        {header}
                      </option>
                    ))}
                  </select>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Validating..." : "Continue"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
