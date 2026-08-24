"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, apiFetch } from "@/lib/api";
import type { ImportJob, ImportRow, RowClassification } from "@/types/import";
import type { PaginatedResponse } from "@/types/patient";

interface PreviewStepProps {
  job: ImportJob;
  onConfirm: (includeDuplicates: boolean) => Promise<void>;
  onCancel: () => void;
}

const CLASSIFICATION_LABEL: Record<RowClassification, string> = {
  VALID: "New patient",
  INVALID: "Error",
  DUPLICATE_EXACT: "Exact duplicate",
  DUPLICATE_PROBABLE: "Probable duplicate",
};

const CLASSIFICATION_VARIANT: Record<RowClassification, "default" | "destructive" | "secondary"> = {
  VALID: "default",
  INVALID: "destructive",
  DUPLICATE_EXACT: "secondary",
  DUPLICATE_PROBABLE: "secondary",
};

export function PreviewStep({ job, onConfirm, onCancel }: PreviewStepProps) {
  const [rows, setRows] = useState<ImportRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [includeDuplicates, setIncludeDuplicates] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch<PaginatedResponse<ImportRow>>(`/imports/${job.id}/preview?page_size=50`)
      .then((result) => {
        if (!cancelled) setRows(result.items);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the preview.");
      });
    return () => {
      cancelled = true;
    };
  }, [job.id]);

  async function handleConfirm() {
    setConfirming(true);
    setError(null);
    try {
      await onConfirm(includeDuplicates);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the import. Please try again.");
      setConfirming(false);
    }
  }

  const duplicateCount = job.duplicate_records ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Validation &amp; Duplicate Review</CardTitle>
        <CardDescription>Review what will be imported before confirming.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <SummaryStat label="Total Rows" value={job.total_records ?? 0} />
          <SummaryStat label="New Patients" value={job.new_records ?? 0} />
          <SummaryStat label="Duplicates" value={duplicateCount} />
          <SummaryStat label="Errors" value={job.invalid_records ?? 0} />
          <SummaryStat label="Ready to Import" value={job.new_records ?? 0} />
        </div>

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {rows === null && !error && (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        )}

        {rows !== null && (
          <div className="max-h-96 overflow-y-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Row</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>ZIP</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.row_number}>
                    <TableCell>{row.row_number}</TableCell>
                    <TableCell>
                      {[row.mapped_data.first_name, row.mapped_data.last_name].filter(Boolean).join(" ") || "—"}
                    </TableCell>
                    <TableCell>{(row.mapped_data.zip_code as string) || "—"}</TableCell>
                    <TableCell>
                      <Badge variant={CLASSIFICATION_VARIANT[row.classification]}>
                        {CLASSIFICATION_LABEL[row.classification]}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {row.classification === "INVALID" &&
                        row.errors?.map((e) => e.message).join("; ")}
                      {(row.classification === "DUPLICATE_EXACT" || row.classification === "DUPLICATE_PROBABLE") &&
                        (row.duplicate_of_row_number
                          ? `Matches row ${row.duplicate_of_row_number} in this file`
                          : `Matches an existing patient${row.duplicate_confidence ? ` (${row.duplicate_confidence}% confidence)` : ""}`)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {duplicateCount > 0 && (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={includeDuplicates}
              onChange={(e) => setIncludeDuplicates(e.target.checked)}
            />
            <span>
              Import the {duplicateCount} duplicate{duplicateCount === 1 ? "" : "s"} anyway, as new patient records.
              By default, duplicates are skipped and nothing about the matching existing patient is changed.
            </span>
          </label>
        )}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={onCancel} disabled={confirming}>
            Cancel
          </Button>
          <Button type="button" onClick={handleConfirm} disabled={confirming || rows === null}>
            {confirming ? "Starting import..." : "Confirm Import"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SummaryStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border p-3 text-center">
      <p className="text-2xl font-semibold">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
