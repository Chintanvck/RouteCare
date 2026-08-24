"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { ImportJob, ImportRowErrorEntry } from "@/types/import";
import type { PaginatedResponse } from "@/types/patient";

export function ResultsStep({ job, onStartNew }: { job: ImportJob; onStartNew: () => void }) {
  const failed = job.status === "FAILED";
  const hasErrors = job.status === "COMPLETED_WITH_ERRORS";
  const [errors, setErrors] = useState<ImportRowErrorEntry[]>([]);

  useEffect(() => {
    if (!hasErrors) return;
    apiFetch<PaginatedResponse<ImportRowErrorEntry>>(`/imports/${job.id}/errors?page_size=50`)
      .then((result) => setErrors(result.items))
      .catch(() => setErrors([]));
  }, [hasErrors, job.id]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{failed ? "Import Failed" : "Import Complete"}</CardTitle>
        <CardDescription>
          {failed
            ? job.error_message ?? "Something went wrong and the import could not finish."
            : "Here's what happened with your file."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {!failed && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <SummaryStat label="Total Rows" value={job.total_records ?? 0} />
            <SummaryStat label="Successfully Imported" value={job.successful_records ?? 0} />
            <SummaryStat label="Duplicates Skipped" value={job.duplicate_records ?? 0} />
            <SummaryStat label="Errors" value={(job.invalid_records ?? 0) + (job.failed_records ?? 0)} />
          </div>
        )}

        {hasErrors && errors.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium">Rows that could not be imported:</p>
            <ul className="max-h-48 space-y-1 overflow-y-auto rounded-md border p-3 text-sm text-muted-foreground">
              {errors.map((e, i) => (
                <li key={i}>
                  Row {e.row_number}: {e.error_message}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button asChild>
            <Link href="/patients">Go to Patients</Link>
          </Button>
          <Button variant="secondary" onClick={onStartNew}>
            Import Another File
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
